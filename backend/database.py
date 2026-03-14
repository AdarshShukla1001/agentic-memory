import sqlite3
import chromadb
from chromadb.utils import embedding_functions
import os
import datetime
from typing import List, Dict, Any

DB_PATH = "memories.db"
CHROMA_PATH = "./chroma_db"

class DatabaseManager:
    def __init__(self, openai_api_key: str):
        self.sqlite_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.init_sqlite()
        
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=openai_api_key,
            model_name="text-embedding-3-small"
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name="user_memories",
            embedding_function=self.embedding_fn
        )

    def init_sqlite(self):
        cursor = self.sqlite_conn.cursor()
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                hashed_password TEXT,
                created_at DATETIME
            )
        ''')
        
        # Memories table with importance
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(memories)")
            columns = [column[1] for column in cursor.fetchall()]
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN user_id TEXT DEFAULT 'default_user'")
            if "importance" not in columns:
                cursor.execute("ALTER TABLE memories ADD COLUMN importance INTEGER DEFAULT 5")
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    type TEXT,
                    content TEXT,
                    importance INTEGER,
                    timestamp DATETIME
                )
            ''')
        self.sqlite_conn.commit()

    def create_user(self, username, hashed_password):
        user_id = f"user_{os.urandom(4).hex()}"
        timestamp = datetime.datetime.now().isoformat()
        cursor = self.sqlite_conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO users (id, username, hashed_password, created_at) VALUES (?, ?, ?, ?)',
                (user_id, username, hashed_password, timestamp)
            )
            self.sqlite_conn.commit()
            return {"id": user_id, "username": username}
        except sqlite3.IntegrityError:
            return None

    def get_user(self, username):
        cursor = self.sqlite_conn.cursor()
        cursor.execute('SELECT id, username, hashed_password FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "username": row[1], "hashed_password": row[2]}
        return None

    def is_duplicate(self, user_id: str, content: str, threshold: float = 0.1) -> bool:
        """Check if a similar memory already exists for the user."""
        results = self.collection.query(
            query_texts=[content],
            n_results=1,
            where={"user_id": user_id}
        )
        if results['distances'] and len(results['distances'][0]) > 0:
            # Low distance means high similarity
            if results['distances'][0][0] < threshold:
                return True
        return False

    def store_memory(self, user_id: str, mem_type: str, content: str, importance: int = 5):
        # Deduplication check
        if self.is_duplicate(user_id, content):
            print(f"Skipping duplicate memory: {content}")
            return None

        mem_id = f"mem_{os.urandom(4).hex()}"
        timestamp = datetime.datetime.now().isoformat()
        
        # Store in SQLite
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            'INSERT INTO memories (id, user_id, type, content, importance, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
            (mem_id, user_id, mem_type, content, importance, timestamp)
        )
        self.sqlite_conn.commit()
        
        # Store in ChromaDB for semantic search
        self.collection.add(
            ids=[mem_id],
            documents=[content],
            metadatas=[{"user_id": user_id, "type": mem_type, "timestamp": timestamp, "importance": importance}]
        )
        
        return {"id": mem_id, "type": mem_type, "memory": content, "importance": importance, "created_at": timestamp}

    def get_memories(self, user_id: str, limit: int = 50):
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            'SELECT id, type, content, timestamp, importance FROM memories WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?',
            (user_id, limit)
        )
        rows = cursor.fetchall()
        return [{"id": r[0], "type": r[1], "memory": r[2], "created_at": r[3], "importance": r[4]} for r in rows]

    def search_memories(self, user_id: str, query: str, limit: int = 5):
        results = self.collection.query(
            query_texts=[query],
            n_results=limit,
            where={"user_id": user_id}
        )
        
        memories = []
        if results['documents']:
            for i in range(len(results['documents'][0])):
                meta = results['metadatas'][0][i]
                memories.append({
                    "content": results['documents'][0][i],
                    "type": meta['type'],
                    "id": results['ids'][0][i],
                    "importance": meta.get('importance', 5)
                })
        return memories

    def clear_memories(self, user_id: str):
        cursor = self.sqlite_conn.cursor()
        cursor.execute('DELETE FROM memories WHERE user_id = ?', (user_id,))
        self.sqlite_conn.commit()
        
        self.collection.delete(where={"user_id": user_id})

    def close(self):
        self.sqlite_conn.close()

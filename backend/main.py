import os
import json
import asyncio
import sqlite3
import datetime
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Setup
DB_PATH = "memories.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            type TEXT,
            content TEXT,
            timestamp DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Simple Memory Layer (Multi-Layer SQLite Implementation)
class MultiLayerMemory:
    def __init__(self):
        self.short_term = [] # List of {role, content} - last 5 messages

    def add_to_short_term(self, role, content):
        self.short_term.append({"role": role, "content": content})
        if len(self.short_term) > 10: # Keep last 10 turns
            self.short_term.pop(0)

    def add_long_term(self, mem_type, content):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        mem_id = f"mem_{os.urandom(4).hex()}"
        timestamp = datetime.datetime.now().isoformat()
        cursor.execute('INSERT INTO memories VALUES (?, ?, ?, ?)', (mem_id, mem_type, content, timestamp))
        conn.commit()
        conn.close()
        return {"id": mem_id, "type": mem_type, "memory": content, "created_at": timestamp}

    async def extract_and_store(self, text):
        # Use LLM to classify and extract facts
        prompt = f"""
        Extract and classify facts from this message: '{text}'.
        Classify each fact into one of these types:
        - FACTUAL: Stable facts about the user (name, age, skills, location).
        - EPISODIC: Specific events or experiences (e.g., "I went to a concert").
        - SEMANTIC: General knowledge or distilled beliefs (e.g., "I think coding is art").

        Return a JSON array of objects: [{{"type": "FACTUAL|EPISODIC|SEMANTIC", "content": "the fact"}}]
        If no facts found, return [].
        Return ONLY valid JSON.
        """
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        try:
            data = json.loads(response.choices[0].message.content)
            extracted = data.get("facts", data.get("memories", []))
            if not isinstance(extracted, list) and isinstance(data, dict):
                # Handle cases where LLM might return {"FACTUAL": [...]} etc.
                if "facts" not in data and len(data) > 0:
                    # heuristic: if no "facts" key, maybe the root is the object we want if it has type/content
                    if "type" in data and "content" in data:
                        extracted = [data]
            
            added = []
            for item in extracted:
                res = self.add_long_term(item["type"], item["content"])
                added.append(res)
            return added
        except Exception as e:
            print(f"Extraction error: {e}")
            return []

    def get_all(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id, type, content, timestamp FROM memories ORDER BY timestamp DESC')
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r[0], "type": r[1], "memory": r[2], "created_at": r[3]} for r in rows]

    def search(self, text):
        # For this simple demo, we'll retrieve all and let the LLM filter, 
        # or just return the most recent 10 across types.
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT type, content FROM memories ORDER BY timestamp DESC LIMIT 20')
        rows = cursor.fetchall()
        conn.close()
        
        # Categorize for the prompt
        categorized = {"FACTUAL": [], "EPISODIC": [], "SEMANTIC": []}
        for r in rows:
            if r[0] in categorized:
                categorized[r[0]].append(r[1])
        return categorized

    def clear(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM memories')
        conn.commit()
        conn.close()
        self.short_term = []

# Initialize Services
client = None
memory = MultiLayerMemory()

try:
    if os.getenv("OPENAI_API_KEY"):
        client = OpenAI()
    else:
        print("WARNING: OPENAI_API_KEY not found. Chat features will not work.")
except Exception as e:
    print(f"Error initializing OpenAI: {e}")

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

async def emit_event(event_type: str, data: Any):
    print(f"Emitting event: {event_type}")
    payload = {
        "type": event_type,
        "data": data
    }
    await manager.broadcast(json.dumps(payload))

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/chat")
async def chat(request: ChatRequest):
    if not client:
        error_msg = "OpenAI API Key is missing. Please set it in the .env file and restart the backend."
        await emit_event("ERROR", {"message": error_msg})
        raise HTTPException(status_code=500, detail=error_msg)

    user_message = request.message
    user_id = request.user_id

    try:
        # 0. Add to Short Term
        memory.add_to_short_term("user", user_message)
        
        # 1. User Message
        await emit_event("USER_MESSAGE", {"message": user_message})

        # 2. Memory Extraction & Storage
        await emit_event("PIPELINE_STEP", {"step": "Extracting & Classifying Facts..."})
        memories_added = await memory.extract_and_store(user_message)
        
        extracted_summary = [f"{m['type']}: {m['memory']}" for m in memories_added]
        await emit_event("MEMORY_EXTRACTED", {"facts": extracted_summary})
        await emit_event("MEMORY_STORED", {"memories": memories_added})

        # 3. Memory Retrieval
        await emit_event("PIPELINE_STEP", {"step": "Retrieving context across layers..."})
        retrieved_categorized = memory.search(user_message)
        
        context_parts = []
        for m_type, contents in retrieved_categorized.items():
            if contents:
                context_parts.append(f"[{m_type} MEMORY]:\n- " + "\n- ".join(contents))
        
        # Add Short term summary
        st_summary = "\n".join([f"{m['role']}: {m['content']}" for m in memory.short_term[:-1]]) # Hide current message
        if st_summary:
            context_parts.append(f"[SHORT-TERM MEMORY]:\n{st_summary}")

        context_str = "\n\n".join(context_parts)
        
        # Flatten for the timeline
        flat_retrieved = []
        for t, cs in retrieved_categorized.items():
            for c in cs:
                flat_retrieved.append({"type": t, "memory": c})

        await emit_event("MEMORY_RETRIEVED", {"memories": flat_retrieved})

        # 4. Prompt Construction
        system_prompt = f"You are a helpful AI assistant. Use the following multi-layer memory context to personalize your response:\n\n{context_str}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        await emit_event("PROMPT_CREATED", {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "full_messages": messages
        })

        # 5. LLM Call
        await emit_event("PIPELINE_STEP", {"step": "Calling OpenAI..."})
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        assistant_response = response.choices[0].message.content
        
        # Add assistant response to ST memory
        memory.add_to_short_term("assistant", assistant_response)
        
        await emit_event("LLM_RESPONSE", {"response": assistant_response})

        return {"response": assistant_response}

    except Exception as e:
        import traceback
        traceback.print_exc()
        await emit_event("ERROR", {"message": str(e)})
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories")
async def get_memories(user_id: str = "default_user"):
    return memory.get_all()

@app.delete("/memories")
async def delete_memories(user_id: str = "default_user"):
    memory.clear()
    return {"message": "Memory cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

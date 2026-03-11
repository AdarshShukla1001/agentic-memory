from typing import List, Dict, Any
from database import DatabaseManager
from llm_service import LLMService

class MemoryManager:
    def __init__(self, db_manager: DatabaseManager, llm_service: LLMService):
        self.db = db_manager
        self.llm = llm_service
        self.short_term_context: Dict[str, List[Dict[str, str]]] = {}

    def add_to_short_term(self, user_id: str, role: str, content: str):
        if user_id not in self.short_term_context:
            self.short_term_context[user_id] = []
        
        self.short_term_context[user_id].append({"role": role, "content": content})
        if len(self.short_term_context[user_id]) > 10:
            self.short_term_context[user_id].pop(0)

    async def process_user_message(self, user_id: str, text: str):
        # 1. Add to short term
        self.add_to_short_term(user_id, "user", text)
        
        # 2. Extract and store long-term memories
        extracted_memories = await self.llm.extract_memories(text)
        memories_added = []
        for mem in extracted_memories:
            # Only store if importance is at least 3 (skip trivial stuff to reduce size)
            importance = mem.get("importance", 5)
            if importance < 3:
                print(f"Skipping low importance memory: {mem['content']}")
                continue
                
            res = self.db.store_memory(user_id, mem["type"], mem["content"], importance)
            if res:
                memories_added.append(res)
            
        return memories_added

    def get_context_for_llm(self, user_id: str, query: str) -> str:
        # Retrieve semantic context
        semantic_mems = self.db.search_memories(user_id, query, limit=5)
        
        # Retrieve recent factual/episodic context from SQLite for stability
        recent_mems = self.db.get_memories(user_id, limit=10)
        
        context_parts = []
        
        if semantic_mems:
            context_parts.append("[RELEVANT PAST MEMORIES]:")
            for m in semantic_mems:
                context_parts.append(f"- {m['type']}: {m['content']}")
        
        if recent_mems:
            context_parts.append("\n[RECENT CONTEXT]:")
            # Filter to avoid too much redundancy if semantic returned the same
            seen_content = {m['content'] for m in semantic_mems}
            for m in recent_mems:
                if m['memory'] not in seen_content:
                    context_parts.append(f"- {m['type']}: {m['memory']}")

        # Short term
        st = self.short_term_context.get(user_id, [])
        if st:
            context_parts.append("\n[CURRENT CONVERSATION]:")
            for msg in st[:-1]: # exclude current message which is handled by LLM call
                context_parts.append(f"{msg['role']}: {msg['content']}")
                
        return "\n".join(context_parts)

    def get_all_memories(self, user_id: str):
        return self.db.get_memories(user_id)

    def clear_all(self, user_id: str):
        self.db.clear_memories(user_id)
        if user_id in self.short_term_context:
            self.short_term_context[user_id] = []

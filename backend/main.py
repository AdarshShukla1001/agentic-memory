import os
import json
import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from auth import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    get_current_user,
    TokenData,
    SECRET_KEY,
    ALGORITHM
)
from jose import jwt, JWTError

from database import DatabaseManager
from llm_service import LLMService
from memory_manager import MemoryManager

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Services
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("WARNING: OPENAI_API_KEY not found. Backend will not function correctly.")

db_manager = DatabaseManager(api_key)
llm_service = LLMService(api_key)
memory_manager = MemoryManager(db_manager, llm_service)

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {} # user_id -> websocket

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_to_user(self, user_id: str, message: str):
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_text(message)
            except:
                pass

manager = ConnectionManager()

async def emit_event(user_id: str, event_type: str, data: Any):
    print(f"Emitting event to {user_id}: {event_type}")
    payload = {
        "type": event_type,
        "data": data
    }
    await manager.send_to_user(user_id, json.dumps(payload))

@app.post("/signup")
async def signup(user: UserCreate):
    existing_user = db_manager.get_user(user.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = db_manager.create_user(user.username, hashed_password)
    if not new_user:
        raise HTTPException(status_code=500, detail="Error creating user")
    
    return {"message": "User created successfully"}

@app.post("/login")
async def login(user: UserLogin):
    db_user = db_manager.get_user(user.username)
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": db_user["username"], "id": db_user["id"]})
    return {"access_token": access_token, "token_type": "bearer", "username": db_user["username"]}

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id)

@app.post("/chat")
async def chat(request: ChatRequest, current_user: TokenData = Depends(get_current_user)):
    if not api_key:
        error_msg = "OpenAI API Key is missing."
        await emit_event(current_user.user_id, "ERROR", {"message": error_msg})
        raise HTTPException(status_code=500, detail=error_msg)

    user_message = request.message
    user_id = current_user.user_id

    try:
        await emit_event(user_id, "USER_MESSAGE", {"message": user_message})

        await emit_event(user_id, "PIPELINE_STEP", {"step": "Extracting & Classifying Facts..."})
        memories_added = await memory_manager.process_user_message(user_id, user_message)
        
        extracted_summary = [f"{m['type']}: {m['memory']}" for m in memories_added]
        await emit_event(user_id, "MEMORY_EXTRACTED", {"facts": extracted_summary})
        await emit_event(user_id, "MEMORY_STORED", {"memories": memories_added})

        await emit_event(user_id, "PIPELINE_STEP", {"step": "Retrieving context across layers..."})
        context_str = memory_manager.get_context_for_llm(user_id, user_message)
        
        semantic_mems = db_manager.search_memories(user_id, user_message)
        await emit_event(user_id, "MEMORY_RETRIEVED", {"memories": [{"type": m['type'], "memory": m['content']} for m in semantic_mems]})

        system_prompt = f"You are a helpful AI assistant. Use the following memory context to personalize your response:\n\n{context_str}"
        
        await emit_event(user_id, "PROMPT_CREATED", {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "full_messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        })

        await emit_event(user_id, "PIPELINE_STEP", {"step": "Calling OpenAI..."})
        assistant_response = await llm_service.get_chat_response(system_prompt, user_message)
        
        memory_manager.add_to_short_term(user_id, "assistant", assistant_response)
        
        await emit_event(user_id, "LLM_RESPONSE", {"response": assistant_response})

        return {"response": assistant_response}

    except Exception as e:
        import traceback
        traceback.print_exc()
        await emit_event(user_id, "ERROR", {"message": str(e)})
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories")
async def get_memories(current_user: TokenData = Depends(get_current_user)):
    return memory_manager.get_all_memories(current_user.user_id)

@app.delete("/memories")
async def delete_memories(current_user: TokenData = Depends(get_current_user)):
    memory_manager.clear_all(current_user.user_id)
    return {"message": f"Memory cleared for {current_user.username}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

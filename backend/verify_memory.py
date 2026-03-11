import asyncio
import os
from dotenv import load_dotenv
from database import DatabaseManager
from llm_service import LLMService
from memory_manager import MemoryManager

load_dotenv()

async def test_modular_memory():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("API Key not found")
        return

    db = DatabaseManager(api_key)
    llm = LLMService(api_key)
    memory = MemoryManager(db, llm)

    user_a = "user_alpha"
    user_b = "user_beta"

    print(f"--- Testing for {user_a} ---")
    # Alice info
    await memory.process_user_message(user_a, "My name is Alice and I love hiking.")
    await memory.process_user_message(user_a, "I live in San Francisco.")
    # Duplicate Alice info (should be skipped)
    await memory.process_user_message(user_a, "I am Alice and I really enjoy hiking.")
    # Low importance info (should be skipped)
    await memory.process_user_message(user_a, "I just blinked my eyes.")
    
    print(f"--- Testing for {user_b} ---")
    await memory.process_user_message(user_b, "I am Bob and I am a backend developer.")
    await memory.process_user_message(user_b, "I enjoy playing chess.")

    print("\n--- Verifying Separation & Deduplication ---")
    mems_a = memory.get_all_memories(user_a)
    mems_b = memory.get_all_memories(user_b)
    
    print(f"Alice's memories: {[m['memory'] for m in mems_a]}")
    print(f"Bob's memories: {[m['memory'] for m in mems_b]}")

    # Check for deduplication: "love hiking" and "enjoy hiking" are very similar
    alice_texts = [m['memory'].lower() for m in mems_a]
    assert len([t for t in alice_texts if "hiking" in t]) == 1, f"Expected 1 hiking memory, got {len([t for t in alice_texts if 'hiking' in t])}"
    
    # Check for importance filtering: "blinked" should NOT be there
    assert not any("blink" in t for t in alice_texts), "Expected low importance memory to be filtered out"

    print("\n--- Testing Semantic Search ---")
    context_a = memory.get_context_for_llm(user_a, "Where do I live?")
    print(f"Context for Alice (query 'Where do I live?'):\n{context_a}")
    assert "San Francisco" in context_a or "san francisco" in context_a.lower()

    context_b = memory.get_context_for_llm(user_b, "What do I do for work?")
    print(f"Context for Bob (query 'What do I do for work?'):\n{context_b}")
    assert "developer" in context_b.lower()

    print("\nVerification successful!")
    db.close()

if __name__ == "__main__":
    asyncio.run(test_modular_memory())

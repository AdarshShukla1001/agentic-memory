import json
from openai import OpenAI
from typing import List, Dict, Any

class LLMService:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    async def extract_memories(self, text: str) -> List[Dict[str, str]]:
        prompt = f"""
        Analyze the user's message: '{text}' and extract significant pieces of information for long-term memory.
        
        Classify each piece into one of these strict categories:
        - FACTUAL: Concrete, static data about the user (e.g., name, current location, job title, birthday, family members). These change very rarely.
        - EPISODIC: Specific events, experiences, or actions that happened at a point in time (e.g., "I just ate a pizza", "I worked on the backend today", "I met Sarah yesterday").
        - SEMANTIC: Beliefs, opinions, general preferences, or distilled concepts (e.g., "I love Italian food", "I think AI will change the world", "I prefer dark mode UI", "Coding is like writing poetry").

        Guidelines:
        1. Be concise. Extract only the essence.
        2. Assign an 'importance' score from 1-10 (1: trivial/fleeting, 10: life-changing/core identity).
        3. Only extract information that is useful for future personalization or context.

        Return a JSON object:
        {{
            "memories": [
                {{
                    "type": "FACTUAL|EPISODIC|SEMANTIC",
                    "content": "concise memory string",
                    "importance": 5
                }}
            ]
        }}
        If no significant information is found, return {{"memories": []}}.
        Return ONLY valid JSON.
        """
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are an expert memory architect specializing in human-AI interaction context."},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        try:
            data = json.loads(response.choices[0].message.content)
            return data.get("memories", [])
        except Exception as e:
            print(f"Extraction error: {e}")
            return []

    async def get_chat_response(self, system_prompt: str, user_message: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        return response.choices[0].message.content

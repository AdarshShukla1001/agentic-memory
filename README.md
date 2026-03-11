# Agentic Memory System

A sophisticated, multi-layered memory system for AI agents, featuring private user-scoped storage, semantic deduplication, and a beautiful glassmorphic control center.

 

## 🌟 Key Features

- **4-Layer Memory Architecture**:
  - **Short-Term**: Immediate conversational context.
  - **Factual**: Long-term storage of immutable user facts.
  - **Episodic**: Time-bound memories of past interactions.
  - **Semantic**: Opinions, beliefs, and general preferences.
- **Smart Extraction**: Uses LLM-powered pipelines to extract and categorize memories automatically.
- **Semantic Deduplication**: Prevents storage of redundant information using vector similarity checks.
- **Importance Filtering**: Automatically filters out "noise" based on assigned importance scores.
- **Multi-User Security**: JWT-based authentication ensuring each user's memory is private and isolated.
- **Real-time Pipeline Visualization**: Watch the memory extraction and retrieval process in real-time.

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API Key

### Running with Docker (Recommended)

The easiest way to run the entire stack is using Docker Compose:

```bash
docker-compose up -d --build
```

Access the UI at `http://localhost`.

### Manual Setup

#### Backend

1. Navigate to `backend/`.
2. Install dependencies: `pip install -r requirements.txt`.
3. Set your environment variables in `.env`:
   ```env
   OPENAI_API_KEY=your_key
   JWT_SECRET=your_secret
   ```
4. Start the server: `python main.py`.

#### Frontend

1. Navigate to `frontend/`.
2. Install dependencies: `npm install`.
3. Start the development server: `npm run dev`.
4. Access the UI at `http://localhost:5173`.

## 🛠 Tech Stack

- **Backend**: FastAPI, OpenAI API, ChromaDB (Vector Store), SQLite (Relational Store), Bcrypt (Security), JWT (Auth).
- **Frontend**: Vite, React, Lucide Icons, Vanilla CSS (Glassmorphism).
- **Deployment**: Docker, Docker Compose, Nginx.

---

Built with ❤️ by Antigravity.

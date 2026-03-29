# Proofdesk

AI-powered compliance questionnaire automation workbench. Upload your knowledge base, parse vendor questionnaires, and get draft answers with citations — then review, approve, and export.

**Comparable to**: Responsive, Loopio, Conveyor — built for the China market.

---

## What it does

```
KB documents → Parse questionnaire → AI drafts answers (with citations) → Human review → Export / Fill template
```

1. **Knowledge Base** — Upload PDF, DOCX, TXT, PPTX, HTML, MD files per project
2. **Questionnaire Workbench** — Upload `.xlsx` or `.txt` questionnaire, auto-answer all questions via RAG
3. **Review** — Edit answers, approve, flag issues, regenerate individual questions
4. **Export** — Download a summary Excel, or fill answers back into the original questionnaire template
5. **Answer Library** — Save approved answers for reuse across projects

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11 |
| Database | PostgreSQL + pgvector (async via asyncpg) |
| Retrieval | BM25 + vector hybrid search + RRF reranking |
| Embedding | Alibaba DashScope `text-embedding-v4` (1024-dim) |
| Reranker | Alibaba `gte-rerank` |
| LLM | OpenAI-compatible API |
| Frontend | React + TypeScript + Vite |
| UI | Tailwind CSS v3 + lucide-react + Inter font |

---

## Project Structure

```
proofdesk/
├── backend/
│   ├── api/              # FastAPI routers
│   │   ├── auth.py       # JWT login
│   │   ├── kb.py         # Document upload & management
│   │   ├── questionnaire.py  # Parse & answer questionnaires (SSE streaming)
│   │   ├── projects.py   # Project CRUD
│   │   ├── library.py    # Answer library
│   │   └── export.py     # Excel export & fill-template
│   ├── services/
│   │   ├── ingestion.py      # PDF/DOCX parsing, chunking, embedding
│   │   ├── retrieval.py      # Hybrid BM25 + vector + rerank
│   │   ├── generation.py     # LLM answer generation + confidence scoring
│   │   └── questionnaire_parser.py  # Excel/TXT questionnaire parsing
│   ├── models.py         # SQLAlchemy ORM models
│   ├── database.py       # Async DB connection
│   ├── config.py         # Pydantic settings
│   ├── main.py           # FastAPI app entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Main layout (header, sidebar, routing)
│   │   └── components/
│   │       ├── WorkbenchPanel.tsx  # Question cards, answer editing, SSE
│   │       ├── KBPanel.tsx         # Document upload with streaming progress
│   │       ├── LibraryPanel.tsx    # Answer library browser
│   │       ├── LoginPage.tsx       # Auth page
│   │       └── Modal.tsx           # Alert/confirm dialogs
│   ├── tailwind.config.js
│   └── package.json
└── docs/
```

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ with `pgvector` extension
- Node.js 18+
- Alibaba DashScope API key (embedding + reranking)
- OpenAI-compatible LLM endpoint

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/proofdesk
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
DASHSCOPE_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-v4
RERANKER_MODEL=gte-rerank
EMBED_DIM=1024
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-password
SECRET_KEY=your-jwt-secret
```

Initialize database:

```bash
# Create the database
psql -U postgres -c "CREATE DATABASE proofdesk;"
psql -U postgres -d proofdesk -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Run migrations (SQLAlchemy creates tables on startup)
python main.py
```

Start the server:

```bash
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App runs at `http://localhost:5173`, API at `http://localhost:8000`.

---

## Configuration

| Variable | Description |
|----------|-------------|
| `POSTGRES_DSN` | PostgreSQL connection string (asyncpg driver) |
| `OPENAI_API_KEY` | API key for LLM |
| `OPENAI_BASE_URL` | LLM endpoint (supports any OpenAI-compatible API) |
| `OPENAI_MODEL` | Model name |
| `DASHSCOPE_API_KEY` | Alibaba DashScope key (embedding + reranking) |
| `EMBEDDING_MODEL` | DashScope embedding model (default: `text-embedding-v4`) |
| `RERANKER_MODEL` | Reranker model (default: `gte-rerank`) |
| `EMBED_DIM` | Embedding dimension (default: `1024`) |
| `ADMIN_USERNAME` | Login username |
| `ADMIN_PASSWORD` | Login password |
| `SECRET_KEY` | JWT signing secret |

---

## Key Design Decisions

### Retrieval Pipeline

Hybrid search combining BM25 (keyword) + pgvector (semantic) with Reciprocal Rank Fusion (RRF), then Alibaba `gte-rerank` cross-encoder reranking. This handles both exact terminology matches and semantic similarity.

### Confidence Scoring

Multi-signal confidence for each generated answer:
- **50%** — top rerank score × 2 (gte-rerank scores ≈ 0.4–0.6 for strong matches)
- **20%** — mean top-3 rerank scores × 2
- **30%** — hedge detection (0 if answer contains "not specified", "not found", etc.)

Answers above 75% show as **Confident**, below as **Needs Review**.

### Questionnaire Parsing

LLM-assisted Excel parsing — the model identifies which column contains questions and which (if any) contains answer cells, handling diverse real-world questionnaire formats.

### Fill Template Export

Answers are written back into the original uploaded `.xlsx` file at the exact cells the parser identified — preserving formatting, formulas, and multi-sheet structure.

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

---

## API Reference

Base URL: `http://localhost:8000/api`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Get JWT token |
| GET/POST/DELETE | `/projects/` | Project management |
| POST | `/kb/upload-stream` | Upload document (SSE progress) |
| GET/DELETE | `/kb/docs` | List / delete documents |
| POST | `/questionnaire/parse` | Parse questionnaire file |
| GET | `/questionnaire/{qid}/answer-all-stream` | Auto-answer all (SSE) |
| GET | `/questionnaire/{qid}/answers` | Get answers |
| PATCH | `/questionnaire/{qid}/answers/{aid}` | Edit / approve / flag answer |
| GET | `/questionnaire/{qid}/regen-stream/{question_id}` | Regenerate single answer (SSE) |
| GET | `/questionnaire/{qid}/export` | Export summary Excel |
| GET | `/questionnaire/{qid}/export-filled` | Export filled template |
| GET/POST/DELETE | `/library/` | Answer library management |

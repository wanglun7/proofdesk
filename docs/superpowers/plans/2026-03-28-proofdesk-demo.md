# Proofdesk Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a demo of security questionnaire automation: upload KB docs → upload questionnaire → AI auto-answers each question with citations → human review → export Excel.

**Architecture:** FastAPI backend with pgvector for document chunks + vector search, Alibaba embedding/reranker for retrieval quality, OpenAI relay for generation. React frontend with two panels: KB management and questionnaire workbench.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy + asyncpg, pgvector, LlamaIndex (ingestion only), Alibaba dashscope (embedding + reranker), OpenAI relay (generation), openpyxl, React + Vite, TypeScript

---

## Environment

```
POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@localhost:5432/proofdesk
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=<relay key>
OPENAI_BASE_URL=<relay base url>
OPENAI_MODEL=gpt-4o
DASHSCOPE_API_KEY=<alibaba key>
EMBEDDING_MODEL=text-embedding-v3
RERANKER_MODEL=gte-rerank
```

---

## File Map

```
proofdesk/
├── backend/
│   ├── main.py                     # FastAPI app, CORS, routers
│   ├── config.py                   # Settings from env
│   ├── database.py                 # Async SQLAlchemy engine + session
│   ├── models.py                   # ORM: Document, Chunk, Questionnaire, Question, Answer
│   ├── api/
│   │   ├── kb.py                   # POST /kb/upload, GET /kb/documents
│   │   ├── questionnaire.py        # POST /questionnaire/parse, POST /questionnaire/{id}/answer-all, PATCH /answers/{id}
│   │   └── export.py               # GET /questionnaire/{id}/export
│   ├── services/
│   │   ├── ingestion.py            # parse file → chunks → embed → store
│   │   ├── retrieval.py            # pgvector search + alibaba rerank
│   │   └── generation.py          # build prompt → openai → parse {answer, citations}
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── KBPanel.tsx         # Upload docs, list docs
│   │   │   └── WorkbenchPanel.tsx  # Upload questionnaire, show Q+A+citations, export
│   │   └── api.ts                  # typed fetch wrappers
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
└── .env.example
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env`
- Create: `backend/config.py`
- Create: `backend/main.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
pgvector==0.3.6
pydantic-settings==2.5.2
python-multipart==0.0.12
llama-index-core==0.12.0
llama-index-readers-file==0.4.0
dashscope==1.20.0
openai==1.50.0
openpyxl==3.1.5
python-dotenv==1.0.1
python-docx==1.1.2
aiofiles==24.1.0
httpx==0.27.0
```

- [ ] **Step 2: Create config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    postgres_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/proofdesk"
    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    dashscope_api_key: str
    embedding_model: str = "text-embedding-v3"
    reranker_model: str = "gte-rerank"
    embed_dim: int = 1024

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 3: Create `api/__init__.py`, `services/__init__.py`, `tests/__init__.py`**

```bash
mkdir -p backend/api backend/services backend/tests
touch backend/api/__init__.py backend/services/__init__.py backend/tests/__init__.py
```

- [ ] **Step 4: Create stub router files so main.py can import at boot**

```bash
# api/kb.py stub
cat > backend/api/kb.py << 'EOF'
from fastapi import APIRouter
router = APIRouter()
EOF

# api/questionnaire.py stub
cat > backend/api/questionnaire.py << 'EOF'
from fastapi import APIRouter
router = APIRouter()
EOF

# api/export.py stub
cat > backend/api/export.py << 'EOF'
from fastapi import APIRouter
router = APIRouter()
EOF
```

- [ ] **Step 6: Create main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from api.kb import router as kb_router
from api.questionnaire import router as questionnaire_router
from api.export import router as export_router

app = FastAPI(title="Proofdesk")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    await init_db()

app.include_router(kb_router, prefix="/api/kb", tags=["kb"])
app.include_router(questionnaire_router, prefix="/api/questionnaire", tags=["questionnaire"])
app.include_router(export_router, prefix="/api", tags=["export"])
```

- [ ] **Step 7: Install and verify boots**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Expected: "Application startup complete" — Ctrl+C after verify
```

---

## Task 2: Database Schema

**Files:**
- Create: `backend/database.py`
- Create: `backend/models.py`

- [ ] **Step 1: Create database.py**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import settings

engine = create_async_engine(settings.postgres_dsn, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 2: Create models.py**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from database import Base
from config import settings

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(32))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete")

class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    content: Mapped[str] = mapped_column(Text)
    page: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list] = mapped_column(Vector(settings.embed_dim))
    document: Mapped["Document"] = relationship(back_populates="chunks")

class Questionnaire(Base):
    __tablename__ = "questionnaires"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    questions: Mapped[list["Question"]] = relationship(back_populates="questionnaire", cascade="all, delete")

class Question(Base):
    __tablename__ = "questions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questionnaires.id"))
    seq: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    answer: Mapped["Answer"] = relationship(back_populates="question", uselist=False, cascade="all, delete")
    questionnaire: Mapped["Questionnaire"] = relationship(back_populates="questions")

class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), unique=True)
    draft: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSON)  # [{chunk_id, content, source}]
    confidence: Mapped[float | None] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True)
    human_edit: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|generating|done|approved
    question: Mapped["Question"] = relationship(back_populates="answer")
```

- [ ] **Step 3: Verify DB migration**

```bash
cd backend
python -c "import asyncio; from database import init_db; asyncio.run(init_db()); print('OK')"
# Expected: OK (no errors)
```

```bash
docker exec -it security_questionnaire_postgres psql -U postgres -d proofdesk -c "\dt"
# Expected: documents, chunks, questionnaires, questions, answers
```

- [ ] **Step 4: Commit**

```bash
git init && git add backend/
git commit -m "feat: project scaffold + pgvector schema"
```

---

## Task 3: KB Ingestion Service

**Files:**
- Create: `backend/services/ingestion.py`
- Create: `backend/api/kb.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_ingestion.py
import pytest
from services.ingestion import chunk_text

def test_chunk_text_splits_long_text():
    text = "word " * 600  # ~3000 chars
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 600 for c in chunks)  # some slack for word boundaries

def test_chunk_text_short_text():
    text = "short text"
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert chunks == ["short text"]
```

```bash
cd backend && pytest tests/test_ingestion.py -v
# Expected: FAIL (module not found)
```

- [ ] **Step 2: Create services/ingestion.py**

```python
import os, uuid, tempfile
from pathlib import Path
from typing import BinaryIO
import dashscope
from dashscope import TextEmbedding
from sqlalchemy.ext.asyncio import AsyncSession
from models import Document, Chunk
from config import settings

# --- Text extraction ---

def extract_text_from_pdf(path: str) -> list[tuple[int, str]]:
    """Returns list of (page_num, text)"""
    from llama_index.readers.file import PDFReader
    docs = PDFReader().load_data(Path(path))
    return [(i, d.text) for i, d in enumerate(docs)]

def extract_text_from_docx(path: str) -> list[tuple[int, str]]:
    from docx import Document as DocxDoc
    doc = DocxDoc(path)
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [(0, text)]

def extract_text_from_txt(path: str) -> list[tuple[int, str]]:
    return [(0, Path(path).read_text(encoding="utf-8"))]

def extract_text(path: str, file_type: str) -> list[tuple[int, str]]:
    if file_type == "pdf":
        return extract_text_from_pdf(path)
    elif file_type in ("docx", "doc"):
        return extract_text_from_docx(path)
    else:
        return extract_text_from_txt(path)

# --- Chunking ---

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks, i = [], 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += chunk_size - overlap
    return chunks

# --- Embedding ---

def embed_texts(texts: list[str]) -> list[list[float]]:
    dashscope.api_key = settings.dashscope_api_key
    # Alibaba supports batch up to 25
    all_embeddings = []
    for i in range(0, len(texts), 25):
        batch = texts[i:i+25]
        resp = TextEmbedding.call(
            model=settings.embedding_model,
            input=batch,
            dimension=settings.embed_dim,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Embedding API error: {resp.message}")
        all_embeddings.extend([e["embedding"] for e in resp.output["embeddings"]])
    return all_embeddings

# --- Full ingestion pipeline ---

async def ingest_file(file_bytes: bytes, filename: str, db: AsyncSession) -> Document:
    suffix = Path(filename).suffix.lower().lstrip(".")
    with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as f:
        f.write(file_bytes)
        tmp_path = f.name

    try:
        pages = extract_text(tmp_path, suffix)
        doc = Document(filename=filename, file_type=suffix)
        db.add(doc)
        await db.flush()

        all_chunks_text = []
        all_pages = []
        for page_num, page_text in pages:
            for chunk in chunk_text(page_text):
                all_chunks_text.append(chunk)
                all_pages.append(page_num)

        embeddings = embed_texts(all_chunks_text)
        for content, page, emb in zip(all_chunks_text, all_pages, embeddings):
            db.add(Chunk(document_id=doc.id, content=content, page=page, embedding=emb))

        await db.commit()
        await db.refresh(doc)
        return doc
    finally:
        os.unlink(tmp_path)
```

- [ ] **Step 3: Run tests**

```bash
cd backend && pytest tests/test_ingestion.py -v
# Expected: PASS
```

- [ ] **Step 4: Create api/kb.py**

```python
from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Document
from services.ingestion import ingest_file

router = APIRouter()

@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    doc = await ingest_file(content, file.filename, db)
    return {"id": str(doc.id), "filename": doc.filename, "uploaded_at": doc.uploaded_at.isoformat()}

@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.uploaded_at.desc()))
    docs = result.scalars().all()
    return [{"id": str(d.id), "filename": d.filename, "uploaded_at": d.uploaded_at.isoformat()} for d in docs]
```

- [ ] **Step 5: Manual smoke test**

```bash
# Start server
uvicorn main:app --reload --port 8000 &
# Upload a test PDF
curl -X POST http://localhost:8000/api/kb/upload \
  -F "file=@/path/to/any.pdf"
# Expected: {"id": "...", "filename": "..."}
curl http://localhost:8000/api/kb/documents
# Expected: list with 1 doc
```

- [ ] **Step 6: Commit**

```bash
git add backend/services/ingestion.py backend/api/kb.py backend/tests/
git commit -m "feat: KB ingestion — PDF/DOCX/TXT → chunks → alibaba embed → pgvector"
```

---

## Task 4: Retrieval + Rerank Service

**Files:**
- Create: `backend/services/retrieval.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_retrieval.py
import pytest
from unittest.mock import patch, MagicMock
from services.retrieval import cosine_top_k_mock

def test_cosine_top_k_mock_returns_sorted():
    # unit test the sorting logic in isolation
    items = [("a", 0.5), ("b", 0.9), ("c", 0.3)]
    result = cosine_top_k_mock(items, top_k=2)
    assert result[0][1] >= result[1][1]
    assert len(result) == 2
```

```bash
pytest tests/test_retrieval.py -v
# Expected: FAIL
```

- [ ] **Step 2: Create services/retrieval.py**

```python
import dashscope
from dashscope import TextEmbedding
from dashscope.rerank import Rerank
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from config import settings
from models import Chunk, Document

def cosine_top_k_mock(items: list[tuple], top_k: int) -> list[tuple]:
    """Helper for testing — sorts by score desc and returns top_k."""
    return sorted(items, key=lambda x: x[1], reverse=True)[:top_k]

async def retrieve_chunks(query: str, db: AsyncSession, top_k: int = 20) -> list[dict]:
    """Vector similarity search via pgvector."""
    dashscope.api_key = settings.dashscope_api_key
    resp = TextEmbedding.call(
        model=settings.embedding_model,
        input=[query],
        dimension=settings.embed_dim,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Embedding error: {resp.message}")
    qvec = resp.output["embeddings"][0]["embedding"]

    # pgvector cosine similarity — operator <=> is cosine distance (lower = more similar)
    sql = text("""
        SELECT c.id, c.content, c.page, d.filename,
               1 - (c.embedding <=> CAST(:vec AS vector)) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        ORDER BY c.embedding <=> CAST(:vec AS vector)
        LIMIT :k
    """)
    result = await db.execute(sql, {"vec": str(qvec), "k": top_k})
    return [
        {"id": str(r.id), "content": r.content, "page": r.page,
         "source": r.filename, "score": float(r.score)}
        for r in result.fetchall()
    ]

def rerank_chunks(query: str, chunks: list[dict], top_n: int = 4) -> list[dict]:
    """Alibaba reranker — reorders chunks by relevance to query."""
    if not chunks:
        return []
    resp = Rerank.call(
        model=settings.reranker_model,
        query=query,
        documents=[c["content"] for c in chunks],
        top_n=top_n,
        return_documents=False,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Rerank error: {resp.message}")
    reranked = []
    for item in resp.output.results:
        chunk = chunks[item.index]
        chunk["rerank_score"] = item.relevance_score
        reranked.append(chunk)
    return reranked

async def retrieve_and_rerank(query: str, db: AsyncSession, top_n: int = 4) -> list[dict]:
    chunks = await retrieve_chunks(query, db, top_k=20)
    return rerank_chunks(query, chunks, top_n=top_n)
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_retrieval.py -v
# Expected: PASS
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/retrieval.py backend/tests/test_retrieval.py
git commit -m "feat: pgvector retrieval + alibaba rerank"
```

---

## Task 5: Generation Service

**Files:**
- Create: `backend/services/generation.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_generation.py
from services.generation import build_prompt, parse_llm_response

def test_build_prompt_includes_question_and_chunks():
    chunks = [{"content": "We use AES-256 encryption.", "source": "policy.pdf", "page": 1}]
    prompt = build_prompt("How do you encrypt data?", chunks)
    assert "AES-256" in prompt
    assert "How do you encrypt data?" in prompt

def test_parse_llm_response_valid():
    raw = '{"answer": "We use AES-256.", "confidence": 0.9, "citations": [0]}'
    result = parse_llm_response(raw)
    assert result["answer"] == "We use AES-256."
    assert result["confidence"] == 0.9

def test_parse_llm_response_fallback():
    raw = "We use AES-256 encryption for all data at rest."
    result = parse_llm_response(raw)
    assert result["answer"] == raw
    assert result["confidence"] == 0.5
```

```bash
pytest tests/test_generation.py -v
# Expected: FAIL
```

- [ ] **Step 2: Create services/generation.py**

```python
import json
from openai import AsyncOpenAI
from config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

SYSTEM_PROMPT = """You are a security compliance expert. Answer the given security questionnaire question based ONLY on the provided reference documents.

Respond with valid JSON only:
{
  "answer": "<concise answer in Chinese or English matching the question language>",
  "confidence": <float 0.0-1.0>,
  "citations": [<list of reference indices used, 0-based>]
}

If the references don't contain enough information, set confidence below 0.6."""

def build_prompt(question: str, chunks: list[dict]) -> str:
    refs = "\n\n".join(
        f"[{i}] Source: {c['source']} (p.{c['page']})\n{c['content']}"
        for i, c in enumerate(chunks)
    )
    return f"Question: {question}\n\nReferences:\n{refs}"

def parse_llm_response(raw: str) -> dict:
    raw = raw.strip()
    # Try to extract JSON from markdown code blocks
    if "```" in raw:
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        data = json.loads(raw)
        return {
            "answer": data.get("answer", ""),
            "confidence": float(data.get("confidence", 0.5)),
            "citations": data.get("citations", []),
        }
    except (json.JSONDecodeError, ValueError):
        return {"answer": raw, "confidence": 0.5, "citations": []}

async def generate_answer(question: str, chunks: list[dict]) -> dict:
    """Returns {answer, confidence, citations (as list of chunk dicts)}"""
    if not chunks:
        return {"answer": "No relevant information found in knowledge base.", "confidence": 0.0, "citations": []}

    user_prompt = build_prompt(question, chunks)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    parsed = parse_llm_response(raw)

    # Map citation indices back to chunk objects
    cited_chunks = [chunks[i] for i in parsed["citations"] if i < len(chunks)]
    return {
        "answer": parsed["answer"],
        "confidence": parsed["confidence"],
        "citations": [{"source": c["source"], "page": c["page"], "excerpt": c["content"][:200]} for c in cited_chunks],
    }
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_generation.py -v
# Expected: PASS
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/generation.py backend/tests/test_generation.py
git commit -m "feat: generation service with citation parsing"
```

---

## Task 6: Questionnaire API

**Files:**
- Create: `backend/services/questionnaire_parser.py`
- Create: `backend/api/questionnaire.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_questionnaire_parser.py
import openpyxl, tempfile, os
from services.questionnaire_parser import parse_excel_questionnaire

def test_parse_excel_first_column_as_questions():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Question", "Answer"])  # header
    ws.append(["How do you handle data encryption?", ""])
    ws.append(["What is your incident response process?", ""])
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        wb.save(f.name)
        path = f.name
    try:
        questions = parse_excel_questionnaire(path)
        assert len(questions) == 2
        assert questions[0] == "How do you handle data encryption?"
    finally:
        os.unlink(path)
```

```bash
pytest tests/test_questionnaire_parser.py -v
# Expected: FAIL
```

- [ ] **Step 2: Create services/questionnaire_parser.py**

```python
import openpyxl
from pathlib import Path

def parse_excel_questionnaire(path: str) -> list[str]:
    """Extract questions from first non-empty column, skip header row."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    questions = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # skip header
        if row and row[0] and str(row[0]).strip():
            questions.append(str(row[0]).strip())
    return questions

def parse_questionnaire_file(path: str, filename: str) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return parse_excel_questionnaire(path)
    elif suffix == ".txt":
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        return [l.strip() for l in lines if l.strip()]
    else:
        raise ValueError(f"Unsupported questionnaire format: {suffix}")
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_questionnaire_parser.py -v
# Expected: PASS
```

- [ ] **Step 4: Create api/questionnaire.py**

```python
import os, tempfile, asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Questionnaire, Question, Answer
from services.questionnaire_parser import parse_questionnaire_file
from services.retrieval import retrieve_and_rerank
from services.generation import generate_answer

router = APIRouter()

@router.post("/parse")
async def parse_questionnaire(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        questions_text = parse_questionnaire_file(tmp_path, file.filename)
    finally:
        os.unlink(tmp_path)

    q = Questionnaire(filename=file.filename)
    db.add(q)
    await db.flush()
    for i, qt in enumerate(questions_text):
        question = Question(questionnaire_id=q.id, seq=i, question_text=qt)
        db.add(question)
        await db.flush()
        db.add(Answer(question_id=question.id))
    await db.commit()
    await db.refresh(q)

    result = await db.execute(select(Question).where(Question.questionnaire_id == q.id).order_by(Question.seq))
    qs = result.scalars().all()
    return {
        "id": str(q.id),
        "filename": q.filename,
        "questions": [{"id": str(x.id), "seq": x.seq, "text": x.question_text} for x in qs]
    }

@router.post("/{qid}/answer-all")
async def answer_all(qid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Question).where(Question.questionnaire_id == qid).order_by(Question.seq)
    )
    questions = result.scalars().all()
    if not questions:
        raise HTTPException(404, "Questionnaire not found")

    async def process_one(q: Question):
        chunks = await retrieve_and_rerank(q.question_text, db)
        gen = await generate_answer(q.question_text, chunks)
        ans_result = await db.execute(select(Answer).where(Answer.question_id == q.id))
        ans = ans_result.scalar_one_or_none()
        if ans:
            ans.draft = gen["answer"]
            ans.citations = gen["citations"]
            ans.confidence = gen["confidence"]
            ans.needs_review = gen["confidence"] < 0.75
            ans.status = "done"

    for q in questions:
        await process_one(q)
    await db.commit()
    return {"status": "done", "count": len(questions)}

@router.get("/{qid}/answers")
async def get_answers(qid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Question, Answer)
        .join(Answer, Answer.question_id == Question.id)
        .where(Question.questionnaire_id == qid)
        .order_by(Question.seq)
    )
    rows = result.all()
    return [
        {
            "question_id": str(q.id),
            "seq": q.seq,
            "question": q.question_text,
            "answer_id": str(a.id),
            "draft": a.draft,
            "human_edit": a.human_edit,
            "citations": a.citations,
            "confidence": a.confidence,
            "needs_review": a.needs_review,
            "status": a.status,
        }
        for q, a in rows
    ]

class AnswerPatch(BaseModel):
    human_edit: str | None = None
    status: str | None = None

@router.patch("/answers/{aid}")
async def patch_answer(aid: str, body: AnswerPatch, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Answer).where(Answer.id == aid))
    ans = result.scalar_one_or_none()
    if not ans:
        raise HTTPException(404, "Answer not found")
    if body.human_edit is not None:
        ans.human_edit = body.human_edit
        ans.status = "approved"
    if body.status is not None:
        ans.status = body.status
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 5: Commit**

```bash
git add backend/services/questionnaire_parser.py backend/api/questionnaire.py backend/tests/
git commit -m "feat: questionnaire parse + auto-answer-all + review patch"
```

---

## Task 7: Export API

**Files:**
- Create: `backend/api/export.py`

- [ ] **Step 1: Create api/export.py**

```python
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Questionnaire, Question, Answer

router = APIRouter()

@router.get("/questionnaire/{qid}/export")
async def export_questionnaire(qid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Questionnaire).where(Questionnaire.id == qid)
    )
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Not found")

    rows_result = await db.execute(
        select(Question, Answer)
        .join(Answer, Answer.question_id == Question.id)
        .where(Question.questionnaire_id == qid)
        .order_by(Question.seq)
    )
    rows = rows_result.all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Answers"

    # Header
    headers = ["#", "Question", "Answer", "Confidence", "Status", "Sources"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E1F2")

    for row_idx, (question, answer) in enumerate(rows, 2):
        final_answer = answer.human_edit or answer.draft or ""
        sources = "; ".join(
            f"{c['source']} p.{c['page']}" for c in (answer.citations or [])
        )
        ws.cell(row=row_idx, column=1, value=question.seq + 1)
        ws.cell(row=row_idx, column=2, value=question.question_text)
        ws.cell(row=row_idx, column=3, value=final_answer).alignment = Alignment(wrap_text=True)
        ws.cell(row=row_idx, column=4, value=round(answer.confidence or 0, 2))
        ws.cell(row=row_idx, column=5, value=answer.status)
        ws.cell(row=row_idx, column=6, value=sources)

    ws.column_dimensions["B"].width = 50
    ws.column_dimensions["C"].width = 70

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = q.filename.replace(".xlsx", "") + "_answered.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
```

- [ ] **Step 2: Smoke test export**

```bash
curl -o out.xlsx "http://localhost:8000/api/questionnaire/<qid>/export"
# Open out.xlsx — verify columns: #, Question, Answer, Confidence, Status, Sources
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/export.py
git commit -m "feat: export answered questionnaire to xlsx"
```

---

## Task 8: Frontend

**Files:**
- Create: `frontend/` (Vite + React + TypeScript, minimal)

- [ ] **Step 1: Scaffold frontend**

```bash
cd /Users/lun/Desktop/manifex/proofdesk
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install axios
```

- [ ] **Step 2: Create frontend/src/api.ts**

```typescript
import axios from 'axios'
const BASE = 'http://localhost:8000/api'
const api = axios.create({ baseURL: BASE })

export const uploadDoc = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/kb/upload', fd)
}
export const listDocs = () => api.get('/kb/documents')

export const parseQuestionnaire = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/questionnaire/parse', fd)
}
export const answerAll = (qid: string) => api.post(`/questionnaire/${qid}/answer-all`)
export const getAnswers = (qid: string) => api.get(`/questionnaire/${qid}/answers`)
export const patchAnswer = (aid: string, data: { human_edit?: string; status?: string }) =>
  api.patch(`/questionnaire/answers/${aid}`, data)
export const exportUrl = (qid: string) => `${BASE}/questionnaire/${qid}/export`
```

- [ ] **Step 3: Replace frontend/src/App.tsx**

```tsx
import { useState } from 'react'
import KBPanel from './components/KBPanel'
import WorkbenchPanel from './components/WorkbenchPanel'
import './App.css'

export default function App() {
  const [activeQid, setActiveQid] = useState<string | null>(null)
  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'system-ui' }}>
      <div style={{ width: 320, borderRight: '1px solid #e5e7eb', padding: 16, overflowY: 'auto' }}>
        <h2 style={{ margin: '0 0 16px' }}>Knowledge Base</h2>
        <KBPanel />
      </div>
      <div style={{ flex: 1, padding: 16, overflowY: 'auto' }}>
        <h2 style={{ margin: '0 0 16px' }}>Questionnaire Workbench</h2>
        <WorkbenchPanel onQidChange={setActiveQid} activeQid={activeQid} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create frontend/src/components/KBPanel.tsx**

```tsx
import { useEffect, useState, useRef } from 'react'
import { uploadDoc, listDocs } from '../api'

interface Doc { id: string; filename: string; uploaded_at: string }

export default function KBPanel() {
  const [docs, setDocs] = useState<Doc[]>([])
  const [uploading, setUploading] = useState(false)
  const ref = useRef<HTMLInputElement>(null)

  const load = async () => {
    const r = await listDocs(); setDocs(r.data)
  }
  useEffect(() => { load() }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return
    setUploading(true)
    try { await uploadDoc(file); await load() }
    finally { setUploading(false) }
  }

  return (
    <div>
      <input ref={ref} type="file" accept=".pdf,.docx,.txt" style={{ display: 'none' }} onChange={handleUpload} />
      <button onClick={() => ref.current?.click()} disabled={uploading}
        style={{ width: '100%', padding: '8px 0', marginBottom: 12, cursor: 'pointer' }}>
        {uploading ? 'Uploading…' : '+ Upload Document'}
      </button>
      {docs.map(d => (
        <div key={d.id} style={{ padding: '6px 8px', marginBottom: 4, background: '#f9fafb', borderRadius: 6, fontSize: 13 }}>
          📄 {d.filename}
          <div style={{ color: '#9ca3af', fontSize: 11 }}>{new Date(d.uploaded_at).toLocaleString()}</div>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Create frontend/src/components/WorkbenchPanel.tsx**

```tsx
import { useRef, useState } from 'react'
import { parseQuestionnaire, answerAll, getAnswers, patchAnswer, exportUrl } from '../api'

interface QItem {
  question_id: string; seq: number; question: string
  answer_id: string; draft: string | null; human_edit: string | null
  citations: { source: string; page: number; excerpt: string }[] | null
  confidence: number | null; needs_review: boolean; status: string
}

export default function WorkbenchPanel({ onQidChange, activeQid }: { onQidChange: (id: string) => void; activeQid: string | null }) {
  const [items, setItems] = useState<QItem[]>([])
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const ref = useRef<HTMLInputElement>(null)

  const loadAnswers = async (qid: string) => {
    const r = await getAnswers(qid); setItems(r.data)
  }

  const handleParse = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return
    setLoading(true)
    try {
      const r = await parseQuestionnaire(file)
      const qid = r.data.id; onQidChange(qid)
      await loadAnswers(qid)
    } finally { setLoading(false) }
  }

  const handleAnswerAll = async () => {
    if (!activeQid) return
    setRunning(true)
    try { await answerAll(activeQid); await loadAnswers(activeQid) }
    finally { setRunning(false) }
  }

  const handleEdit = async (item: QItem, val: string) => {
    await patchAnswer(item.answer_id, { human_edit: val })
    setItems(prev => prev.map(x => x.answer_id === item.answer_id ? { ...x, human_edit: val, status: 'approved' } : x))
  }

  const badge = (item: QItem) => {
    if (item.status === 'approved') return { label: '✓ Approved', color: '#d1fae5' }
    if (item.needs_review) return { label: '⚠ Review', color: '#fef3c7' }
    return { label: '• Generated', color: '#e0e7ff' }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input ref={ref} type="file" accept=".xlsx,.txt" style={{ display: 'none' }} onChange={handleParse} />
        <button onClick={() => ref.current?.click()} disabled={loading} style={{ padding: '8px 16px' }}>
          {loading ? 'Parsing…' : 'Upload Questionnaire'}
        </button>
        {activeQid && (
          <>
            <button onClick={handleAnswerAll} disabled={running} style={{ padding: '8px 16px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
              {running ? 'Answering…' : '⚡ Auto-Answer All'}
            </button>
            <a href={exportUrl(activeQid)} download style={{ padding: '8px 16px', background: '#10b981', color: '#fff', borderRadius: 6, textDecoration: 'none' }}>
              ↓ Export Excel
            </a>
          </>
        )}
      </div>

      {items.map(item => {
        const b = badge(item)
        const displayAnswer = item.human_edit ?? item.draft ?? ''
        return (
          <div key={item.answer_id} style={{ marginBottom: 16, border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
            <div style={{ background: '#f9fafb', padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>{item.seq + 1}. {item.question}</span>
              <span style={{ background: b.color, padding: '2px 8px', borderRadius: 12, fontSize: 12 }}>{b.label}</span>
            </div>
            <div style={{ padding: 12 }}>
              <textarea
                defaultValue={displayAnswer}
                onBlur={e => handleEdit(item, e.target.value)}
                rows={3}
                style={{ width: '100%', boxSizing: 'border-box', border: '1px solid #d1d5db', borderRadius: 6, padding: 8, fontSize: 13, resize: 'vertical' }}
              />
              {item.citations && item.citations.length > 0 && (
                <details style={{ marginTop: 6, fontSize: 12, color: '#6b7280' }}>
                  <summary style={{ cursor: 'pointer' }}>📎 {item.citations.length} source(s) — confidence {Math.round((item.confidence ?? 0) * 100)}%</summary>
                  {item.citations.map((c, i) => (
                    <div key={i} style={{ marginTop: 4, padding: '4px 8px', background: '#f3f4f6', borderRadius: 4 }}>
                      <strong>{c.source}</strong> p.{c.page}<br />
                      <span>{c.excerpt}</span>
                    </div>
                  ))}
                </details>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 6: Verify frontend builds**

```bash
cd frontend && npm run build
# Expected: dist/ folder created, no errors
npm run dev
# Open http://localhost:5173
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: React frontend — KB panel + questionnaire workbench"
```

---

## Task 9: End-to-End Smoke Test

- [ ] **Step 1: Start all services**

```bash
# Terminal 1
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

- [ ] **Step 2: Run full demo flow**

```
1. Open http://localhost:5173
2. Upload 1-2 security policy PDFs to KB panel
3. Upload a .xlsx questionnaire (first column = questions, header row)
4. Click "Auto-Answer All" — wait for completion
5. Verify: each question shows a draft answer + citations
6. Edit one answer manually — verify status changes to "Approved"
7. Click "Export Excel" — verify download contains all answers
```

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat: proofdesk demo complete — KB ingestion + questionnaire auto-answer + export"
```

---

## Quick Reference

| Service | URL |
|---------|-----|
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Frontend | http://localhost:5173 |
| pgvector | localhost:5432 (db: proofdesk) |

**Env vars needed:**
- `OPENAI_API_KEY` + `OPENAI_BASE_URL` (your relay)
- `DASHSCOPE_API_KEY` (Alibaba)

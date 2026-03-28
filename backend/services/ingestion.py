import os
import tempfile
from pathlib import Path

import dashscope
from dashscope import TextEmbedding
from sqlalchemy.ext.asyncio import AsyncSession

from models import Document, Chunk
from config import settings


# --- Text extraction ---

def extract_text_from_pdf(path: str) -> list[tuple[int, str]]:
    """Returns list of (page_num, text)."""
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
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += chunk_size - overlap
    return chunks


# --- Embedding ---

def embed_texts(texts: list[str]) -> list[list[float]]:
    dashscope.api_key = settings.dashscope_api_key
    all_embeddings = []
    # Alibaba supports batch up to 25
    for i in range(0, len(texts), 25):
        batch = texts[i:i + 25]
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

        all_chunks_text: list[str] = []
        all_pages: list[int] = []
        for page_num, page_text in pages:
            for chunk in chunk_text(page_text):
                all_chunks_text.append(chunk)
                all_pages.append(page_num)

        if all_chunks_text:
            embeddings = embed_texts(all_chunks_text)
            for content, page, emb in zip(all_chunks_text, all_pages, embeddings):
                db.add(Chunk(document_id=doc.id, content=content, page=page, embedding=emb))

        await db.commit()
        await db.refresh(doc)
        return doc
    finally:
        os.unlink(tmp_path)

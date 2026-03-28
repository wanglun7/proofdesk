import dashscope
from dashscope import TextEmbedding
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from config import settings


def cosine_top_k_mock(items: list[tuple], top_k: int) -> list[tuple]:
    """Sort by score desc and return top_k. Used in unit tests."""
    return sorted(items, key=lambda x: x[1], reverse=True)[:top_k]


async def retrieve_chunks(query: str, db: AsyncSession, top_k: int = 20) -> list[dict]:
    """Vector similarity search via pgvector cosine distance."""
    dashscope.api_key = settings.dashscope_api_key
    resp = TextEmbedding.call(
        model=settings.embedding_model,
        input=[query],
        dimension=settings.embed_dim,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Embedding error: {resp.message}")
    qvec = resp.output["embeddings"][0]["embedding"]

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
        {
            "id": str(r.id),
            "content": r.content,
            "page": r.page,
            "source": r.filename,
            "score": float(r.score),
        }
        for r in result.fetchall()
    ]


def rerank_chunks(query: str, chunks: list[dict], top_n: int = 4) -> list[dict]:
    """Alibaba reranker — reorders chunks by relevance to query."""
    if not chunks:
        return []
    from dashscope.rerank import Rerank
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
        chunk = dict(chunks[item.index])
        chunk["rerank_score"] = item.relevance_score
        reranked.append(chunk)
    return reranked


async def retrieve_and_rerank(query: str, db: AsyncSession, top_n: int = 4) -> list[dict]:
    chunks = await retrieve_chunks(query, db, top_k=20)
    return rerank_chunks(query, chunks, top_n=top_n)

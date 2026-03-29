import dashscope
from dashscope import TextEmbedding
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from config import settings


def cosine_top_k_mock(items: list[tuple], top_k: int) -> list[tuple]:
    """Sort by score desc and return top_k. Used in unit tests."""
    return sorted(items, key=lambda x: x[1], reverse=True)[:top_k]


def _embed_query(query: str) -> list[float]:
    dashscope.api_key = settings.dashscope_api_key
    resp = TextEmbedding.call(
        model=settings.embedding_model,
        input=[query],
        dimension=settings.embed_dim,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Embedding error: {resp.message}")
    return resp.output["embeddings"][0]["embedding"]


async def retrieve_chunks(
    query: str, db: AsyncSession, top_k: int = 20, project_id: str | None = None
) -> list[dict]:
    """Hybrid BM25 + vector retrieval with Reciprocal Rank Fusion."""
    qvec = _embed_query(query)
    project_filter = "AND d.project_id = CAST(:project_id AS uuid)" if project_id else ""

    # Build hybrid RRF query
    sql = text(f"""
        WITH vector_ranked AS (
            SELECT c.id,
                   ROW_NUMBER() OVER (ORDER BY c.embedding <=> CAST(:vec AS vector)) AS rank
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE 1=1 {project_filter}
            LIMIT :k
        ),
        bm25_ranked AS (
            SELECT c.id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank(
                           to_tsvector('simple', c.content),
                           plainto_tsquery('simple', :query)
                       ) DESC
                   ) AS rank
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE to_tsvector('simple', c.content) @@ plainto_tsquery('simple', :query)
              {project_filter}
            LIMIT :k
        ),
        rrf AS (
            SELECT id, SUM(1.0 / (60.0 + rank)) AS score
            FROM (
                SELECT id, rank FROM vector_ranked
                UNION ALL
                SELECT id, rank FROM bm25_ranked
            ) combined
            GROUP BY id
        )
        SELECT c.id, c.content, c.window_content, c.page, d.filename, r.score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN rrf r ON r.id = c.id
        ORDER BY r.score DESC
        LIMIT :k
    """)

    params = {"vec": str(qvec), "query": query, "k": top_k}
    if project_id:
        params["project_id"] = project_id

    result = await db.execute(sql, params)
    return [
        {
            "id": str(r.id),
            "content": r.window_content or r.content,  # use window for LLM context; fallback to sentence
            "sentence": r.content,                       # original sentence for BM25 scoring reference
            "page": r.page,
            "source": r.filename,
            "score": float(r.score),
        }
        for r in result.fetchall()
    ]


def rerank_chunks(query: str, chunks: list[dict], top_n: int = 5) -> list[dict]:
    """Alibaba reranker — reorders chunks by relevance to query."""
    if not chunks:
        return []
    from dashscope import TextReRank
    resp = TextReRank.call(
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


async def retrieve_and_rerank(
    query: str, db: AsyncSession, top_n: int = 8, project_id: str | None = None
) -> list[dict]:
    chunks = await retrieve_chunks(query, db, top_k=20, project_id=project_id)
    return rerank_chunks(query, chunks, top_n=top_n)

import json
from openai import AsyncOpenAI
from config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    return _client


SYSTEM_PROMPT = """You are a compliance expert. Answer the given questionnaire question based ONLY on the provided reference documents.

Rules:
- Always answer in the SAME language as the question. English question = English answer. Never switch languages.
- State ONLY facts explicitly written in the references. Do NOT infer, extrapolate, or add information not present verbatim.
- If a specific detail (number, threshold, timeframe, procedure) is not found in the references, say "Not specified in provided documents." Do NOT guess.
- Be specific: quote exact numbers, thresholds, timeframes, and procedures when they appear in the references.
- Never combine information from different references to reach a new conclusion that isn't stated directly.

Respond with valid JSON only:
{
  "answer": "<concise answer>",
  "citations": [<list of reference indices used, 0-based>]
}

If the references don't contain enough information, say so explicitly in the answer."""

DECOMPOSE_PROMPT = """Analyze the following question and determine if it contains multiple independent sub-questions.
If yes, break it into 2-3 focused sub-questions (each answerable independently).
If it's already a single focused question, return it as-is.

Respond with JSON only: {"sub_questions": ["...", "..."]}

Question: {question}"""


async def decompose_question(question: str) -> list[str]:
    """Break a complex multi-part question into focused sub-questions."""
    try:
        response = await get_client().chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": DECOMPOSE_PROMPT.format(question=question)}],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        sub_qs = data.get("sub_questions", [question])
        # Guard: if LLM returns garbage, fall back to original
        if not sub_qs or not isinstance(sub_qs, list):
            return [question]
        return [q for q in sub_qs if isinstance(q, str) and q.strip()]
    except Exception:
        return [question]


def _best_excerpt(question: str, content: str, max_len: int = 500) -> str:
    """Return the most relevant sentence(s) from a chunk based on keyword overlap."""
    import re
    q_words = set(w.lower() for w in re.split(r'\W+', question) if len(w) > 3)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', content) if s.strip()]
    if not sentences:
        return content[:max_len]

    def score(s: str) -> int:
        s_words = set(w.lower() for w in re.split(r'\W+', s))
        return len(q_words & s_words)

    scored = sorted(enumerate(sentences), key=lambda x: score(x[1]), reverse=True)
    top_indices = sorted(i for i, _ in scored[:3])
    excerpt = " … ".join(sentences[i] for i in top_indices)
    return excerpt[:max_len]


def build_prompt(question: str, chunks: list[dict]) -> str:
    refs = "\n\n".join(
        f"[{i}] Source: {c['source']} (p.{c['page']})\n{c['content']}"
        for i, c in enumerate(chunks)
    )
    return f"Question: {question}\n\nReferences:\n{refs}"


def parse_llm_response(raw: str) -> dict:
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1].lstrip("json").strip()
    try:
        data = json.loads(raw)
        return {
            "answer": data.get("answer", ""),
            "citations": data.get("citations", []),
        }
    except (json.JSONDecodeError, ValueError):
        return {"answer": raw, "citations": []}


# Phrases indicating the answer couldn't be grounded in the documents
_HEDGE_PHRASES = [
    "not specified", "not found", "no information", "cannot determine",
    "not mentioned", "not provided", "not available", "not stated",
    "no relevant", "insufficient", "does not contain", "not indicated",
    "unable to find", "not described", "not documented",
]


def compute_confidence(chunks: list[dict], answer: str) -> float:
    """
    Multi-signal confidence (calibrated against gte-rerank score distribution):
      50% — top rerank_score ×2 (gte-rerank strong match ≈ 0.4-0.6, so ×2 maps 0.5→1.0)
      20% — mean top-3 rerank_scores ×2
      30% — 0 if answer contains hedging phrases, else 1
             (higher weight so partial/not-found answers reliably fall below 75%)
    """
    if not chunks:
        return 0.0

    scores = [c.get("rerank_score", 0.0) for c in chunks]
    top_scaled = min(scores[0] * 2.0, 1.0)
    top3_scaled = min(sum(scores[:3]) / min(len(scores), 3) * 2.0, 1.0)
    hedge = any(p in answer.lower() for p in _HEDGE_PHRASES)
    hedge_score = 0.0 if hedge else 1.0

    return round(min(0.5 * top_scaled + 0.2 * top3_scaled + 0.3 * hedge_score, 1.0), 2)


async def generate_answer(question: str, chunks: list[dict]) -> dict:
    """Returns {answer, confidence, citations (list of citation dicts)}."""
    if not chunks:
        return {
            "answer": "No relevant information found in knowledge base.",
            "confidence": 0.0,
            "citations": [],
        }

    user_prompt = build_prompt(question, chunks)
    response = await get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    parsed = parse_llm_response(raw)

    cited_chunks = [chunks[i] for i in parsed["citations"] if i < len(chunks)]
    seen_excerpts: set[str] = set()
    unique_citations = []
    for c in cited_chunks:
        excerpt = _best_excerpt(question, c["content"])
        if excerpt not in seen_excerpts:
            seen_excerpts.add(excerpt)
            unique_citations.append({"source": c["source"], "page": c["page"], "excerpt": excerpt})
    return {
        "answer": parsed["answer"],
        "confidence": compute_confidence(chunks, parsed["answer"]),
        "citations": unique_citations,
    }

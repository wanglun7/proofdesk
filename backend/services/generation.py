import json
from openai import AsyncOpenAI
from config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    return _client

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
    # Strip markdown code fences if present
    if "```" in raw:
        parts = raw.split("```")
        # parts[1] is the content inside the first fence
        if len(parts) >= 2:
            raw = parts[1].lstrip("json").strip()
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

    # Map citation indices back to chunk objects
    cited_chunks = [chunks[i] for i in parsed["citations"] if i < len(chunks)]
    return {
        "answer": parsed["answer"],
        "confidence": parsed["confidence"],
        "citations": [
            {"source": c["source"], "page": c["page"], "excerpt": c["content"][:200]}
            for c in cited_chunks
        ],
    }

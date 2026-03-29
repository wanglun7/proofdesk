"""
eval.py — RAG pipeline evaluation via LLM-as-judge

Usage:
  python eval.py --project-id <uuid> --questionnaire-id <uuid>

Scores each answer on:
  - Faithfulness (0-10): answer grounded in cited chunks, no hallucination
  - Completeness (0-10): all parts of the question addressed
  - Citation Hit Rate: does cited chunk contain answer keywords
"""
import asyncio
import argparse
import json
import re
from sqlalchemy import select
from database import AsyncSessionLocal, init_db
from models import Questionnaire, Question, Answer
from services.generation import get_client
from config import settings


JUDGE_PROMPT = """You are evaluating a RAG system answer for a compliance questionnaire.

Question: {question}

Retrieved context used:
{context}

Generated answer: {answer}

Score the answer on TWO dimensions (0-10 each):

1. FAITHFULNESS: Is every claim in the answer directly supported by the retrieved context? Penalize for any information not present in the context (hallucination). 10 = fully grounded, 0 = mostly hallucinated.

2. COMPLETENESS: Does the answer address all parts of the question? If the question has multiple sub-questions, are all addressed? 10 = fully complete, 0 = major parts missing.

Respond with JSON only:
{{"faithfulness": <int 0-10>, "completeness": <int 0-10>, "notes": "<one sentence>"}}"""


def citation_hit_rate(answer: str, citations: list[dict]) -> float:
    """Fraction of answer keywords found in at least one cited chunk."""
    if not citations:
        return 0.0
    answer_words = set(w.lower() for w in re.split(r'\W+', answer) if len(w) > 4)
    if not answer_words:
        return 1.0
    all_chunk_text = " ".join(c.get("excerpt", "") for c in citations).lower()
    hits = sum(1 for w in answer_words if w in all_chunk_text)
    return hits / len(answer_words)


async def judge_answer(question: str, answer: str, citations: list[dict]) -> dict:
    context = "\n---\n".join(
        f"[{c['source']} p.{c['page']}] {c['excerpt']}" for c in citations
    ) if citations else "(no citations)"

    try:
        response = await get_client().chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": JUDGE_PROMPT.format(
                question=question, context=context, answer=answer
            )}],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        return {"faithfulness": -1, "completeness": -1, "notes": f"judge error: {e}"}


async def run_eval(questionnaire_id: str):
    await init_db()
    async with AsyncSessionLocal() as db:
        # Load questionnaire
        q_res = await db.execute(select(Questionnaire).where(Questionnaire.id == questionnaire_id))
        questionnaire = q_res.scalar_one_or_none()
        if not questionnaire:
            print(f"Questionnaire {questionnaire_id} not found")
            return

        # Load questions + answers
        rows = await db.execute(
            select(Question, Answer)
            .join(Answer, Answer.question_id == Question.id)
            .where(Question.questionnaire_id == questionnaire_id)
            .order_by(Question.seq)
        )
        items = rows.all()

        print(f"\nEvaluating: {questionnaire.filename} ({len(items)} questions)\n")
        print(f"{'Q#':<4} {'Faithfulness':>13} {'Completeness':>13} {'CitHit':>7}  Notes")
        print("-" * 70)

        total_faith = 0
        total_complete = 0
        total_cit_hit = 0
        scored = 0

        for q, a in items:
            answer_text = a.human_edit or a.draft or ""
            if not answer_text or a.status == "pending":
                print(f"{q.seq+1:<4} {'(pending)':<13}")
                continue

            citations = a.citations or []
            scores = await judge_answer(q.question_text, answer_text, citations)
            cit_hit = citation_hit_rate(answer_text, citations)

            faith = scores.get("faithfulness", -1)
            complete = scores.get("completeness", -1)
            notes = scores.get("notes", "")[:60]

            print(f"{q.seq+1:<4} {faith:>13.0f} {complete:>13.0f} {cit_hit:>7.0%}  {notes}")

            if faith >= 0:
                total_faith += faith
                total_complete += complete
                total_cit_hit += cit_hit
                scored += 1

        if scored > 0:
            print("-" * 70)
            print(f"{'AVG':<4} {total_faith/scored:>13.1f} {total_complete/scored:>13.1f} {total_cit_hit/scored:>7.0%}")
            print(f"\nSummary: Faithfulness {total_faith/scored:.1f}/10  "
                  f"Completeness {total_complete/scored:.1f}/10  "
                  f"Citation Hit Rate {total_cit_hit/scored:.0%}")


async def list_questionnaires():
    await init_db()
    async with AsyncSessionLocal() as db:
        from models import Project
        rows = await db.execute(
            select(Questionnaire, Project)
            .join(Project, Project.id == Questionnaire.project_id, isouter=True)
            .order_by(Questionnaire.created_at.desc())
        )
        print(f"\n{'ID':<38} {'Project':<12} {'Filename':<30} {'Created'}")
        print("-" * 90)
        for q, p in rows.all():
            print(f"{str(q.id):<38} {(p.name if p else 'none'):<12} {q.filename:<30} {q.created_at.strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate RAG answer quality")
    parser.add_argument("--questionnaire-id", help="Questionnaire UUID to evaluate")
    parser.add_argument("--list", action="store_true", help="List available questionnaires")
    args = parser.parse_args()

    if args.list:
        asyncio.run(list_questionnaires())
    elif args.questionnaire_id:
        asyncio.run(run_eval(args.questionnaire_id))
    else:
        parser.print_help()

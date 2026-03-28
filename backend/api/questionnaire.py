import os
import tempfile
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

    result = await db.execute(
        select(Question).where(Question.questionnaire_id == q.id).order_by(Question.seq)
    )
    qs = result.scalars().all()
    return {
        "id": str(q.id),
        "filename": q.filename,
        "questions": [{"id": str(x.id), "seq": x.seq, "text": x.question_text} for x in qs],
    }


@router.post("/{qid}/answer-all")
async def answer_all(qid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Question).where(Question.questionnaire_id == qid).order_by(Question.seq)
    )
    questions = result.scalars().all()
    if not questions:
        raise HTTPException(404, "Questionnaire not found")

    for q in questions:
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

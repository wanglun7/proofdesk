from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from database import get_db
from models import AnswerLibraryEntry
from services.retrieval import _embed_query

router = APIRouter()


class LibraryEntryIn(BaseModel):
    question_text: str
    answer_text: str
    source_questionnaire_id: str | None = None


@router.post("/entries")
async def save_entry(body: LibraryEntryIn, db: AsyncSession = Depends(get_db)):
    embedding = _embed_query(body.question_text)
    entry = AnswerLibraryEntry(
        question_text=body.question_text,
        question_embedding=embedding,
        answer_text=body.answer_text,
        source_questionnaire_id=body.source_questionnaire_id or None,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"id": str(entry.id), "created_at": entry.created_at.isoformat()}


@router.get("/entries")
async def list_entries(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AnswerLibraryEntry).order_by(AnswerLibraryEntry.created_at.desc())
    )
    entries = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "question_text": e.question_text[:80],
            "answer_text": e.answer_text[:120],
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]


@router.delete("/entries/{eid}")
async def delete_entry(eid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AnswerLibraryEntry).where(AnswerLibraryEntry.id == eid))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Entry not found")
    await db.delete(entry)
    await db.commit()
    return {"ok": True}

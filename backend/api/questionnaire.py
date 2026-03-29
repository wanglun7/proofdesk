import os
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from database import get_db
from models import Questionnaire, Question, Answer
from services.questionnaire_parser import parse_questionnaire_file_llm
from services.retrieval import retrieve_and_rerank, _embed_query
from services.generation import generate_answer, decompose_question

router = APIRouter()

QUESTIONNAIRE_FILES_DIR = Path(__file__).parent.parent / "questionnaire_files"


async def _check_library(question: str, db: AsyncSession, threshold: float = 0.88) -> dict | None:
    """Check answer library for a semantically similar question."""
    try:
        qvec = _embed_query(question)
    except Exception:
        return None
    sql = text("""
        SELECT id, answer_text, 1 - (question_embedding <=> CAST(:vec AS vector)) AS similarity
        FROM answer_library
        ORDER BY question_embedding <=> CAST(:vec AS vector)
        LIMIT 1
    """)
    row = (await db.execute(sql, {"vec": str(qvec)})).fetchone()
    if row and row.similarity >= threshold:
        return {"answer": row.answer_text, "confidence": 1.0, "citations": [], "from_library": True}
    return None


@router.post("/parse")
async def parse_questionnaire(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        question_dicts = await parse_questionnaire_file_llm(tmp_path, file.filename)
    finally:
        os.unlink(tmp_path)

    q = Questionnaire(filename=file.filename, project_id=project_id or None)
    db.add(q)
    await db.flush()

    # 存储原始 Excel 供回填导出使用
    if suffix in (".xlsx", ".xls"):
        QUESTIONNAIRE_FILES_DIR.mkdir(parents=True, exist_ok=True)
        (QUESTIONNAIRE_FILES_DIR / f"{q.id}.xlsx").write_bytes(content)

    for qd in question_dicts:
        question = Question(
            questionnaire_id=q.id,
            seq=qd["seq"],
            question_text=qd["question_text"],
            section=qd.get("section"),
            answer_cell=qd.get("answer_cell"),
        )
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
        "project_id": str(q.project_id) if q.project_id else None,
        "questions": [{"id": str(x.id), "seq": x.seq, "text": x.question_text} for x in qs],
    }


@router.get("/by-project/{pid}")
async def list_questionnaires_by_project(pid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Questionnaire)
        .where(Questionnaire.project_id == pid)
        .order_by(Questionnaire.created_at.desc())
    )
    questionnaires = result.scalars().all()
    out = []
    for q in questionnaires:
        count_result = await db.execute(
            select(Question).where(Question.questionnaire_id == q.id)
        )
        count = len(count_result.scalars().all())
        out.append({
            "id": str(q.id),
            "filename": q.filename,
            "created_at": q.created_at.isoformat(),
            "question_count": count,
        })
    return out


@router.delete("/{qid}")
async def delete_questionnaire(qid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Questionnaire).where(Questionnaire.id == qid))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Questionnaire not found")
    await db.delete(q)
    await db.commit()

    stored = QUESTIONNAIRE_FILES_DIR / f"{qid}.xlsx"
    if stored.exists():
        stored.unlink()

    return {"ok": True}



@router.get("/{qid}/answer-all-stream")
async def answer_all_stream(qid: str, db: AsyncSession = Depends(get_db)):
    q_result = await db.execute(select(Questionnaire).where(Questionnaire.id == qid))
    questionnaire = q_result.scalar_one_or_none()
    if not questionnaire:
        raise HTTPException(404, "Questionnaire not found")
    project_id = str(questionnaire.project_id) if questionnaire.project_id else None

    result = await db.execute(
        select(Question).where(Question.questionnaire_id == qid).order_by(Question.seq)
    )
    questions = result.scalars().all()
    if not questions:
        raise HTTPException(404, "No questions found")

    async def generate():
        total = len(questions)
        for q in questions:
            yield f"data: {json.dumps({'type': 'answering', 'seq': q.seq, 'total': total})}\n\n"

            try:
                # Check answer library first
                lib_hit = await _check_library(q.question_text, db)
                if lib_hit:
                    gen = lib_hit
                else:
                    # Decompose complex multi-part questions into sub-questions
                    sub_questions = await decompose_question(q.question_text)
                    # Retrieve for each sub-question, deduplicate by chunk id
                    seen_ids: set[str] = set()
                    all_chunks: list[dict] = []
                    for sq in sub_questions:
                        sq_chunks = await retrieve_and_rerank(sq, db, project_id=project_id)
                        for c in sq_chunks:
                            if c["id"] not in seen_ids:
                                seen_ids.add(c["id"])
                                all_chunks.append(c)
                    gen = await generate_answer(q.question_text, all_chunks)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'seq': q.seq, 'error': str(e)})}\n\n"
                continue

            ans_result = await db.execute(select(Answer).where(Answer.question_id == q.id))
            ans = ans_result.scalar_one_or_none()
            if ans:
                ans.draft = gen["answer"]
                ans.citations = gen["citations"]
                ans.confidence = gen["confidence"]
                ans.needs_review = gen["confidence"] < 0.75
                ans.status = "done"
                await db.commit()

            yield f"data: {json.dumps({'type': 'answer', 'seq': q.seq, 'answer_id': str(ans.id), 'draft': gen['answer'], 'citations': gen['citations'], 'confidence': gen['confidence'], 'needs_review': gen['confidence'] < 0.75, 'status': 'done', 'from_library': gen.get('from_library', False)})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'total': total})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/questions/{question_id}/regenerate")
async def regenerate_answer(question_id: str, db: AsyncSession = Depends(get_db)):
    q_result = await db.execute(
        select(Question).where(Question.id == question_id)
    )
    q = q_result.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Question not found")

    qn_result = await db.execute(select(Questionnaire).where(Questionnaire.id == q.questionnaire_id))
    questionnaire = qn_result.scalar_one_or_none()
    project_id = str(questionnaire.project_id) if questionnaire and questionnaire.project_id else None

    async def generate():
        yield f"data: {json.dumps({'type': 'answering', 'seq': q.seq})}\n\n"
        try:
            lib_hit = await _check_library(q.question_text, db)
            if lib_hit:
                gen = lib_hit
            else:
                sub_questions = await decompose_question(q.question_text)
                seen_ids: set[str] = set()
                all_chunks: list[dict] = []
                for sq in sub_questions:
                    sq_chunks = await retrieve_and_rerank(sq, db, project_id=project_id)
                    for c in sq_chunks:
                        if c["id"] not in seen_ids:
                            seen_ids.add(c["id"])
                            all_chunks.append(c)
                gen = await generate_answer(q.question_text, all_chunks)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'seq': q.seq, 'error': str(e)})}\n\n"
            return

        ans_result = await db.execute(select(Answer).where(Answer.question_id == q.id))
        ans = ans_result.scalar_one_or_none()
        if ans:
            ans.draft = gen["answer"]
            ans.citations = gen["citations"]
            ans.confidence = gen["confidence"]
            ans.needs_review = gen["confidence"] < 0.75
            ans.status = "done"
            ans.human_edit = None  # clear previous human edit on regenerate
            await db.commit()

        yield f"data: {json.dumps({'type': 'answer', 'seq': q.seq, 'answer_id': str(ans.id), 'draft': gen['answer'], 'citations': gen['citations'], 'confidence': gen['confidence'], 'needs_review': gen['confidence'] < 0.75, 'status': 'done', 'from_library': gen.get('from_library', False)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
            "flag_reason": a.flag_reason,
        }
        for q, a in rows
    ]


@router.post("/{qid}/approve-all")
async def approve_all(qid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Answer)
        .join(Question, Question.id == Answer.question_id)
        .where(Question.questionnaire_id == qid, Answer.status == "done")
    )
    answers = result.scalars().all()
    for ans in answers:
        ans.status = "approved"
    await db.commit()
    return {"approved": len(answers)}


class AnswerPatch(BaseModel):
    human_edit: str | None = None
    status: str | None = None
    flag_reason: str | None = None


@router.patch("/answers/{aid}")
async def patch_answer(aid: str, body: AnswerPatch, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Answer).where(Answer.id == aid))
    ans = result.scalar_one_or_none()
    if not ans:
        raise HTTPException(404, "Answer not found")
    if body.human_edit is not None:
        ans.human_edit = body.human_edit
        # editing alone does NOT auto-approve — status unchanged
    if body.status is not None:
        ans.status = body.status
        if body.status == "done":
            ans.flag_reason = None  # clear reason when unflagging
    if body.flag_reason is not None:
        ans.flag_reason = body.flag_reason
    await db.commit()
    return {"ok": True}

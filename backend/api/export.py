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
    result = await db.execute(select(Questionnaire).where(Questionnaire.id == qid))
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
        cell = ws.cell(row=row_idx, column=3, value=final_answer)
        cell.alignment = Alignment(wrap_text=True)
        ws.cell(row=row_idx, column=4, value=round(answer.confidence or 0, 2))
        ws.cell(row=row_idx, column=5, value=answer.status)
        ws.cell(row=row_idx, column=6, value=sources)

    ws.column_dimensions["B"].width = 50
    ws.column_dimensions["C"].width = 70

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_filename = q.filename.rsplit(".", 1)[0] + "_answered.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Document
from services.ingestion import ingest_file, ingest_file_stream

router = APIRouter()


@router.post("/upload-stream")
async def upload_document_stream(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    return StreamingResponse(
        ingest_file_stream(content, file.filename, db, project_id=project_id or None),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    doc = await ingest_file(content, file.filename, db, project_id=project_id or None)
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "project_id": str(doc.project_id) if doc.project_id else None,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


@router.get("/documents")
async def list_documents(project_id: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Document).order_by(Document.uploaded_at.desc())
    if project_id:
        q = q.where(Document.project_id == project_id)
    result = await db.execute(q)
    docs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "filename": d.filename,
            "project_id": str(d.project_id) if d.project_id else None,
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in docs
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    await db.delete(doc)
    await db.commit()
    return {"ok": True}

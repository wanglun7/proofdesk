from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Document
from services.ingestion import ingest_file

router = APIRouter()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    doc = await ingest_file(content, file.filename, db)
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.uploaded_at.desc()))
    docs = result.scalars().all()
    return [
        {"id": str(d.id), "filename": d.filename, "uploaded_at": d.uploaded_at.isoformat()}
        for d in docs
    ]

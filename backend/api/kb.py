from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_workspace_member
from api.scoping import get_document_for_workspace, get_project_for_workspace
from auth_utils import AuthContext
from database import get_db
from models import Document, Project
from services.ingestion import ingest_file, ingest_file_stream

router = APIRouter()


@router.post("/upload-stream")
async def upload_document_stream(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_workspace_member),
):
    if not project_id:
        raise HTTPException(400, "project_id is required")
    await get_project_for_workspace(db, project_id, auth.workspace_id)
    content = await file.read()
    return StreamingResponse(
        ingest_file_stream(content, file.filename, db, project_id=project_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_workspace_member),
):
    if not project_id:
        raise HTTPException(400, "project_id is required")
    await get_project_for_workspace(db, project_id, auth.workspace_id)
    content = await file.read()
    doc = await ingest_file(content, file.filename, db, project_id=project_id)
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "project_id": str(doc.project_id),
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


@router.get("/documents")
async def list_documents(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_workspace_member),
):
    if project_id:
        await get_project_for_workspace(db, project_id, auth.workspace_id)

    q = (
        select(Document)
        .join(Project, Project.id == Document.project_id)
        .where(Project.workspace_id == auth.workspace_id)
        .order_by(Document.uploaded_at.desc())
    )
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
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_workspace_member),
):
    doc = await get_document_for_workspace(db, doc_id, auth.workspace_id)
    await db.delete(doc)
    await db.commit()
    return {"ok": True}

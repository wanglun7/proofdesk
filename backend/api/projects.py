from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_workspace_member
from api.scoping import get_project_for_workspace
from auth_utils import AuthContext
from database import get_db
from models import AnswerLibraryEntry, Project, Questionnaire

router = APIRouter()
QUESTIONNAIRE_FILES_DIR = Path(__file__).parent.parent / "questionnaire_files"


class ProjectCreate(BaseModel):
    name: str


@router.post("")
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_workspace_member),
):
    p = Project(name=body.name, workspace_id=auth.workspace_id)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {
        "id": str(p.id),
        "name": p.name,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("")
async def list_projects(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_workspace_member),
):
    result = await db.execute(
        select(Project)
        .where(Project.workspace_id == auth.workspace_id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return [{"id": str(p.id), "name": p.name, "created_at": p.created_at.isoformat()} for p in projects]


@router.delete("/{pid}")
async def delete_project(
    pid: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_workspace_member),
):
    p = await get_project_for_workspace(db, pid, auth.workspace_id)

    qids_result = await db.execute(select(Questionnaire.id).where(Questionnaire.project_id == p.id))
    questionnaire_ids = qids_result.scalars().all()
    if questionnaire_ids:
        await db.execute(
            update(AnswerLibraryEntry)
            .where(AnswerLibraryEntry.source_questionnaire_id.in_(questionnaire_ids))
            .values(source_questionnaire_id=None)
        )

    await db.delete(p)
    await db.commit()

    for questionnaire_id in questionnaire_ids:
        stored = QUESTIONNAIRE_FILES_DIR / f"{questionnaire_id}.xlsx"
        if stored.exists():
            stored.unlink()

    return {"ok": True}

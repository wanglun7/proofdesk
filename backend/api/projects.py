from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Project, Questionnaire

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str


@router.post("")
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    p = Project(name=body.name)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": str(p.id), "name": p.name, "created_at": p.created_at.isoformat()}


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return [{"id": str(p.id), "name": p.name, "created_at": p.created_at.isoformat()} for p in projects]


@router.delete("/{pid}")
async def delete_project(pid: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Project not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}

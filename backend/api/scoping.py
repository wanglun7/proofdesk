from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Answer, Document, Project, Questionnaire, Question


async def get_project_for_workspace(
    db: AsyncSession,
    project_id: str | uuid.UUID,
    workspace_id: str | uuid.UUID,
) -> Project:
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.workspace_id == workspace_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


async def get_document_for_workspace(
    db: AsyncSession,
    document_id: str | uuid.UUID,
    workspace_id: str | uuid.UUID,
) -> Document:
    result = await db.execute(
        select(Document)
        .join(Project, Project.id == Document.project_id)
        .where(Document.id == document_id, Project.workspace_id == workspace_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(404, "Document not found")
    return document


async def get_questionnaire_for_workspace(
    db: AsyncSession,
    questionnaire_id: str | uuid.UUID,
    workspace_id: str | uuid.UUID,
) -> Questionnaire:
    result = await db.execute(
        select(Questionnaire)
        .join(Project, Project.id == Questionnaire.project_id)
        .where(Questionnaire.id == questionnaire_id, Project.workspace_id == workspace_id)
    )
    questionnaire = result.scalar_one_or_none()
    if not questionnaire:
        raise HTTPException(404, "Questionnaire not found")
    return questionnaire


async def get_question_for_workspace(
    db: AsyncSession,
    question_id: str | uuid.UUID,
    workspace_id: str | uuid.UUID,
) -> Question:
    result = await db.execute(
        select(Question)
        .join(Questionnaire, Questionnaire.id == Question.questionnaire_id)
        .join(Project, Project.id == Questionnaire.project_id)
        .where(Question.id == question_id, Project.workspace_id == workspace_id)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(404, "Question not found")
    return question


async def get_answer_for_workspace(
    db: AsyncSession,
    answer_id: str | uuid.UUID,
    workspace_id: str | uuid.UUID,
) -> Answer:
    result = await db.execute(
        select(Answer)
        .join(Question, Question.id == Answer.question_id)
        .join(Questionnaire, Questionnaire.id == Question.questionnaire_id)
        .join(Project, Project.id == Questionnaire.project_id)
        .where(Answer.id == answer_id, Project.workspace_id == workspace_id)
    )
    answer = result.scalar_one_or_none()
    if not answer:
        raise HTTPException(404, "Answer not found")
    return answer

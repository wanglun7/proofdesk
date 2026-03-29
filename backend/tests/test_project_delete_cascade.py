import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal
from models import Answer, AnswerLibraryEntry, Chunk, Document, Project, Question, Questionnaire

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_delete_project_cascades_project_assets_but_preserves_library_reference_slot(
    client,
    workspace_owner,
    monkeypatch,
    deterministic_questionnaire_items,
):
    monkeypatch.setattr(
        "services.ingestion.embed_batch",
        lambda texts: [[0.0] * settings.embed_dim for _ in texts],
    )

    async def fake_parse_questionnaire_file_llm(path: str, filename: str):
        return deterministic_questionnaire_items

    monkeypatch.setattr(
        "api.questionnaire.parse_questionnaire_file_llm",
        fake_parse_questionnaire_file_llm,
    )

    create_project = await client.post(
        "/api/projects",
        headers=workspace_owner["headers"],
        json={"name": "Cascade Project"},
    )
    assert create_project.status_code == 200, create_project.text
    project_id = create_project.json()["id"]

    upload_doc = await client.post(
        "/api/kb/upload",
        headers=workspace_owner["headers"],
        data={"project_id": project_id},
        files={
            "file": (
                "manual.docx",
                (ROOT / "test_kb" / "test-kb-extracts" / "hr-manual" / "hr-manual-master" / "docx" / "manual.docx").read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_doc.status_code == 200, upload_doc.text
    document_id = upload_doc.json()["id"]

    parse_questionnaire = await client.post(
        "/api/questionnaire/parse",
        headers=workspace_owner["headers"],
        data={"project_id": project_id},
        files={
            "file": (
                "test-questionnaire.xlsx",
                (ROOT / "test_kb" / "test-questionnaire.xlsx").read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert parse_questionnaire.status_code == 200, parse_questionnaire.text
    questionnaire_id = parse_questionnaire.json()["id"]

    entry_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(
            AnswerLibraryEntry(
                id=entry_id,
                workspace_id=workspace_owner["workspace_id"],
                question_text=deterministic_questionnaire_items[0]["question_text"],
                question_embedding=[0.0] * settings.embed_dim,
                answer_text="Library answer",
                source_questionnaire_id=questionnaire_id,
            )
        )
        await db.commit()

    delete_project = await client.delete(
        f"/api/projects/{project_id}",
        headers=workspace_owner["headers"],
    )
    assert delete_project.status_code == 200, delete_project.text

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        questionnaire = await db.get(Questionnaire, questionnaire_id)
        document = await db.get(Document, document_id)
        questions = (
            await db.execute(select(Question).where(Question.questionnaire_id == questionnaire_id))
        ).scalars().all()
        answers = (
            await db.execute(select(Answer).join(Question).where(Question.questionnaire_id == questionnaire_id))
        ).scalars().all()
        chunks = (
            await db.execute(select(Chunk).where(Chunk.document_id == document_id))
        ).scalars().all()
        library_entry = await db.get(AnswerLibraryEntry, entry_id)

    assert project is None
    assert questionnaire is None
    assert document is None
    assert questions == []
    assert answers == []
    assert chunks == []
    assert library_entry is not None
    assert library_entry.source_questionnaire_id is None

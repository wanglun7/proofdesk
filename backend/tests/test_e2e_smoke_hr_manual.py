import io
import json
from pathlib import Path

import openpyxl
import pytest

from config import settings

ROOT = Path(__file__).resolve().parents[2]
HR_MANUAL_DOCX = ROOT / "test_kb" / "test-kb-extracts" / "hr-manual" / "hr-manual-master" / "docx" / "manual.docx"
TEST_QUESTIONNAIRE = ROOT / "test_kb" / "test-questionnaire.xlsx"


def read_sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
@pytest.mark.smoke
async def test_hr_manual_to_questionnaire_smoke_flow(
    client,
    workspace_owner,
    monkeypatch,
    deterministic_questionnaire_items,
    deterministic_answer_map,
):
    monkeypatch.setattr(
        "services.ingestion.embed_batch",
        lambda texts: [[0.0] * settings.embed_dim for _ in texts],
    )

    async def fake_parse_questionnaire_file_llm(path: str, filename: str):
        return deterministic_questionnaire_items

    async def fake_check_library(question: str, db, workspace_id, threshold=0.88):
        return None

    async def fake_decompose_question(question: str):
        return [question]

    async def fake_retrieve_and_rerank(question: str, db, top_n=8, project_id=None):
        answer = deterministic_answer_map[question]
        return [
            {
                "id": f"chunk-{abs(hash(question))}",
                "content": answer,
                "page": 1,
                "source": "manual.docx",
                "score": 1.0,
            }
        ]

    async def fake_generate_answer(question: str, chunks: list[dict]):
        answer = deterministic_answer_map[question]
        return {
            "answer": answer,
            "citations": [
                {
                    "source": "manual.docx",
                    "page": 1,
                    "excerpt": chunks[0]["content"],
                }
            ],
            "confidence": 0.97,
        }

    monkeypatch.setattr(
        "api.questionnaire.parse_questionnaire_file_llm",
        fake_parse_questionnaire_file_llm,
    )
    monkeypatch.setattr("api.questionnaire._check_library", fake_check_library)
    monkeypatch.setattr("api.questionnaire.decompose_question", fake_decompose_question)
    monkeypatch.setattr("api.questionnaire.retrieve_and_rerank", fake_retrieve_and_rerank)
    monkeypatch.setattr("api.questionnaire.generate_answer", fake_generate_answer)

    create_project = await client.post(
        "/api/projects",
        headers=workspace_owner["headers"],
        json={"name": "Smoke Project"},
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
                HR_MANUAL_DOCX.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_doc.status_code == 200, upload_doc.text

    parse_questionnaire = await client.post(
        "/api/questionnaire/parse",
        headers=workspace_owner["headers"],
        data={"project_id": project_id},
        files={
            "file": (
                "test-questionnaire.xlsx",
                TEST_QUESTIONNAIRE.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert parse_questionnaire.status_code == 200, parse_questionnaire.text
    questionnaire_data = parse_questionnaire.json()
    assert len(questionnaire_data["questions"]) == len(deterministic_questionnaire_items)
    questionnaire_id = questionnaire_data["id"]

    answer_response = await client.get(
        f"/api/questionnaire/{questionnaire_id}/answer-all-stream",
        headers=workspace_owner["headers"],
    )
    assert answer_response.status_code == 200, answer_response.text
    events = read_sse_events(answer_response.text)
    answer_events = [event for event in events if event["type"] == "answer"]
    done_events = [event for event in events if event["type"] == "done"]

    assert len(answer_events) == len(deterministic_questionnaire_items)
    assert done_events[-1]["total"] == len(deterministic_questionnaire_items)

    answers_response = await client.get(
        f"/api/questionnaire/{questionnaire_id}/answers",
        headers=workspace_owner["headers"],
    )
    assert answers_response.status_code == 200, answers_response.text
    answers = answers_response.json()
    assert all(item["status"] == "done" for item in answers)

    approve_response = await client.post(
        f"/api/questionnaire/{questionnaire_id}/approve-all",
        headers=workspace_owner["headers"],
    )
    assert approve_response.status_code == 200, approve_response.text
    assert approve_response.json()["approved"] == len(deterministic_questionnaire_items)

    export_response = await client.get(
        f"/api/questionnaire/{questionnaire_id}/export-filled",
        headers=workspace_owner["headers"],
    )
    assert export_response.status_code == 200, export_response.text

    wb = openpyxl.load_workbook(io.BytesIO(export_response.content), data_only=True)
    ws = wb.active
    for item in deterministic_questionnaire_items:
        assert ws[item["answer_cell"]].value == deterministic_answer_map[item["question_text"]]
    wb.close()

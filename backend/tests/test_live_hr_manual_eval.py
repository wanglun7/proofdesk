import io
import json
from pathlib import Path

import openpyxl
import pytest
from openai import APIConnectionError

from config import settings


pytestmark = pytest.mark.live_eval

if not settings.openai_api_key or not settings.dashscope_api_key:
    pytest.skip("live eval requires OPENAI_API_KEY and DASHSCOPE_API_KEY", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[2]
HR_MANUAL_DOCX = ROOT / "test_kb" / "test-kb-extracts" / "hr-manual" / "hr-manual-master" / "docx" / "manual.docx"
TEST_QUESTIONNAIRE = ROOT / "test_kb" / "test-questionnaire.xlsx"


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _score_answer(answer: str, citations: list[dict], item: dict) -> tuple[int, dict]:
    normalized_answer = _normalize(answer)
    expected_points = [_normalize(point) for point in item["expected_points"]]
    covered = [point for point in expected_points if point in normalized_answer]
    forbidden_hits = [_normalize(point) for point in item.get("forbidden_claims", []) if _normalize(point) in normalized_answer]

    citation_text = " ".join(
        _normalize(" ".join(
            [
                citation.get("source", ""),
                citation.get("excerpt", ""),
            ]
        ))
        for citation in (citations or [])
    )
    citation_keywords = [_normalize(keyword) for keyword in item.get("citation_keywords", [])]
    citation_supported = any(keyword in citation_text for keyword in citation_keywords)
    coverage_ratio = len(covered) / max(len(expected_points), 1)

    if not normalized_answer:
        score = 0
    elif forbidden_hits:
        score = 1
    elif coverage_ratio >= 1.0 and citation_supported:
        score = 4
    elif coverage_ratio >= 0.66 and citation_supported:
        score = 3
    elif coverage_ratio >= 0.33:
        score = 2
    else:
        score = 1

    return score, {
        "covered_points": covered,
        "coverage_ratio": coverage_ratio,
        "forbidden_hits": forbidden_hits,
        "citation_supported": citation_supported,
    }


@pytest.mark.asyncio
async def test_live_hr_manual_eval(
    client,
    workspace_owner,
    hr_manual_gold,
    tmp_path,
):
    create_project = await client.post(
        "/api/projects",
        headers=workspace_owner["headers"],
        json={"name": "Live Eval Project"},
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
    questionnaire_id = parse_questionnaire.json()["id"]

    try:
        answer_response = await client.get(
            f"/api/questionnaire/{questionnaire_id}/answer-all-stream",
            headers=workspace_owner["headers"],
        )
    except APIConnectionError as exc:
        pytest.skip(f"live eval provider unavailable: {exc}")
    assert answer_response.status_code == 200, answer_response.text

    answers_response = await client.get(
        f"/api/questionnaire/{questionnaire_id}/answers",
        headers=workspace_owner["headers"],
    )
    assert answers_response.status_code == 200, answers_response.text
    answers = answers_response.json()

    answers_by_question = {item["question"]: item for item in answers}
    scored_items = []
    score_values = []
    unsupported_claims = 0
    citation_supported_count = 0
    success_count = 0

    for item in hr_manual_gold:
        answer_row = answers_by_question[item["question_text"]]
        final_answer = answer_row["human_edit"] or answer_row["draft"] or ""
        score, details = _score_answer(final_answer, answer_row["citations"] or [], item)
        score_values.append(score)
        unsupported_claims += 1 if details["forbidden_hits"] else 0
        citation_supported_count += 1 if details["citation_supported"] else 0
        success_count += 1 if final_answer else 0
        scored_items.append(
            {
                "question": item["question_text"],
                "answer": final_answer,
                "citations": answer_row["citations"] or [],
                "score": score,
                **details,
            }
        )

    approve_response = await client.post(
        f"/api/questionnaire/{questionnaire_id}/approve-all",
        headers=workspace_owner["headers"],
    )
    assert approve_response.status_code == 200, approve_response.text

    export_response = await client.get(
        f"/api/questionnaire/{questionnaire_id}/export-filled",
        headers=workspace_owner["headers"],
    )
    assert export_response.status_code == 200, export_response.text
    wb = openpyxl.load_workbook(io.BytesIO(export_response.content), data_only=True)
    ws = wb.active
    export_cell_accuracy = 1.0
    for item in hr_manual_gold:
        answer_row = answers_by_question[item["question_text"]]
        expected_cell_value = answer_row["human_edit"] or answer_row["draft"] or ""
        if (ws[item["answer_cell"]].value or "") != expected_cell_value:
            export_cell_accuracy = 0.0
            break
    wb.close()

    metrics = {
        "avg_score": sum(score_values) / len(score_values),
        "score_ge_3_rate": sum(1 for score in score_values if score >= 3) / len(score_values),
        "unsupported_claim_rate": unsupported_claims / len(score_values),
        "citation_support_rate": citation_supported_count / len(score_values),
        "answer_success_rate": success_count / len(score_values),
        "export_cell_accuracy": export_cell_accuracy,
    }

    report = {
        "fixture": "hr-manual-docx + test-questionnaire.xlsx",
        "model": settings.openai_model,
        "items": scored_items,
        "metrics": metrics,
    }
    json_report = tmp_path / "live-eval-report.json"
    md_report = tmp_path / "live-eval-report.md"
    json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_report.write_text(
        "\n".join(
            [
                "# Live Eval Report",
                "",
                f"- avg_score: {metrics['avg_score']:.2f}",
                f"- score_ge_3_rate: {metrics['score_ge_3_rate']:.2%}",
                f"- unsupported_claim_rate: {metrics['unsupported_claim_rate']:.2%}",
                f"- citation_support_rate: {metrics['citation_support_rate']:.2%}",
                f"- answer_success_rate: {metrics['answer_success_rate']:.2%}",
                f"- export_cell_accuracy: {metrics['export_cell_accuracy']:.2%}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert metrics["answer_success_rate"] >= 0.95
    assert metrics["export_cell_accuracy"] == 1.0
    assert metrics["avg_score"] >= 3.0
    assert metrics["score_ge_3_rate"] >= 0.80
    assert metrics["unsupported_claim_rate"] <= 0.10

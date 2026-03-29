from fastapi import HTTPException

from api.export import _ensure_questionnaire_exportable


def test_export_requires_all_answers_to_be_approved():
    rows = [
        (object(), type("Answer", (), {"status": "approved"})()),
        (object(), type("Answer", (), {"status": "done"})()),
    ]

    try:
        _ensure_questionnaire_exportable(rows)
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "approved" in exc.detail.lower()
    else:
        raise AssertionError("Expected export gating to reject non-approved answers")


def test_export_allows_all_approved_answers():
    rows = [
        (object(), type("Answer", (), {"status": "approved"})()),
        (object(), type("Answer", (), {"status": "approved"})()),
    ]

    _ensure_questionnaire_exportable(rows)

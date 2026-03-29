import pytest

from api.questionnaire import _check_library


class FakeExecuteResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeDB:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, params):
        self.calls.append((sql, params))
        row = type("Row", (), {"similarity": 0.95, "answer_text": "From library"})()
        return FakeExecuteResult(row)


@pytest.mark.asyncio
async def test_check_library_scopes_lookup_to_workspace(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr("api.questionnaire._embed_query", lambda _: [0.1, 0.2])

    result = await _check_library("How do you encrypt data?", db, workspace_id="ws-123")

    assert result["answer"] == "From library"
    assert db.calls[0][1]["workspace_id"] == "ws-123"
    assert "workspace_id" in str(db.calls[0][0])

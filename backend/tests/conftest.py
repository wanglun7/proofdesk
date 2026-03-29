import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal, engine, init_db
from main import app
from models import Account, Project, Questionnaire, Workspace

ROOT = Path(__file__).resolve().parents[2]
TEST_KB_DIR = ROOT / "test_kb"
HR_MANUAL_DOCX = TEST_KB_DIR / "test-kb-extracts" / "hr-manual" / "hr-manual-master" / "docx" / "manual.docx"
TEST_QUESTIONNAIRE = TEST_KB_DIR / "test-questionnaire.xlsx"
HR_MANUAL_EVAL = TEST_KB_DIR / "hr-manual-eval.json"
QUESTIONNAIRE_FILES_DIR = ROOT / "backend" / "questionnaire_files"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _read_gold_eval() -> list[dict]:
    return json.loads(HR_MANUAL_EVAL.read_text(encoding="utf-8"))["items"]


async def _cleanup_workspace(workspace_id: str, owner_username: str) -> None:
    async with AsyncSessionLocal() as db:
        qids_result = await db.execute(
            select(Questionnaire.id)
            .join(Project, Project.id == Questionnaire.project_id)
            .where(Project.workspace_id == workspace_id)
        )
        questionnaire_ids = qids_result.scalars().all()

        workspace = await db.get(Workspace, workspace_id)
        account_result = await db.execute(select(Account).where(Account.username == owner_username))
        account = account_result.scalar_one_or_none()

        if workspace is not None:
            await db.delete(workspace)
        if account is not None:
            await db.delete(account)
        await db.commit()

    for questionnaire_id in questionnaire_ids:
        stored = QUESTIONNAIRE_FILES_DIR / f"{questionnaire_id}.xlsx"
        if stored.exists():
            stored.unlink()


def read_sse_events(body: str) -> list[dict]:
    events: list[dict] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.fixture(scope="session")
def hr_manual_gold() -> list[dict]:
    return _read_gold_eval()


@pytest.fixture(scope="session")
def deterministic_questionnaire_items(hr_manual_gold: list[dict]) -> list[dict]:
    return [
        {
            "seq": index,
            "question_text": item["question_text"],
            "section": item.get("section"),
            "answer_cell": item["answer_cell"],
        }
        for index, item in enumerate(hr_manual_gold)
    ]


@pytest.fixture(scope="session")
def deterministic_answer_map(hr_manual_gold: list[dict]) -> dict[str, str]:
    return {item["question_text"]: item["deterministic_answer"] for item in hr_manual_gold}


@pytest_asyncio.fixture(loop_scope="function")
async def client():
    await engine.dispose()
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def workspace_owner(client: AsyncClient):
    suffix = uuid.uuid4().hex[:10]

    superadmin_login = await client.post(
        "/api/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert superadmin_login.status_code == 200, superadmin_login.text
    superadmin_token = superadmin_login.json()["access_token"]

    bootstrap = await client.post(
        "/api/auth/bootstrap/workspace",
        headers=_auth_headers(superadmin_token),
        json={
            "workspace_name": f"Test Workspace {suffix}",
            "owner_username": f"test_owner_{suffix}",
            "owner_password": "changeme123",
        },
    )
    assert bootstrap.status_code == 200, bootstrap.text
    bootstrap_data = bootstrap.json()

    owner_login = await client.post(
        "/api/auth/login",
        json={
            "username": bootstrap_data["owner_username"],
            "password": "changeme123",
        },
    )
    assert owner_login.status_code == 200, owner_login.text
    owner_token = owner_login.json()["access_token"]

    payload = {
        "workspace_id": bootstrap_data["workspace_id"],
        "workspace_name": bootstrap_data["workspace_name"],
        "owner_username": bootstrap_data["owner_username"],
        "headers": _auth_headers(owner_token),
    }

    try:
        yield payload
    finally:
        await _cleanup_workspace(payload["workspace_id"], payload["owner_username"])

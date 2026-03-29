import uuid

import pytest

from api.projects import ProjectCreate, create_project
from auth_utils import AuthContext


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.refreshed = []

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.committed = True

    async def refresh(self, item):
        self.refreshed.append(item)


@pytest.mark.asyncio
async def test_create_project_assigns_workspace_from_auth_context():
    db = FakeSession()
    auth = AuthContext(
        username="owner",
        account_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        role="owner",
        is_superadmin=False,
    )

    result = await create_project(ProjectCreate(name="Acme"), db=db, auth=auth)

    assert db.committed is True
    assert len(db.added) == 1
    assert db.added[0].workspace_id == auth.workspace_id
    assert result["name"] == "Acme"

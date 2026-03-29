import uuid

from auth_utils import (
    AuthContext,
    create_account_token,
    create_superadmin_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip():
    password_hash = hash_password("s3cret-pass")

    assert password_hash != "s3cret-pass"
    assert verify_password("s3cret-pass", password_hash) is True
    assert verify_password("wrong-pass", password_hash) is False


def test_account_token_round_trip_preserves_workspace_scope():
    context = AuthContext(
        username="alice",
        account_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        role="owner",
        is_superadmin=False,
    )

    token = create_account_token(context)
    decoded = decode_access_token(token)

    assert decoded.username == "alice"
    assert decoded.account_id == context.account_id
    assert decoded.workspace_id == context.workspace_id
    assert decoded.role == "owner"
    assert decoded.is_superadmin is False


def test_superadmin_token_round_trip_has_no_workspace():
    token = create_superadmin_token("admin")
    decoded = decode_access_token(token)

    assert decoded.username == "admin"
    assert decoded.is_superadmin is True
    assert decoded.account_id is None
    assert decoded.workspace_id is None
    assert decoded.role is None

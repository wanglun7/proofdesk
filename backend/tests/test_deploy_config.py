from pathlib import Path

from config import Settings


ROOT = Path(__file__).resolve().parents[2]


def test_settings_accepts_legacy_secret_key_env(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("SECRET_KEY", "legacy-secret")

    settings = Settings(_env_file=None)

    assert settings.jwt_secret == "legacy-secret"


def test_docker_compose_binds_http_to_loopback_only():
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '127.0.0.1:8080:80' in compose_text


def test_env_examples_use_jwt_secret_name():
    root_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    backend_example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")

    assert "JWT_SECRET=" in root_example
    assert "SECRET_KEY=" not in root_example
    assert "JWT_SECRET=" in backend_example
    assert "SECRET_KEY=" not in backend_example


def test_docker_compose_passes_wecom_callback_config_to_backend():
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "WECOM_KF_TOKEN: ${WECOM_KF_TOKEN}" in compose_text
    assert "WECOM_KF_ENCODING_AES_KEY: ${WECOM_KF_ENCODING_AES_KEY}" in compose_text
    assert "WECOM_KF_RECEIVE_ID: ${WECOM_KF_RECEIVE_ID:-}" in compose_text
    assert "WECOM_KF_SECRET: ${WECOM_KF_SECRET:-}" in compose_text
    assert "WECOM_CORP_ID: ${WECOM_CORP_ID:-}" in compose_text

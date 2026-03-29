import dashscope

from config import Settings
from services.dashscope_client import configure_dashscope


def test_settings_accept_dashscope_base_url(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/api/v1")

    settings = Settings(_env_file=None)

    assert settings.dashscope_base_url == "https://dashscope-intl.aliyuncs.com/api/v1"


def test_settings_default_to_intl_dashscope_and_supported_models():
    settings = Settings(_env_file=None)

    assert settings.dashscope_base_url == "https://dashscope-intl.aliyuncs.com/api/v1"
    assert settings.embedding_model == "text-embedding-v4"
    assert settings.reranker_model == "qwen3-rerank"


def test_configure_dashscope_applies_api_key_and_base_url(monkeypatch):
    monkeypatch.setattr(dashscope, "api_key", "")
    monkeypatch.setattr(dashscope, "base_http_api_url", "https://dashscope.aliyuncs.com/api/v1")

    settings = Settings(
        _env_file=None,
        dashscope_api_key="test-key",
        dashscope_base_url="https://dashscope-intl.aliyuncs.com/api/v1",
    )

    configure_dashscope(settings)

    assert dashscope.api_key == "test-key"
    assert dashscope.base_http_api_url == "https://dashscope-intl.aliyuncs.com/api/v1"

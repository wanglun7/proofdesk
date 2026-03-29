from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dashscope_base_url_is_documented_in_env_examples():
    root_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    backend_example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")

    assert "DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1" in root_example
    assert "DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1" in backend_example
    assert "EMBEDDING_MODEL=text-embedding-v4" in root_example
    assert "EMBEDDING_MODEL=text-embedding-v4" in backend_example
    assert "RERANKER_MODEL=qwen3-rerank" in root_example
    assert "RERANKER_MODEL=qwen3-rerank" in backend_example


def test_docker_compose_passes_dashscope_base_url_to_backend():
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "DASHSCOPE_BASE_URL: ${DASHSCOPE_BASE_URL:-https://dashscope-intl.aliyuncs.com/api/v1}" in compose_text
    assert "EMBEDDING_MODEL: ${EMBEDDING_MODEL:-text-embedding-v4}" in compose_text
    assert "RERANKER_MODEL: ${RERANKER_MODEL:-qwen3-rerank}" in compose_text

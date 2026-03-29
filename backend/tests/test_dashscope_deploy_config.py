from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dashscope_base_url_is_documented_in_env_examples():
    root_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    backend_example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")

    assert "DASHSCOPE_BASE_URL=" in root_example
    assert "DASHSCOPE_BASE_URL=" in backend_example


def test_docker_compose_passes_dashscope_base_url_to_backend():
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "DASHSCOPE_BASE_URL: ${DASHSCOPE_BASE_URL" in compose_text

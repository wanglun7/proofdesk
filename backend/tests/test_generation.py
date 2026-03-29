from services.generation import build_prompt, parse_llm_response


def test_build_prompt_includes_question_and_chunks():
    chunks = [{"content": "We use AES-256 encryption.", "source": "policy.pdf", "page": 1}]
    prompt = build_prompt("How do you encrypt data?", chunks)
    assert "AES-256" in prompt
    assert "How do you encrypt data?" in prompt
    assert "policy.pdf" in prompt


def test_parse_llm_response_valid_json():
    raw = '{"answer": "We use AES-256.", "confidence": 0.9, "citations": [0]}'
    result = parse_llm_response(raw)
    assert result["answer"] == "We use AES-256."
    assert result["citations"] == [0]


def test_parse_llm_response_markdown_code_block():
    raw = '```json\n{"answer": "Yes", "confidence": 0.8, "citations": []}\n```'
    result = parse_llm_response(raw)
    assert result["answer"] == "Yes"
    assert result["citations"] == []


def test_parse_llm_response_fallback_on_plain_text():
    raw = "We use AES-256 encryption for all data at rest."
    result = parse_llm_response(raw)
    assert result["answer"] == raw
    assert result["citations"] == []

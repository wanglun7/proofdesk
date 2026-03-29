from pathlib import Path

import pytest
from openai import APIConnectionError

from config import settings
from services.questionnaire_parser import parse_questionnaire_file_llm


pytestmark = pytest.mark.live_eval

if not settings.openai_api_key:
    pytest.skip("live questionnaire parser test requires OPENAI_API_KEY", allow_module_level=True)


ROOT = Path(__file__).resolve().parents[2]
QUESTIONNAIRE_PATH = ROOT / "test_kb" / "test-questionnaire.xlsx"


@pytest.mark.asyncio
async def test_live_test_questionnaire_fixture_parses_with_expected_answer_cells(hr_manual_gold):
    try:
        questions = await parse_questionnaire_file_llm(str(QUESTIONNAIRE_PATH), QUESTIONNAIRE_PATH.name)
    except APIConnectionError as exc:
        pytest.skip(f"live parser provider unavailable: {exc}")

    assert len(questions) == len(hr_manual_gold)
    for item, expected in zip(questions, hr_manual_gold):
        assert item["question_text"] == expected["question_text"]
        assert item["answer_cell"] == expected["answer_cell"]

"""
Integration tests for questionnaire_parser against 7 real-world Excel fixtures.
Each test calls the LLM-based parser and verifies question count + key content + answer_cell.

Run: cd backend && pytest tests/test_questionnaire_parser.py -v -s
"""
import pytest
from pathlib import Path

from config import settings
from services.questionnaire_parser import parse_questionnaire_file_llm

FIXTURES = Path(__file__).parent.parent.parent / "test_kb" / "questionnaire_parser_tests"

pytestmark = [pytest.mark.asyncio, pytest.mark.live_eval]

if not settings.openai_api_key:
    pytest.skip("questionnaire parser tests require OPENAI_API_KEY", allow_module_level=True)


# ---------------------------------------------------------------------------
# 01 — classic two-column: Q in A, answer in B
# ---------------------------------------------------------------------------
async def test_01_classic_two_column():
    path = FIXTURES / "01_classic_two_column.xlsx"
    qs = await parse_questionnaire_file_llm(str(path), path.name)
    texts = [q["question_text"] for q in qs]

    # 5 real questions; row 6 "Note: Please attach..." is INSTRUCTION
    assert len(qs) == 5, f"Expected 5, got {len(qs)}: {texts}"

    assert any("information security policy" in t for t in texts)
    assert any("security policy reviewed" in t for t in texts)
    assert any("CISO" in t or "Chief Information Security Officer" in t for t in texts)
    assert any("onboarding" in t for t in texts)
    assert any("background checks" in t for t in texts)

    # Instruction row must NOT appear
    assert not any("Please attach" in t for t in texts), f"Instruction parsed as question: {texts}"

    # answer_cell: answers in col B
    cells = [q.get("answer_cell") for q in qs]
    for expected in ["B3", "B4", "B5", "B7", "B8"]:
        assert expected in cells, f"{expected} missing from answer_cells: {cells}"
    assert all(c is None or c.startswith("B") for c in cells), f"Unexpected answer col: {cells}"


# ---------------------------------------------------------------------------
# 02 — numbered index + two sections (A=num, B=question, C=required, D=answer)
# ---------------------------------------------------------------------------
async def test_02_numbered_sections():
    path = FIXTURES / "02_numbered_index_with_sections.xlsx"
    qs = await parse_questionnaire_file_llm(str(path), path.name)
    texts = [q["question_text"] for q in qs]
    sections = [q.get("section") for q in qs]

    assert len(qs) == 7, f"Expected 7, got {len(qs)}: {texts}"

    assert any(s and "Data Management" in s for s in sections)
    assert any(s and "Access Control" in s for s in sections)

    assert any("personal data" in t for t in texts)
    assert any("multi-factor" in t for t in texts)
    assert any("access rights reviewed" in t for t in texts)
    assert any("Data retention period" in t for t in texts)

    # Instruction row 10 must NOT appear
    assert not any("Responses should be concise" in t for t in texts), f"Instruction in questions: {texts}"

    # answer_cell: answers in col D
    cells = [q.get("answer_cell") for q in qs]
    for expected in ["D3", "D4", "D5", "D7", "D8", "D9", "D11"]:
        assert expected in cells, f"{expected} missing from answer_cells: {cells}"
    assert all(c is None or c.startswith("D") for c in cells), f"Unexpected answer col: {cells}"


# ---------------------------------------------------------------------------
# 03 — no formatting at all; sections identified purely by semantics
# ---------------------------------------------------------------------------
async def test_03_no_formatting():
    path = FIXTURES / "03_no_formatting_pure_text.xlsx"
    qs = await parse_questionnaire_file_llm(str(path), path.name)
    texts = [q["question_text"] for q in qs]
    sections = [q.get("section") for q in qs]

    assert len(qs) == 10, f"Expected 10, got {len(qs)}: {texts}"

    assert any(s and "Company Overview" in s for s in sections)
    assert any(s and "Security Practices" in s for s in sections)
    assert any(s and "Incident Response" in s for s in sections)

    assert any("Company legal name" in t for t in texts)
    assert any("patch management" in t for t in texts)
    assert any("data breach" in t for t in texts)

    # Title / metadata rows must NOT appear
    assert not any("Vendor Security Assessment Form" in t for t in texts)
    assert not any("Please complete all fields" in t for t in texts)

    # answer_cell: single-column file — LLM 可能猜 B 列，也可能为 None，都合理
    cells = [q.get("answer_cell") for q in qs]
    assert all(c is None or c.startswith("B") for c in cells), f"Unexpected answer col: {cells}"


# ---------------------------------------------------------------------------
# 04 — compliance checklist with Y/N dropdowns
# ---------------------------------------------------------------------------
async def test_04_checklist_dropdowns():
    path = FIXTURES / "04_compliance_checklist_dropdowns.xlsx"
    qs = await parse_questionnaire_file_llm(str(path), path.name)
    texts = [q["question_text"] for q in qs]
    sections = [q.get("section") for q in qs]

    assert len(qs) == 10, f"Expected 10, got {len(qs)}: {texts}"

    assert any(s and "Access Control" in s for s in sections)
    assert any(s and "Cryptography" in s for s in sections)
    assert any(s and "Physical Security" in s for s in sections)

    assert any("multi-factor authentication" in t for t in texts)
    assert any("AES-256" in t for t in texts)
    assert any("CCTV" in t for t in texts)

    # answer_cell: dropdown answers in col B
    cells = [q.get("answer_cell") for q in qs]
    for expected in ["B4", "B5", "B6", "B7", "B9", "B10", "B11", "B13", "B14", "B15"]:
        assert expected in cells, f"{expected} missing from answer_cells: {cells}"
    assert all(c is None or c.startswith("B") for c in cells), f"Unexpected answer col: {cells}"


# ---------------------------------------------------------------------------
# 05 — multi-sheet: Instructions sheet ignored, Questions sheet parsed
# ---------------------------------------------------------------------------
async def test_05_multi_sheet():
    path = FIXTURES / "05_multi_sheet_instructions_plus_questions.xlsx"
    qs = await parse_questionnaire_file_llm(str(path), path.name)
    texts = [q["question_text"] for q in qs]

    assert len(qs) == 8, f"Expected 8, got {len(qs)}: {texts}"

    # Instructions sheet rows must NOT appear
    assert not any("Submit completed form" in t for t in texts)
    assert not any("j.smith" in t for t in texts)

    assert any("legal name" in t for t in texts)
    assert any("DPIA" in t or "Data Protection Impact Assessment" in t for t in texts)
    assert any("subprocessors" in t for t in texts)

    # answer_cell: answers in col C
    cells = [q.get("answer_cell") for q in qs]
    for expected in ["C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]:
        assert expected in cells, f"{expected} missing from answer_cells: {cells}"
    assert all(c is None or c.startswith("C") for c in cells), f"Unexpected answer col: {cells}"


# ---------------------------------------------------------------------------
# 06 — statement-style fields, no question marks
# ---------------------------------------------------------------------------
async def test_06_statement_style():
    path = FIXTURES / "06_statement_style_no_question_marks.xlsx"
    qs = await parse_questionnaire_file_llm(str(path), path.name)
    texts = [q["question_text"] for q in qs]
    sections = [q.get("section") for q in qs]

    assert len(qs) == 13, f"Expected 13, got {len(qs)}: {texts}"

    assert any(s and "Organizational Details" in s for s in sections)
    assert any(s and "Information Security" in s for s in sections)
    assert any(s and "Business Continuity" in s for s in sections)

    assert any("Legal entity name" in t for t in texts)
    assert any("RTO" in t or "Recovery Time Objective" in t for t in texts)
    assert any("BCP" in t or "business continuity" in t.lower() for t in texts)

    # answer_cell: answers in col B
    cells = [q.get("answer_cell") for q in qs]
    for expected in ["B4", "B5", "B6", "B7", "B9", "B10", "B11", "B12", "B13", "B15", "B16", "B17", "B18"]:
        assert expected in cells, f"{expected} missing from answer_cells: {cells}"
    assert all(c is None or c.startswith("B") for c in cells), f"Unexpected answer col: {cells}"


# ---------------------------------------------------------------------------
# 07 — ESG nested sections; questions in col C, letters a/b/c in col B
# Key regression: question text must NOT include "a " / "b " / "c " prefix
# ---------------------------------------------------------------------------
async def test_07_esg_no_prefix():
    path = FIXTURES / "07_nested_sections_esg.xlsx"
    qs = await parse_questionnaire_file_llm(str(path), path.name)
    texts = [q["question_text"] for q in qs]

    assert len(qs) == 13, f"Expected 13, got {len(qs)}: {texts}"

    # No question should start with a single letter index "a " / "b " / "c "
    bad = [t for t in texts if len(t) > 2 and t[0].lower() in "abcde" and t[1] == " "]
    assert not bad, f"Questions have letter-index prefix (regression): {bad}"

    assert any("Scope 1" in t for t in texts)
    assert any("net-zero" in t for t in texts)
    assert any("renewable" in t for t in texts)
    assert any("TRIR" in t or "Recordable Incident" in t for t in texts)
    assert any("code of ethics" in t for t in texts)

    # NOTE row must NOT be a question
    assert not any("most recent full financial year" in t for t in texts), f"NOTE row parsed as question: {texts}"

    # answer_cell: answers in col D
    cells = [q.get("answer_cell") for q in qs]
    for expected in ["D4", "D5", "D6", "D8", "D9", "D12", "D13", "D14", "D16", "D17", "D20", "D21", "D22"]:
        assert expected in cells, f"{expected} missing from answer_cells: {cells}"
    assert all(c is None or c.startswith("D") for c in cells), f"Unexpected answer col: {cells}"

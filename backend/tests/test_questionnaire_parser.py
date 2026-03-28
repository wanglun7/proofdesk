import openpyxl
import tempfile
import os
from services.questionnaire_parser import parse_excel_questionnaire, parse_questionnaire_file


def test_parse_excel_first_column_as_questions():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Question", "Answer"])  # header
    ws.append(["How do you handle data encryption?", ""])
    ws.append(["What is your incident response process?", ""])
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        wb.save(f.name)
        path = f.name
    try:
        questions = parse_excel_questionnaire(path)
        assert len(questions) == 2
        assert questions[0] == "How do you handle data encryption?"
        assert questions[1] == "What is your incident response process?"
    finally:
        os.unlink(path)


def test_parse_excel_skips_empty_rows():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Question"])  # header
    ws.append(["Valid question?", ""])
    ws.append([None, ""])  # empty row
    ws.append(["  ", ""])  # whitespace row
    ws.append(["Another question?", ""])
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        wb.save(f.name)
        path = f.name
    try:
        questions = parse_excel_questionnaire(path)
        assert len(questions) == 2
    finally:
        os.unlink(path)


def test_parse_txt_questionnaire():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("Question 1?\nQuestion 2?\n\nQuestion 3?\n")
        path = f.name
    try:
        questions = parse_questionnaire_file(path, "test.txt")
        assert len(questions) == 3
    finally:
        os.unlink(path)

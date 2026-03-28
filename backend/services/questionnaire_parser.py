import openpyxl
from pathlib import Path


def parse_excel_questionnaire(path: str) -> list[str]:
    """Extract questions from the first non-empty column, skipping the header row."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    questions = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # skip header
        if row and row[0] and str(row[0]).strip():
            questions.append(str(row[0]).strip())
    wb.close()
    return questions


def parse_questionnaire_file(path: str, filename: str) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return parse_excel_questionnaire(path)
    elif suffix == ".txt":
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip()]
    else:
        raise ValueError(f"Unsupported questionnaire format: {suffix}")

import io
import re
import pandas as pd


EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MIME = "text/csv"


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Report") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    buffer.seek(0)
    return buffer.getvalue()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def safe_filename(base_name: str, extension: str) -> str:
    cleaned = re.sub(r'[^\w\-]', '_', base_name)
    return f"{cleaned}.{extension.lstrip('.')}"
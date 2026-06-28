from __future__ import annotations

import csv
import io
import json

from .models import AnnualReportResult


def result_to_json_bytes(result: AnnualReportResult) -> bytes:
    return json.dumps(result.model_dump(), ensure_ascii=False, indent=2).encode("utf-8")


def result_to_csv_bytes(result: AnnualReportResult) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "field_1", "field_2", "field_3", "field_4", "field_5"])

    for item in result.balance_sheet:
        writer.writerow(
            ["balance_sheet", item.field_name, item.value, item.source_page or "", item.source_excerpt, ""]
        )
    for item in result.management_changes:
        writer.writerow(
            [
                "management_changes",
                item.name,
                item.change_type,
                item.current_role,
                item.effective_date,
                item.source_page or "",
            ]
        )
    for item in result.notes_summary:
        writer.writerow(["notes_summary", item.category, item.page_range, item.summary, item.risk_hint, ""])
    for item in result.quality_checks:
        writer.writerow(["quality_checks", item.level, item.code, item.message, "", ""])

    return buffer.getvalue().encode("utf-8-sig")


from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PageAnalysis(BaseModel):
    page_number: int
    page_type: Literal["cover", "table_of_contents", "financial_statement", "management", "notes", "other"]
    confidence: float = 0.0
    evidence: str = ""


class BalanceSheetItem(BaseModel):
    field_name: str
    value: str = ""
    source_page: int | None = None
    source_excerpt: str = ""


class ManagementChangeItem(BaseModel):
    name: str = ""
    previous_role: str = ""
    current_role: str = ""
    change_type: str = ""
    effective_date: str = ""
    source_page: int | None = None
    source_excerpt: str = ""


class NotesSummaryItem(BaseModel):
    category: str
    page_range: str = ""
    summary: str = ""
    risk_hint: str = ""
    source_excerpt: str = ""


class QualityCheckItem(BaseModel):
    level: Literal["info", "warning", "error"] = "info"
    code: str
    message: str


class AnnualReportResult(BaseModel):
    company_name: str = ""
    report_period: str = ""
    balance_sheet: list[BalanceSheetItem] = Field(default_factory=list)
    management_changes: list[ManagementChangeItem] = Field(default_factory=list)
    notes_summary: list[NotesSummaryItem] = Field(default_factory=list)
    quality_checks: list[QualityCheckItem] = Field(default_factory=list)
    page_analyses: list[PageAnalysis] = Field(default_factory=list)
    status: str = "success"


class UploadResponse(BaseModel):
    task_id: str
    status: str = "success"


class TaskEnvelope(BaseModel):
    task_id: str
    result: AnnualReportResult


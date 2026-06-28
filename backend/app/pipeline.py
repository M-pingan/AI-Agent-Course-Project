from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import settings
from .knowledge_base import BALANCE_SHEET_FIELDS, BALANCE_SHEET_FIELD_ALIASES, MANAGEMENT_ACTION_KEYWORDS, MANAGEMENT_EXCLUDE_KEYWORDS, NOTE_CATEGORIES, PAGE_TYPE_KEYWORDS, STATEMENT_TITLE_KEYWORDS
from .models import AnnualReportResult, BalanceSheetItem, ManagementChangeItem, NotesSummaryItem, PageAnalysis, QualityCheckItem
from .pdf_utils import PageText, extract_pdf_pages
from .prompts import build_balance_sheet_prompt, build_management_change_prompt, build_notes_summary_prompt
from .qwen_client import QwenClient


@dataclass(frozen=True)
class SectionRange:
    title: str
    start_page: int
    end_page: int


def process_annual_report(pdf_path: Path) -> AnnualReportResult:
    pages = extract_pdf_pages(pdf_path)
    toc_sections = parse_table_of_contents(pages)
    page_analyses = classify_pages(pages, toc_sections)
    opening_text = build_labeled_text(pages[:8], max_chars=9000)
    result = AnnualReportResult(
        company_name=extract_company_name(opening_text),
        report_period=extract_report_period(opening_text),
        balance_sheet=extract_balance_sheet(pages, page_analyses),
        management_changes=extract_management_changes(pages, page_analyses),
        notes_summary=extract_notes_summary(pages, page_analyses),
        page_analyses=page_analyses,
    )
    result.quality_checks = run_quality_checks(result, pages) + enhance_with_qwen(result, pages, page_analyses)
    if not any(page.text for page in pages):
        result.status = "partial_success"
    return result


def parse_table_of_contents(pages: list[PageText]) -> list[SectionRange]:
    toc_mark = "\u76ee\u5f55"
    toc_pages = [page for page in pages[:12] if toc_mark in page.text]
    if not toc_pages:
        return []
    entries: list[tuple[str, int]] = []
    for page in toc_pages[:3]:
        for line in page.text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("\u7b2c") or "\u8282" not in stripped:
                continue
            normalized = re.sub(r"[.\u00b7\u2022\uff0e\u2026]{2,}", " ", stripped)
            match = re.search(r"(\u7b2c[\u4e00-\u9fa5]{1,6}\u8282)\s*(.*?)\s+(\d{1,3})$", normalized)
            if not match:
                continue
            title = f"{match.group(1)} {match.group(2).strip()}".strip()
            start_page = int(match.group(3))
            if 1 <= start_page <= len(pages):
                entries.append((title, start_page))
    deduped: list[tuple[str, int]] = []
    seen: set[int] = set()
    for title, start_page in sorted(entries, key=lambda item: item[1]):
        if start_page in seen:
            continue
        seen.add(start_page)
        deduped.append((title, start_page))
    ranges: list[SectionRange] = []
    for idx, (title, start_page) in enumerate(deduped):
        next_start = deduped[idx + 1][1] if idx + 1 < len(deduped) else len(pages) + 1
        ranges.append(SectionRange(title=title, start_page=start_page, end_page=min(len(pages), next_start - 1)))
    return ranges


def classify_pages(pages: list[PageText], sections: list[SectionRange]) -> list[PageAnalysis]:
    toc_pages = {page.page_number for page in pages if "\u76ee\u5f55" in page.text}
    management_range = find_section_range(sections, ["\u516c\u53f8\u6cbb\u7406", "\u73af\u5883\u548c\u793e\u4f1a", "\u8463\u4e8b", "\u76d1\u4e8b", "\u9ad8\u7ea7\u7ba1\u7406\u4eba\u5458"])
    financial_range = find_section_range(sections, ["\u8d22\u52a1\u62a5\u544a"])
    statement_window = detect_statement_window(pages, financial_range)
    notes_start = statement_window[1] + 1 if statement_window else None
    analyses: list[PageAnalysis] = []
    for page in pages:
        text = page.text
        page_type = "other"
        evidence = ""
        confidence = 0.25
        if page.page_number in toc_pages:
            page_type, evidence, confidence = "table_of_contents", "toc", 0.99
        elif page.page_number <= 3 and has_cover_features(text):
            page_type, evidence, confidence = "cover", "cover", 0.95
        elif statement_window and statement_window[0] <= page.page_number <= statement_window[1]:
            page_type, evidence, confidence = "financial_statement", "statement_window", 0.96
        elif financial_range and notes_start and notes_start <= page.page_number <= financial_range.end_page:
            page_type, evidence, confidence = "notes", "notes_window", 0.92
        elif management_range and management_range.start_page <= page.page_number <= management_range.end_page:
            page_type, evidence, confidence = "management", management_range.title, 0.88
        else:
            fallback_type, fallback_evidence = classify_page_by_keywords(text)
            if fallback_type:
                page_type, evidence, confidence = fallback_type, fallback_evidence, 0.7
        analyses.append(PageAnalysis(page_number=page.page_number, page_type=page_type, confidence=confidence, evidence=evidence))
    return analyses


def find_section_range(sections: list[SectionRange], keywords: list[str]) -> SectionRange | None:
    for section in sections:
        if any(keyword in section.title for keyword in keywords):
            return section
    return None


def has_cover_features(text: str) -> bool:
    return ("\u5e74\u5ea6\u62a5\u544a" in text and "\u516c\u53f8\u4ee3\u7801" in text) or ("\u5e74\u5ea6\u62a5\u544a" in text and "\u516c\u53f8\u7b80\u79f0" in text)


def classify_page_by_keywords(text: str) -> tuple[str | None, str]:
    if "\u76ee\u5f55" in text:
        return "table_of_contents", "toc"
    if any(title in text for title in STATEMENT_TITLE_KEYWORDS):
        return "financial_statement", "statement_title"
    if is_note_anchor_page(text):
        return "notes", "note_anchor"
    if is_management_context_page(text):
        return "management", "management_context"
    for page_type, keywords in PAGE_TYPE_KEYWORDS.items():
        hit = next((keyword for keyword in keywords if keyword in text), None)
        if hit:
            return page_type, hit
    return None, ""


def detect_statement_window(pages: list[PageText], financial_range: SectionRange | None) -> tuple[int, int] | None:
    candidates = pages if not financial_range else [page for page in pages if financial_range.start_page <= page.page_number <= financial_range.end_page]
    start_page: int | None = None
    last_page: int | None = None
    for page in candidates:
        text = page.text
        if start_page is None and ("\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868" in text or ("\u8d44\u4ea7\u8d1f\u503a\u8868" in text and "\u7f16\u5236\u5355\u4f4d" in text)):
            start_page = page.page_number
        if start_page is not None and any(title in text for title in STATEMENT_TITLE_KEYWORDS):
            last_page = page.page_number
        if start_page is not None and is_note_anchor_page(text):
            return start_page, page.page_number - 1
    if start_page is None:
        return None
    return start_page, last_page or start_page


def is_note_anchor_page(text: str) -> bool:
    markers = ["\u8d22\u52a1\u62a5\u8868\u9644\u6ce8", "\u516c\u53f8\u57fa\u672c\u60c5\u51b5", "\u7f16\u5236\u57fa\u7840", "\u91cd\u8981\u4f1a\u8ba1\u653f\u7b56", "\u4f1a\u8ba1\u671f\u95f4"]
    return any(marker in text for marker in markers)

def extract_company_name(text: str) -> str:
    corp_suffixes = ("\u80a1\u4efd\u6709\u9650\u516c\u53f8", "\u6709\u9650\u516c\u53f8")
    lines = [line.strip() for line in text.splitlines()[:10] if line.strip()]

    for marker in ["\u516c\u53f8\u540d\u79f0\uff1a", "\u516c\u53f8\u540d\u79f0:"]:
        if marker in text:
            tail = text.split(marker, 1)[1].split("\n", 1)[0].strip()
            if tail:
                return clean_company_name(tail)

    for line in lines:
        if any(flag in line for flag in ["\u516c\u53f8\u4ee3\u7801", "\u516c\u53f8\u7b80\u79f0"]):
            continue
        if any(line.endswith(suffix) for suffix in corp_suffixes):
            return clean_company_name(line)

    compact = re.sub(r"\s+", "", text)
    candidates = re.findall(r"([\u4e00-\u9fa5][\u4e00-\u9fa5A-Za-z0-9\uff08\uff09()]{2,80}(?:\u80a1\u4efd\u6709\u9650\u516c\u53f8|\u6709\u9650\u516c\u53f8))", compact)
    filtered = [item for item in candidates if not re.match(r"\d", item) and "\u516c\u53f8\u7b80\u79f0" not in item and "\u516c\u53f8\u4ee3\u7801" not in item]
    if filtered:
        return choose_best_company_name(filtered)

    return "\u5f85\u8865\u5145\u516c\u53f8\u540d\u79f0"


def clean_company_name(name: str) -> str:
    return re.sub(r"[\uff1a:]+$", "", name).strip()[:80]


def choose_best_company_name(candidates: list[str]) -> str:
    cleaned = [clean_company_name(item) for item in candidates if item]
    cleaned = [item for item in cleaned if item.endswith("\u516c\u53f8")]
    if not cleaned:
        return "\u5f85\u8865\u5145\u516c\u53f8\u540d\u79f0"

    preferred = [item for item in cleaned if item.endswith("\u80a1\u4efd\u6709\u9650\u516c\u53f8")]
    if preferred:
        preferred.sort(key=len)
        return preferred[0]

    cleaned.sort(key=len)
    return cleaned[0]


def extract_report_period(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    match = re.search(r"20\d{2}", compact)
    if match and "\u5e74\u5ea6\u62a5\u544a" in compact:
        return match.group(0) + "\u5e74\u5e74\u5ea6\u62a5\u544a"
    date_match = re.search(r"20\d{2}\u5e741\u67081\u65e5.{0,20}?20\d{2}\u5e7412\u670831\u65e5", compact)
    if date_match:
        return date_match.group(0)
    return "\u5f85\u8865\u5145\u62a5\u544a\u671f"


def extract_balance_sheet(pages: list[PageText], analyses: list[PageAnalysis]) -> list[BalanceSheetItem]:
    lines = collect_consolidated_balance_sheet_lines(pages, analyses)
    items: list[BalanceSheetItem] = []
    for field_name in BALANCE_SHEET_FIELDS:
        page_number, line = find_balance_sheet_line(lines, field_name)
        value = extract_current_period_amount(line) if line else ""
        items.append(BalanceSheetItem(field_name=field_name, value=value, source_page=page_number, source_excerpt=line[:180] if line else ""))
    return items


def collect_consolidated_balance_sheet_lines(pages: list[PageText], analyses: list[PageAnalysis]) -> list[tuple[int, str]]:
    page_map = {page.page_number: page for page in pages}
    statement_pages = [analysis.page_number for analysis in analyses if analysis.page_type == "financial_statement"]
    lines: list[tuple[int, str]] = []
    collecting = False
    for page_number in statement_pages:
        for raw_line in page_map[page_number].text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not collecting and "\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868" in line:
                collecting = True
                continue
            if not collecting:
                continue
            if "\u6bcd\u516c\u53f8\u8d44\u4ea7\u8d1f\u503a\u8868" in line or "\u5408\u5e76\u5229\u6da6\u8868" in line:
                return lines
            if should_skip_statement_line(line):
                continue
            lines.append((page_number, line))
    return lines


def should_skip_statement_line(line: str) -> bool:
    skip_words = ["\u7f16\u5236\u5355\u4f4d", "\u5355\u4f4d\uff1a\u5143", "\u5e01\u79cd\uff1a\u4eba\u6c11\u5e01", "\u9879\u76ee", "\u6d41\u52a8\u8d44\u4ea7\uff1a", "\u975e\u6d41\u52a8\u8d44\u4ea7\uff1a", "\u6d41\u52a8\u8d1f\u503a\uff1a", "\u975e\u6d41\u52a8\u8d1f\u503a\uff1a"]
    return any(word in line for word in skip_words)


def find_balance_sheet_line(lines: list[tuple[int, str]], field_name: str) -> tuple[int | None, str]:
    aliases = BALANCE_SHEET_FIELD_ALIASES.get(field_name, [field_name])
    for page_number, line in lines:
        normalized = normalize_lookup_text(line)
        if field_name == "\u6240\u6709\u8005\u6743\u76ca\u5408\u8ba1":
            if "\u6240\u6709\u8005\u6743\u76ca" in line and "\u5408\u8ba1" in line:
                return page_number, line
        elif any(normalize_lookup_text(alias) in normalized for alias in aliases):
            return page_number, line
    return None, ""


def normalize_lookup_text(text: str) -> str:
    return re.sub(r"[\s\uff1a:\uff08\uff09()\u3001\uff0c,]", "", text)


def extract_current_period_amount(line: str) -> str:
    if not line:
        return ""
    cleaned = re.sub("\\u9644\\u6ce8[\\u4e00-\\u9fa50-9\\u3001,\\uff0c\\-\\uff08\\uff09()A-Za-z]+", "", line)
    matches = re.findall(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?", cleaned)
    return matches[0] if matches else ""

def extract_management_changes(pages: list[PageText], analyses: list[PageAnalysis]) -> list[ManagementChangeItem]:
    page_map = {page.page_number: page for page in pages}
    items: list[ManagementChangeItem] = []
    for page in pick_pages_by_type(analyses, page_map, "management"):
        for line in page.text.splitlines():
            stripped = line.strip()
            if not is_management_change_line(stripped):
                continue
            item = parse_management_change_line(stripped, page.page_number)
            if item:
                items.append(item)
    return dedupe_management_changes(items)[:20]


def is_management_context_page(text: str) -> bool:
    return any(mark in text for mark in ["\u516c\u53f8\u6cbb\u7406", "\u8463\u4e8b", "\u76d1\u4e8b", "\u9ad8\u7ea7\u7ba1\u7406\u4eba\u5458"]) or any(word in text for word in MANAGEMENT_ACTION_KEYWORDS)


def is_management_change_line(line: str) -> bool:
    if not line or len(line) < 8 or len(line) > 220:
        return False
    if any(word in line for word in MANAGEMENT_EXCLUDE_KEYWORDS):
        return False
    if "\u53d6\u6d88\u76d1\u4e8b\u4f1a" in line:
        return True
    if "\u8058\u4efb\u3001\u89e3\u8058\u4f1a\u8ba1\u5e08\u4e8b\u52a1\u6240" in line or "\u8058\u4efb\u3001\u89e3\u8058" in line:
        return False
    if "\u73b0\u4efb\u53ca\u62a5\u544a\u671f\u5185\u79bb\u4efb" in line:
        return False
    return any(word in line for word in MANAGEMENT_ACTION_KEYWORDS)


def parse_management_change_line(line: str, page_number: int) -> ManagementChangeItem | None:
    if "\u53d6\u6d88\u76d1\u4e8b\u4f1a" in line:
        return ManagementChangeItem(name="\u76d1\u4e8b\u4f1a", previous_role="\u76d1\u4e8b\u4f1a", current_role="\u5ba1\u8ba1\u59d4\u5458\u4f1a\u627f\u63a5\u76d1\u7763\u804c\u8d23", change_type="\u6cbb\u7406\u7ed3\u6784\u8c03\u6574", effective_date=extract_date(line), source_page=page_number, source_excerpt=line[:180])
    name = extract_person_name(line)
    current_role = extract_current_role(line)
    if not name and not current_role:
        return None
    return ManagementChangeItem(name=name or "\u5f85\u4eba\u5de5\u786e\u8ba4", previous_role=extract_previous_role(line), current_role=current_role, change_type=extract_change_type(line), effective_date=extract_date(line), source_page=page_number, source_excerpt=line[:180])


def extract_person_name(line: str) -> str:
    stopwords = {"\u516c\u53f8", "\u62a5\u544a\u671f\u5185", "\u8463\u4e8b\u4f1a", "\u80a1\u4e1c\u4f1a", "\u76d1\u4e8b\u4f1a", "\u5ba1\u8ba1\u59d4\u5458\u4f1a", "\u73b0\u4efb\u53ca\u62a5\u544a", "\u51b3\u5b9a\u516c\u53f8", "\u4f53\u89c4\u7ae0", "\u8058\u4efb", "\u89e3\u8058"}
    for candidate in re.findall(r"([\u4e00-\u9fa5]{2,4})(?:\u5148\u751f|\u5973\u58eb)?", line):
        if candidate not in stopwords:
            return candidate
    return ""


def extract_previous_role(line: str) -> str:
    return line[line.find("\u539f") : line.find("\u539f") + 14].strip() if "\u539f" in line else ""


def extract_current_role(line: str) -> str:
    roles = ["\u8463\u4e8b\u957f", "\u603b\u7ecf\u7406", "\u8463\u4e8b", "\u76d1\u4e8b", "\u8d22\u52a1\u603b\u76d1", "\u526f\u603b\u7ecf\u7406", "\u5ba1\u8ba1\u59d4\u5458\u4f1a", "\u8463\u4e8b\u4f1a\u79d8\u4e66"]
    return next((role for role in roles if role in line), "")


def extract_change_type(line: str) -> str:
    mapping = ["\u8058\u4efb", "\u4efb\u547d", "\u8f9e\u4efb", "\u79bb\u4efb", "\u9009\u4e3e", "\u5f53\u9009", "\u8f9e\u53bb", "\u89e3\u8058", "\u6539\u9009"]
    hit = next((word for word in mapping if word in line), "")
    return hit or "\u6cbb\u7406\u7ed3\u6784\u8c03\u6574"


def extract_date(line: str) -> str:
    match = re.search(r"20\d{2}[\u5e74\-/.]\d{1,2}[\u6708\-/.]\d{1,2}\u65e5?", line)
    return match.group(0) if match else ""


def extract_notes_summary(pages: list[PageText], analyses: list[PageAnalysis]) -> list[NotesSummaryItem]:
    page_map = {page.page_number: page for page in pages}
    notes: list[NotesSummaryItem] = []
    for category, keywords in NOTE_CATEGORIES.items():
        matched_pages: list[int] = []
        excerpts: list[str] = []
        for page in pick_pages_by_type(analyses, page_map, "notes"):
            for line in page.text.splitlines():
                if any(keyword in line for keyword in keywords):
                    matched_pages.append(page.page_number)
                    excerpts.append(line[:180])
                    break
        if matched_pages:
            risk_hint = "\u5b58\u5728\u6f5c\u5728\u98ce\u9669\uff0c\u9700\u8981\u4eba\u5de5\u590d\u6838\u3002" if category in {"\u8d44\u4ea7\u51cf\u503c", "\u8bc9\u8bbc\u4e8b\u9879", "\u6216\u6709\u4e8b\u9879"} else "\u98ce\u9669\u6574\u4f53\u53ef\u63a7\u3002"
            notes.append(NotesSummaryItem(category=category, page_range=f"{matched_pages[0]}-{matched_pages[-1]}", summary=build_summary_from_excerpts(excerpts), risk_hint=risk_hint, source_excerpt="\uff1b".join(excerpts[:2])))
    return notes


def enhance_with_qwen(result: AnnualReportResult, pages: list[PageText], analyses: list[PageAnalysis]) -> list[QualityCheckItem]:
    client = QwenClient(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url, model=settings.qwen_model)
    if not client.enabled:
        return [QualityCheckItem(level="info", code="QWEN_DISABLED", message="Qwen disabled; using local rules only.")]
    page_map = {page.page_number: page for page in pages}
    checks: list[QualityCheckItem] = []
    try:
        financial_pages = pick_pages_by_type(analyses, page_map, "financial_statement")
        if financial_pages and count_missing_balance_fields(result.balance_sheet) >= 2:
            merge_balance_sheet(result.balance_sheet, extract_balance_sheet_with_qwen(client, financial_pages))
        management_pages = pick_pages_by_type(analyses, page_map, "management")
        if management_pages:
            llm_management = extract_management_changes_with_qwen(client, management_pages)
            if llm_management:
                result.management_changes = merge_management_changes(result.management_changes, llm_management)
        note_pages = pick_pages_by_type(analyses, page_map, "notes")
        if note_pages and len(result.notes_summary) < 3:
            llm_notes = extract_notes_summary_with_qwen(client, note_pages)
            if llm_notes:
                result.notes_summary = llm_notes[:10]
        if result.company_name == "\u5f85\u8865\u5145\u516c\u53f8\u540d\u79f0":
            candidate = extract_company_name(build_labeled_text(pages[:5], max_chars=5000))
            if candidate != "\u5f85\u8865\u5145\u516c\u53f8\u540d\u79f0":
                result.company_name = candidate
        checks.append(QualityCheckItem(level="info", code="QWEN_ENABLED", message=f"Qwen enhancement enabled: {settings.qwen_model}"))
    except Exception as exc:
        checks.append(QualityCheckItem(level="warning", code="QWEN_ENHANCE_FAILED", message=f"Qwen enhancement failed; falling back to local rules: {exc}"))
    return checks


def pick_pages_by_type(analyses: list[PageAnalysis], page_map: dict[int, PageText], page_type: str) -> list[PageText]:
    return [page_map[item.page_number] for item in analyses if item.page_type == page_type and item.page_number in page_map and page_map[item.page_number].text]


def count_missing_balance_fields(items: list[BalanceSheetItem]) -> int:
    return sum(1 for item in items if not item.value)


def build_labeled_text(pages: list[PageText], max_chars: int = 12000) -> str:
    chunks: list[str] = []
    total = 0
    for page in pages:
        segment = f"[page {page.page_number}]\n{page.text}\n"
        if total + len(segment) > max_chars:
            break
        chunks.append(segment)
        total += len(segment)
    return "\n".join(chunks)


def extract_balance_sheet_with_qwen(client: QwenClient, pages: list[PageText]) -> list[BalanceSheetItem]:
    payload = client.chat_json(system_prompt="Extract balance sheet fields and return JSON only.", user_prompt=build_balance_sheet_prompt(build_labeled_text(pages)))
    if not isinstance(payload, list):
        return []
    items: list[BalanceSheetItem] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        field_name = str(entry.get("field_name", "")).strip()
        if not field_name:
            continue
        excerpt = str(entry.get("source_excerpt", "")).strip()
        items.append(BalanceSheetItem(field_name=field_name, value=str(entry.get("value", "")).strip(), source_page=find_page_number_in_text(excerpt, pages), source_excerpt=excerpt))
    return items


def merge_balance_sheet(existing: list[BalanceSheetItem], llm_items: list[BalanceSheetItem]) -> None:
    mapping = {item.field_name: item for item in existing}
    for item in llm_items:
        target = mapping.get(item.field_name)
        if target:
            if not target.value and item.value:
                target.value = item.value
            if not target.source_page and item.source_page:
                target.source_page = item.source_page
            if not target.source_excerpt and item.source_excerpt:
                target.source_excerpt = item.source_excerpt


def extract_management_changes_with_qwen(client: QwenClient, pages: list[PageText]) -> list[ManagementChangeItem]:
    payload = client.chat_json(system_prompt="Extract real governance or management changes and return JSON only.", user_prompt=build_management_change_prompt(build_labeled_text(pages)))
    if not isinstance(payload, list):
        return []
    items: list[ManagementChangeItem] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        excerpt = str(entry.get("source_excerpt", "")).strip()
        items.append(ManagementChangeItem(name=str(entry.get("name", "")).strip(), previous_role=str(entry.get("previous_role", "")).strip(), current_role=str(entry.get("current_role", "")).strip(), change_type=str(entry.get("change_type", "")).strip(), effective_date=str(entry.get("effective_date", "")).strip(), source_page=find_page_number_in_text(excerpt, pages), source_excerpt=excerpt))
    return [item for item in items if item.source_excerpt or item.name]


def merge_management_changes(rule_items: list[ManagementChangeItem], llm_items: list[ManagementChangeItem]) -> list[ManagementChangeItem]:
    picked = [item for item in llm_items if item.name and item.name != "\u5f85\u4eba\u5de5\u786e\u8ba4"]
    picked += [item for item in rule_items if item.change_type == "\u6cbb\u7406\u7ed3\u6784\u8c03\u6574"]
    return dedupe_management_changes(picked or llm_items or rule_items)[:20]


def dedupe_management_changes(items: list[ManagementChangeItem]) -> list[ManagementChangeItem]:
    seen: set[tuple[str, str, int | None, str]] = set()
    deduped: list[ManagementChangeItem] = []
    for item in items:
        key = (item.name, item.change_type, item.source_page, item.current_role)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def extract_notes_summary_with_qwen(client: QwenClient, pages: list[PageText]) -> list[NotesSummaryItem]:
    payload = client.chat_json(system_prompt="Summarize note-related risk items and return JSON only.", user_prompt=build_notes_summary_prompt(build_labeled_text(pages)))
    if not isinstance(payload, list):
        return []
    items: list[NotesSummaryItem] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        excerpt = str(entry.get("source_excerpt", "")).strip()
        source_page = find_page_number_in_text(excerpt, pages)
        page_range = str(entry.get("page_range", "")).strip() or (str(source_page) if source_page else "")
        items.append(NotesSummaryItem(category=str(entry.get("category", "uncategorized")).strip(), page_range=page_range, summary=str(entry.get("summary", "")).strip(), risk_hint=str(entry.get("risk_hint", "")).strip(), source_excerpt=excerpt))
    return [item for item in items if item.summary or item.source_excerpt]


def find_page_number_in_text(excerpt: str, pages: list[PageText]) -> int | None:
    normalized = normalize_lookup_text(excerpt)[:50]
    if not normalized:
        return None
    for page in pages:
        if normalized in normalize_lookup_text(page.text):
            return page.page_number
    return None


def build_summary_from_excerpts(excerpts: list[str]) -> str:
    cleaned = [item.strip() for item in excerpts if item.strip()]
    return "\u672a\u8bc6\u522b\u5230\u6709\u6548\u9644\u6ce8\u5185\u5bb9\u3002" if not cleaned else "\uff1b".join(cleaned[:2])


def run_quality_checks(result: AnnualReportResult, pages: list[PageText]) -> list[QualityCheckItem]:
    checks: list[QualityCheckItem] = []
    if not any(page.text for page in pages):
        checks.append(QualityCheckItem(level="error", code="NO_TEXT", message="PDF text extraction failed; OCR may be required."))
    if result.company_name == "\u5f85\u8865\u5145\u516c\u53f8\u540d\u79f0":
        checks.append(QualityCheckItem(level="warning", code="COMPANY_NAME_MISSING", message="Company name was not identified reliably."))
    missing_fields = [item.field_name for item in result.balance_sheet if not item.value]
    if missing_fields:
        checks.append(QualityCheckItem(level="warning", code="MISSING_BALANCE_FIELDS", message="Missing balance fields: " + ", ".join(missing_fields[:5])))
    invalid_fields = [item.field_name for item in result.balance_sheet if item.value and not is_number_like(item.value)]
    if invalid_fields:
        checks.append(QualityCheckItem(level="warning", code="INVALID_NUMBER_FORMAT", message="Invalid number format fields: " + ", ".join(invalid_fields)))
    incomplete_management = [item for item in result.management_changes if item.name in {"", "\u5f85\u4eba\u5de5\u786e\u8ba4"} or not item.current_role]
    if incomplete_management:
        checks.append(QualityCheckItem(level="info", code="MANAGEMENT_FIELDS_INCOMPLETE", message="Some management change fields still need manual review."))
    if not checks:
        checks.append(QualityCheckItem(level="info", code="BASIC_CHECKS_PASSED", message="Basic rule checks passed."))
    return checks


def is_number_like(value: str) -> bool:
    return bool(re.fullmatch(r"[-]?\d[\d,]*(?:\.\d+)?", value))

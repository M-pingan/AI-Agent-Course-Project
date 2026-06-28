from __future__ import annotations


def build_page_classification_prompt(text: str) -> str:
    return f"""
You are an annual report parser. Classify the page into exactly one label:
- cover
- table_of_contents
- financial_statement
- management
- notes
- other

Page text:
{text[:2500]}
""".strip()


def build_balance_sheet_prompt(text: str) -> str:
    return f"""
Extract core balance sheet fields from the formal financial statement text below.
Requirements:
1. Prefer the consolidated balance sheet.
2. Extract the current reporting period amount, not the YoY percentage.
3. Return a JSON array only.
4. Each item must contain: field_name, value, source_excerpt.

Text:
{text[:6000]}
""".strip()


def build_management_change_prompt(text: str) -> str:
    return f"""
Extract real management or governance changes from the annual report text below.
Requirements:
1. Only keep real events such as appointment, resignation, election, dismissal, governance restructuring.
2. Ignore general annual report statements, directory lines, glossary text, meeting attendance, and process descriptions.
3. Return a JSON array only.
4. Each item must contain: name, previous_role, current_role, change_type, effective_date, source_excerpt.

Text:
{text[:6000]}
""".strip()


def build_notes_summary_prompt(text: str) -> str:
    return f"""
Summarize note-related annual report text into a JSON array.
Requirements:
1. Focus on impairment, litigation, guarantee, related-party transactions, and contingent matters.
2. Ignore cover pages, table of contents, and governance discussion.
3. Each item must contain: category, page_range, summary, risk_hint, source_excerpt.
4. Return JSON only.

Text:
{text[:7000]}
""".strip()

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import fitz
import pdfplumber


@dataclass
class PageText:
    page_number: int
    text: str


@dataclass
class _RawPage:
    page_number: int
    lines: list[str]


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _page_number_like(line: str) -> bool:
    normalized = line.strip()
    return bool(re.fullmatch(r"\d+\s*/\s*\d+", normalized)) or bool(re.fullmatch(r"-?\d+-?", normalized))


def _prepare_raw_pages(texts: list[str]) -> list[_RawPage]:
    return [
        _RawPage(page_number=index, lines=[_normalize_line(line) for line in text.splitlines() if _normalize_line(line)])
        for index, text in enumerate(texts, start=1)
    ]


def _detect_repeated_lines(raw_pages: list[_RawPage]) -> tuple[set[str], set[str]]:
    top_counter: Counter[str] = Counter()
    bottom_counter: Counter[str] = Counter()
    for page in raw_pages:
        if page.lines:
            top_counter[page.lines[0]] += 1
            bottom_counter[page.lines[-1]] += 1
    threshold = max(5, len(raw_pages) // 8)
    repeated_top = {line for line, count in top_counter.items() if count >= threshold and not _page_number_like(line)}
    repeated_bottom = {line for line, count in bottom_counter.items() if count >= threshold and not _page_number_like(line)}
    return repeated_top, repeated_bottom


def _clean_raw_pages(raw_pages: list[_RawPage]) -> list[PageText]:
    repeated_top, repeated_bottom = _detect_repeated_lines(raw_pages)
    cleaned_pages: list[PageText] = []
    for page in raw_pages:
        cleaned_lines = list(page.lines)
        if cleaned_lines and cleaned_lines[0] in repeated_top:
            cleaned_lines = cleaned_lines[1:]
        if cleaned_lines and (cleaned_lines[-1] in repeated_bottom or _page_number_like(cleaned_lines[-1])):
            cleaned_lines = cleaned_lines[:-1]
        cleaned_lines = [line for line in cleaned_lines if not _page_number_like(line)]
        cleaned_pages.append(PageText(page_number=page.page_number, text="\n".join(cleaned_lines)))
    return cleaned_pages


def extract_pdf_pages(pdf_path: Path) -> list[PageText]:
    raw_texts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            raw_texts.append(page.extract_text() or "")
    if any(text.strip() for text in raw_texts):
        return _clean_raw_pages(_prepare_raw_pages(raw_texts))

    raw_texts = []
    doc = fitz.open(str(pdf_path))
    try:
        for page in doc:
            raw_texts.append(page.get_text("text") or "")
    finally:
        doc.close()
    return _clean_raw_pages(_prepare_raw_pages(raw_texts))

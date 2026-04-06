"""
Phase 10 — Fact-capture: map frame_id + selected option (or submitted text) to learner_memory fields.

Authoritative: docs/phases/PHASE10_TECHNICAL_PROPOSAL.md §2 capture rules.
Called by ui_server after a response turn; returns a dict of field updates to apply.
No persistence; ui_server applies updates and persists by learner_id.
"""

import re
from typing import Dict, Optional

# Frame IDs that map to a single learner_memory field (no ambiguity)
_NAME_FRAMES = ("f_ask_you_name",)
_ORIGIN_FRAMES = ("f_from_where",)   # → hometown (origin/nationality)
_LIVE_FRAMES = ("frame.location.live_question", "f_live_where")  # → lives_in (legacy id alias)
_WORK_FRAMES = ("f_what_work",)
_COMPANY_FRAMES = ("f_work_company",)
_FAMILY_FRAMES = ("f_have_family", "f_have_siblings")
_FOOD_FRAMES = ("f_food_what_good",)

# frame_id → learner_memory field (for selector: suppress re-ask when fact set and within interval)
FRAME_TO_MEMORY_FIELD: Dict[str, str] = {}
for _fid in _NAME_FRAMES:
    FRAME_TO_MEMORY_FIELD[_fid] = "learner_name"
for _fid in _ORIGIN_FRAMES:
    FRAME_TO_MEMORY_FIELD[_fid] = "hometown"
for _fid in _LIVE_FRAMES:
    FRAME_TO_MEMORY_FIELD[_fid] = "lives_in"
for _fid in _WORK_FRAMES:
    FRAME_TO_MEMORY_FIELD[_fid] = "job_or_study"
for _fid in _COMPANY_FRAMES:
    FRAME_TO_MEMORY_FIELD[_fid] = "job_company"
for _fid in _FAMILY_FRAMES:
    FRAME_TO_MEMORY_FIELD[_fid] = "family"
for _fid in _FOOD_FRAMES:
    FRAME_TO_MEMORY_FIELD[_fid] = "favourite_food"


def get_memory_field_for_frame(frame_id: str) -> Optional[str]:
    """Return the learner_memory field this frame asks for, or None if not an ask-for-fact frame."""
    return FRAME_TO_MEMORY_FIELD.get((frame_id or "").strip())


def _extract_name_from_hanzi(hanzi: str) -> Optional[str]:
    """Extract name from '我叫XXX。' or similar; return None if not recognizable."""
    if not hanzi or not isinstance(hanzi, str):
        return None
    s = hanzi.strip()
    # Strip trailing turn-around phrases before extracting (e.g. "我叫杨利明，你呢？" -> "我叫杨利明")
    s = re.sub(r"[，,]?\s*(那?你呢|你怎么想|为什么这么问)[？?！!。]?\s*$", "", s).strip()
    # Split on period OR Chinese comma so compound answers are trimmed correctly
    first = re.split(r"[。.,，]", s, maxsplit=1)[0].strip()
    # 我叫小明 / 我叫丽丽
    m = re.match(r"我叫\s*(.+?)\s*$", first)
    if m:
        return m.group(1).strip() or None
    if first.startswith("我叫"):
        return first[2:].strip() or None
    return first[:50].strip() or None  # fallback: use as name if short


def _extract_origin_from_hanzi(hanzi: str) -> Optional[str]:
    """Extract origin from '我是XXX人。' → XXX."""
    if not hanzi or not isinstance(hanzi, str):
        return None
    s = hanzi.strip()
    first = re.split(r"[。.]", s, maxsplit=1)[0].strip()
    m = re.match(r"我是\s*(.+?)人\s*$", first)
    if m:
        return m.group(1).strip() or None
    if "人" in first and "我是" in first:
        idx = first.find("我是") + 2
        end = first.rfind("人")
        if end > idx:
            return first[idx:end].strip() or None
    return None


def _extract_city_from_hanzi(hanzi: str) -> Optional[str]:
    """Extract city from '我现在住在XXX。' or '我现在住XXX。' → XXX."""
    if not hanzi or not isinstance(hanzi, str):
        return None
    s = hanzi.strip()
    first = re.split(r"[。.]", s, maxsplit=1)[0].strip()
    # Match 住在XXX and 住XXX (with or without 在, with or without 我/现在 prefix)
    m = re.match(r"(?:我)?(?:现在)?住(?:在)?\s*(.+?)\s*$", first)
    if m:
        return m.group(1).strip() or None
    if "住在" in first:
        idx = first.find("住在") + 2
        return first[idx:].strip() or None
    if "住" in first:
        idx = first.find("住") + 1
        return first[idx:].strip() or None
    return None


def _extract_job_and_company_from_hanzi(hanzi: str) -> tuple:
    """Extract (job_title, company) from work disclosures.

    Handles patterns:
      我(曾经/以前/现在)?是[COMPANY]的[JOB]  →  job=JOB, company=COMPANY
      我(曾经/以前)?是[JOB]                  →  job=JOB, company=None
      我在[COMPANY]工作/上班                  →  job=None, company=COMPANY
    Returns (job, company) — either may be None if not found.
    """
    if not hanzi or not isinstance(hanzi, str):
        return None, None
    s = hanzi.strip()
    first = re.split(r"[。.]", s, maxsplit=1)[0].strip()

    # Pattern: 我(曾经|以前|现在)?是[COMPANY]的[JOB]
    m = re.match(r"我(?:曾经|以前|现在)?是\s*(.+?)\s*的\s*(.+?)\s*$", first)
    if m:
        company_part = m.group(1).strip()
        job_part = m.group(2).strip()
        # Sanity: company should be ≤20 chars, job ≤10 chars
        if job_part and len(job_part) <= 10:
            return job_part or None, company_part[:20] or None

    # Pattern: 我(曾经|以前)?是[JOB]
    m = re.match(r"我(?:曾经|以前)?是\s*(.+?)\s*$", first)
    if m:
        return m.group(1).strip() or None, None

    # Pattern: 我在[COMPANY](工作|上班)
    m = re.match(r"我(?:在|目前在|现在在)\s*(.+?)\s*(?:工作|上班)", first)
    if m:
        return None, m.group(1).strip() or None

    return None, None


def _extract_job_from_hanzi(hanzi: str) -> Optional[str]:
    """Extract job title only (backward compatibility wrapper)."""
    job, _ = _extract_job_and_company_from_hanzi(hanzi)
    return job


def _extract_food_from_hanzi(hanzi: str) -> Optional[str]:
    """Extract dish from '有很多XXX。' → XXX."""
    if not hanzi or not isinstance(hanzi, str):
        return None
    s = hanzi.strip()
    first = re.split(r"[。.]", s, maxsplit=1)[0].strip()
    m = re.match(r"有很多\s*(.+?)\s*$", first)
    if m:
        return m.group(1).strip() or None
    if "有很多" in first:
        idx = first.find("有很多") + 3
        return first[idx:].strip() or None
    return None


def capture_from_turn(
    frame_id: str,
    *,
    selected_option_hanzi: Optional[str] = None,
    selected_option_meaning: Optional[str] = None,
    submitted_text: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Map this turn's answer to learner_memory field updates.
    Returns a dict of { field_name: value } to apply; only includes fields we can set unambiguously.
    """
    updates: Dict[str, Optional[str]] = {}
    fid = (frame_id or "").strip()
    hanzi = (selected_option_hanzi or "").strip() if selected_option_hanzi else ""
    meaning = (selected_option_meaning or "").strip() if selected_option_meaning else ""
    text = (submitted_text or "").strip() if submitted_text else ""

    # Prefer selected option hanzi; fall back to submitted text for name/slot answers
    value_hanzi = hanzi or text
    value_any = value_hanzi or meaning

    if not fid:
        return updates

    if fid in _NAME_FRAMES:
        name = _extract_name_from_hanzi(value_hanzi) if value_hanzi else _extract_name_from_hanzi(text)
        if name:
            updates["learner_name"] = name

    elif fid in _ORIGIN_FRAMES:
        origin = _extract_origin_from_hanzi(value_hanzi)
        if origin:
            updates["hometown"] = origin

    elif fid in _LIVE_FRAMES:
        city = _extract_city_from_hanzi(value_hanzi)
        if city:
            updates["lives_in"] = city

    elif fid in _WORK_FRAMES:
        job, company = _extract_job_and_company_from_hanzi(value_hanzi)
        if job:
            updates["job_or_study"] = job
        # If company was embedded in the job disclosure (e.g. "我曾经是富士通的首席信息官"),
        # capture it now so f_work_company can be suppressed as already-known.
        if company:
            updates["job_company"] = company

    elif fid in _COMPANY_FRAMES:
        # Direct answer to "你在哪个公司上班?" — store as-is
        if value_hanzi:
            updates["job_company"] = value_hanzi

    elif fid in _FAMILY_FRAMES:
        if value_any:
            updates["family"] = value_hanzi or meaning

    elif fid in _FOOD_FRAMES:
        food = _extract_food_from_hanzi(value_hanzi)
        if food:
            updates["favourite_food"] = food

    return updates

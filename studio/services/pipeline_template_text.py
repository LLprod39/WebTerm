from __future__ import annotations

import re
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalise_query(value: str) -> str:
    return re.sub(r"\s+", " ", _text(value).lower())


def _contains_term(haystack: str, term: str) -> bool:
    needle = _normalise_query(term)
    if not needle:
        return False
    if len(needle) <= 3 and re.fullmatch(r"[a-z0-9]+", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None
    return needle in haystack

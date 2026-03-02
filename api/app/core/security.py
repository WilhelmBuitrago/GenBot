from __future__ import annotations

import re


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_text(value: str, max_length: int = 2000) -> str:
    cleaned = _CONTROL_CHARS.sub("", value).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned

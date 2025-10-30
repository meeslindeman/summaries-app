import hashlib
from typing import List

def sha1(text: str) -> str:
    """Stable short hash of text for deduplication."""
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()

def match_keywords(text: str, includes: List[str], excludes: List[str]) -> bool:
    """Return True if text matches include/exclude rules."""
    t = text.casefold()
    if excludes and any(x.casefold() in t for x in excludes):
        return False
    if includes and not any(x.casefold() in t for x in includes):
        return False
    return True

def should_skip(url: str, title: str, text: str, includes: List[str], excludes: List[str]) -> bool:
    """Convenience wrapper to apply filters."""
    combined = f"{url}\n{title}\n{text}"
    return not match_keywords(combined, includes, excludes)

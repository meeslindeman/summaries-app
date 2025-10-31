# app/filters.py
from __future__ import annotations
import re
from typing import List, Dict, Tuple
from urllib.parse import urlsplit
import hashlib


WORD_BOUNDARY = r"(?:^|[^A-Za-z0-9_])"  # simple non-word boundary

def _domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host.lstrip("www.")

def _parse_lines(lines: List[str]) -> Tuple[List[str], Dict[str, List[str]]]:
    """Split rules into global list and per-domain map: domain -> [terms]."""
    globals_: List[str] = []
    per_dom: Dict[str, List[str]] = {}
    for raw in lines or []:
        ln = (raw or "").strip()
        if not ln or ln.startswith("#"):
            continue
        if ":" in ln and not ln.startswith('"'):
            # "domain: term" (allow spaces around :)
            dom, term = ln.split(":", 1)
            dom = dom.strip().lower().lstrip("www.")
            term = term.strip()
            if term:
                per_dom.setdefault(dom, []).append(term)
        else:
            globals_.append(ln)
    return globals_, per_dom

def _make_pattern(term: str) -> re.Pattern:
    """Quoted strings become exact phrase; otherwise word-boundary match."""
    if len(term) >= 2 and term[0] == term[-1] == '"':
        phrase = re.escape(term[1:-1].strip())
        return re.compile(phrase, re.IGNORECASE)
    core = re.escape(term)
    return re.compile(rf"{WORD_BOUNDARY}{core}{WORD_BOUNDARY}", re.IGNORECASE)

def _any_match(text: str, terms: List[str]) -> bool:
    if not terms or not text:
        return False
    for t in terms:
        if _make_pattern(t).search(text):
            return True
    return False

def compile_rules(include_lines: List[str], exclude_lines: List[str]):
    """Prepare a reusable rules object from raw lines (include.txt/exclude.txt)."""
    inc_global, inc_per = _parse_lines(include_lines or [])
    exc_global, exc_per = _parse_lines(exclude_lines or [])
    return {
        "inc_global": inc_global,
        "inc_per": inc_per,
        "exc_global": exc_global,
        "exc_per": exc_per,
    }

def should_keep(url: str, title: str, body: str, rules) -> bool:
    """
    Keep an article if:
      1) No exclude matches (global or per-domain), and
      2) If include lists exist (global+per-domain), at least one include matches.
         If no includes defined at all, keep by default.
    Matching happens against (title + body), case-insensitive.
    """
    dom = _domain(url)
    text = f"{title or ''}\n{body or ''}"

    # Excludes: per-domain + global
    exc_terms = (rules.get("exc_per", {}).get(dom, []) or []) + (rules.get("exc_global") or [])
    if _any_match(text, exc_terms):
        return False

    # Includes: if any exist, require a hit (per-domain + global)
    inc_terms = (rules.get("inc_per", {}).get(dom, []) or []) + (rules.get("inc_global") or [])
    if inc_terms:
        return _any_match(text, inc_terms)

    # No includes configured => keep by default
    return True


def sha1(text: str) -> str:
    """Return a short, stable SHA-1 hash for deduplication."""
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()
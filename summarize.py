import argparse
import os
import sys
from typing import List, Dict, Any

import feedparser
import trafilatura
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    print("Missing OPENAI_API_KEY in environment.", file=sys.stderr)
    sys.exit(1)

client = OpenAI(api_key=API_KEY)

SYSTEM_INSTRUCTIONS = (
    "You are a factual summarizer. Write one coherent paragraph (max 100 words) "
    "explaining the main story, events, and implications of the article. "
    "Base all facts strictly on the text provided. Include no bullet points or lists."
)

def fetch_main_text(url: str) -> str:
    downloaded = trafilatura.fetch_url(url, no_ssl=True)
    if not downloaded:
        return ""
    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_images=False,
        include_tables=False,
        favor_precision=True,
    )
    return text or ""

def summarize(url: str, title: str, text: str) -> Dict[str, Any]:
    import json, re

    schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "title": {"type": "string"},
            "bullets": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            "why": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        },
        "required": ["url", "title", "bullets", "why"],
        "additionalProperties": False,
    }

    capped = (text or "")[:12000]

    # Prefer Structured Outputs if available
    try:
        resp = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "system",
                    "content": "You output JSON that matches the provided schema. No prose.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text",
                         "text": (
                             "Schema:\n"
                             + json.dumps(schema)
                             + "\n\nReturn ONLY a JSON object matching this schema."
                             f"\nURL: {url}\nTITLE: {title}\n\nARTICLE:\n{capped}"
                         )
                        }
                    ],
                },
            ],
            temperature=0,
            max_output_tokens=400,
        )
        raw = resp.output_text  # single concatenated string
    except Exception as e:
        # Fallback: older SDKs can still return output_text; if not, rethrow
        raise

    # Parse JSON robustly
    def parse_json_maybe(s: str) -> Dict[str, Any]:
        s = s.strip()
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            # Try to extract the first {...} block
            m = re.search(r"\{.*\}", s, flags=re.S)
            if m:
                return json.loads(m.group(0))
            raise

    data = parse_json_maybe(raw)

    # Fill url/title if missing
    data.setdefault("url", url)
    data.setdefault("title", title)
    # Guard rails
    data["bullets"] = list(data.get("bullets", []))[:5]
    data["tags"] = list(data.get("tags", []))[:8]
    return data


def parse_feed(feed_url: str, limit: int) -> List[Dict[str, str]]:
    fp = feedparser.parse(feed_url)
    items = []
    for e in fp.entries[:limit]:
        link = e.get("link") or ""
        title = e.get("title") or "(no title)"
        items.append({"url": link, "title": title})
    return items

def main():
    ap = argparse.ArgumentParser(description="Summarize an RSS feed with OpenAI.")
    ap.add_argument("--feed", required=True, help="RSS/Atom feed URL")
    ap.add_argument("--limit", type=int, default=5, help="Max items to summarize")
    ap.add_argument("--skip-empty", action="store_true", help="Skip articles with no extracted text")
    args = ap.parse_args()

    items = parse_feed(args.feed, args.limit)
    if not items:
        print("No items found.", file=sys.stderr)
        sys.exit(2)

    for i, it in enumerate(items, 1):
        url, title = it["url"], it["title"]
        text = fetch_main_text(url)
        if not text and args.skip_empty:
            print(f"[{i}] Skipped (no extractable text): {title}")
            continue
        try:
            summary = summarize(url, title, text)
        except Exception as ex:
            print(f"[{i}] Error summarizing {url}: {ex}", file=sys.stderr)
            continue

        # Pretty print
        print(f"\n[{i}] {summary['title']}")
        print(summary.get("url", ""))
        bullets = summary.get("bullets", [])
        for b in bullets:
            print(f"  - {b}")
        if "why" in summary:
            print(f"Why it matters: {summary['why']}")
        tags = summary.get("tags") or []
        if tags:
            print("Tags:", ", ".join(tags))

if __name__ == "__main__":
    main()

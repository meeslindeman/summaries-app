import json, re
from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = (
    "You are a factual summarizer. Write one coherent paragraph (120–160 words) "
    "that captures the article's main events, facts, and context. Be strictly extractive. "
    "Then produce 2–4 concise takeaways as short sentences, each a specific fact or implication. "
    "Return ONLY valid JSON with keys: url, title, summary, takeaways[], tags[]. "
    "Do not include analysis not present in the text."
)

def summarize_article(url: str, title: str, text: str) -> dict:
    capped = (text or "")[:settings.input_char_cap]

    resp = client.responses.create(
        model=settings.openai_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": [
                 {"type": "input_text",
                  "text": (
                      'Return JSON only:\n'
                      '{"url": str, "title": str, "summary": str, "takeaways": [str,...], "tags": [str,...]}\n'
                      f"URL: {url}\nTITLE: {title}\n\nARTICLE:\n{capped}"
                  )}
             ]},
        ],
        temperature=0,
        max_output_tokens=max(360, settings.max_output_tokens),
    )

    raw = resp.output_text.strip()

    def parse_json_safe(s: str) -> dict:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", s, re.S)
            if not m:
                raise
            return json.loads(m.group(0))

    data = parse_json_safe(raw)
    # normalize and clamp
    data.setdefault("url", url)
    data.setdefault("title", title)
    data["summary"] = " ".join((data.get("summary") or "").split())
    tks = data.get("takeaways") or []
    data["takeaways"] = [str(x).strip() for x in tks if str(x).strip()][:4]
    data["tags"] = list(data.get("tags", []))[:8]
    return data

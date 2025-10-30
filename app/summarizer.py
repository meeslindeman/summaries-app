import json, re, time
from openai import OpenAI
from openai import APIStatusError, APIConnectionError, RateLimitError
from app.config import settings
from app.logging import setup

log = setup()
client = OpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = (
    "You are a factual summarizer. Write one coherent paragraph (120–160 words) "
    "that captures the article's main events, facts, and context. Be strictly extractive. "
    "Then produce 2–4 concise takeaways as short sentences, each a specific fact or implication. "
    "Return ONLY valid JSON with keys: url, title, summary, takeaways[], tags[]. "
    "Do not include analysis not present in the text."
)

def _parse_json_safe(s: str) -> dict:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            raise
        return json.loads(m.group(0))

def summarize_article(url: str, title: str, text: str) -> dict:
    capped = (text or "")[:settings.input_char_cap]

    backoff = 0.5
    for attempt in range(1, 4):
        try:
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
            data = _parse_json_safe(raw)
            break
        except (APIConnectionError, RateLimitError, APIStatusError) as e:
            log.warning("LLM error %s on attempt %d for %s", type(e).__name__, attempt, url)
            time.sleep(backoff)
            backoff *= 2
        except Exception as e:
            # unrecoverable parse or other error
            raise

    # normalize
    data.setdefault("url", url)
    data.setdefault("title", title)
    data["summary"] = " ".join((data.get("summary") or "").split())
    tks = data.get("takeaways") or []
    data["takeaways"] = [str(x).strip() for x in tks if str(x).strip()][:4]
    data["tags"] = list(data.get("tags", []))[:8]
    return data

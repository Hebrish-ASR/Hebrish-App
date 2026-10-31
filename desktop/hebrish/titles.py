"""Transcript titles (B-75, Daniel 2026-10-31): a small title model, an optional add-on in
Models → Utilities, writes a short title for each saved transcript (transcripts.py puts it in the
file name, the front matter and the H1).

Model (chosen 2026-10-31, see the catalogue entry's `_doc`): gghfez/openwebui-title-generator-270m,
a Gemma 3 270M fine-tune trained on Open WebUI's title task. Catalogue `addons`, kind `text_title`;
downloaded and run exactly like the clean-up models (cleanup.download / cleanup.server: the same
pinned llama-server build, its own process). Rejected in the same test: S1-mini (ignores a title
instruction and cleans the text instead), Supra-Title-350M-exp ("Hebrish" became "Hebride"),
Supra-Title-50M ("Hbrish").

- Prompt: Open WebUI's default title prompt (what the model was trained on), the transcript as the
  user turn, in Gemma's chat template. Greedy, at most N_PREDICT tokens, the first INPUT_WORDS words.
- Output: JSON `{"title": "..."}` with an emoji or two. `clean()` is deterministic: the JSON value
  (or the raw line), emojis and symbols dropped, quotes and a final full stop stripped, spaces
  collapsed, then `fit()` to the user's limit (cfg `title_max_chars`, default 60) at a word end.
- Never blocks a save: any failure, or nothing left after cleaning, returns None and the
  transcript is saved by its time alone.

No Qt import: tested in tests/test_titles.py.
"""

import json
import re
import unicodedata

from . import cleanup

KIND = "text_title"
INPUT_WORDS = 1200
N_PREDICT = 40
TIMEOUT_S = 60.0
MAX_CHARS = 60           # default for cfg title_max_chars
MIN_CHARS, MAX_CHARS_LIMIT = 16, 120
END = "<end_of_turn>"

PROMPT = """### Task:
Generate a concise, 3-5 word title with an emoji summarizing the chat history.
### Guidelines:
- The title should clearly represent the main theme or subject of the conversation.
- Use emojis that enhance understanding of the topic, but avoid quotation marks or special formatting.
- Write the title in the chat's primary language; default to English if multilingual.
- Prioritize accuracy over excessive creativity; keep it clear and simple.
### Output:
JSON format: { "title": "your concise title here" }
### Chat History:
<chat_history>
USER: {text}
</chat_history>"""


def render_prompt(text: str) -> str:
    words = text.split()
    body = " ".join(words[:INPUT_WORDS])
    return (f"<start_of_turn>user\n{PROMPT.replace('{text}', body)}{END}\n"
            "<start_of_turn>model\n")


_KEEP_PUNCT = set("&-'’,:+/.#")


def _strip_symbols(s: str) -> str:
    """Letters, digits, spaces and a little punctuation; emojis and other symbols go."""
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat[0] in "LN" or ch in _KEEP_PUNCT:
            out.append(ch)
        elif cat[0] == "Z" or ch in "\t\n":
            out.append(" ")
        # S* (symbols, emojis), Cf (zero-width joiners, variation selectors), other P*: dropped
    return "".join(out)


def fit(title: str, max_chars: int = MAX_CHARS) -> str:
    """`title` cut to at most `max_chars` at a word end, without a dangling joiner."""
    title = " ".join(title.split())
    if len(title) > max_chars:
        cut = title[:max_chars + 1]
        title = cut[:cut.rfind(" ")] if " " in cut else title[:max_chars]
    words = title.split()
    while words and (words[-1].lower() in {"&", "and", "-", "or", "of", "the", "a", "for", "with", "to"}
                     or not any(c.isalnum() for c in words[-1])):
        words.pop()
    return " ".join(words).rstrip(",:-/ ")


def clean(raw: str, max_chars: int = MAX_CHARS) -> str:
    """The model's reply as a plain title, '' when nothing usable is left."""
    raw = raw.replace(END, "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw).strip()
    text = None
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            v = json.loads(m.group(0)).get("title")
            text = v if isinstance(v, str) else None
        except (ValueError, AttributeError):
            m2 = re.search(r'"title"\s*:\s*"([^"]*)', raw)
            text = m2.group(1) if m2 else None
    if text is None and '"title"' in raw:            # cut off before the closing quote or brace
        m2 = re.search(r'"title"\s*:\s*"([^"]*)', raw)
        text = m2.group(1) if m2 else None
    if text is None:
        text = raw.splitlines()[0] if raw else ""
    t = _strip_symbols(text)
    t = " ".join(t.split()).strip(" '’\"“”").rstrip(".")
    if not any(c.isalpha() for c in t):
        return ""
    return fit(t, max_chars)


def limit(v) -> int:
    """cfg title_max_chars, kept in MIN_CHARS..MAX_CHARS_LIMIT."""
    try:
        return max(MIN_CHARS, min(MAX_CHARS_LIMIT, int(v)))
    except (TypeError, ValueError):
        return MAX_CHARS


def entries() -> list[dict]:
    return cleanup.entries(KIND)


def ready() -> dict | None:
    """The title model's entry when it is downloaded, else None."""
    for e in entries():
        if cleanup.installed(e["id"]) is not None:
            return e
    return None


def make(text: str, client, max_chars: int = MAX_CHARS) -> str | None:
    """A title for `text` from `client` (cleanup.Server or a fake: complete(prompt, n, timeout,
    stop)). None on any failure or an empty result."""
    if not text.strip():
        return None
    try:
        content, _stop = client.complete(render_prompt(text), N_PREDICT, TIMEOUT_S, stop=(END,))
    except Exception:
        return None
    return clean(content, max_chars) or None


def title(text: str, max_chars: int = MAX_CHARS) -> str | None:
    """A title from the installed title model, or None (not downloaded, or it failed)."""
    e = ready()
    if e is None:
        return None
    try:
        s = cleanup.server(e["id"])
    except Exception:
        return None
    return make(text, s, max_chars)

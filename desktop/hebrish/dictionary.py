"""Personal dictionary (0.8.0): words the user wants written a certain way, applied to the model's
text after decoding. The rules are shared with Android: ../shared/personal-dictionary.md, test set
../shared/dictionary-cases.json (tests/test_dictionary.py)."""

import re
import threading
from collections import Counter

from .config import CONFIG_DIR, load_json, save_json

PATH = CONFIG_DIR / "dictionary.json"     # {"schema": 1, "words": [{"word": ..., "heard": [...]}]}
_SEP = r"[\s\-']?"                       # rule 4: one space, hyphen or apostrophe between two letters/digits
_write = threading.Lock()                # add/remove read, change and save: the window and the local API


def load(path=None) -> list[dict]:
    """The entries, cleaned: word and heard-as phrases trimmed, empty ones dropped (rule 7)."""
    data = load_json(path or PATH, {})
    words = data.get("words", []) if isinstance(data, dict) else []
    return clean(words)


def save(entries, path=None):
    save_json(path or PATH, {"schema": 1, "words": clean(entries)})


def clean(entries) -> list[dict]:
    out = []
    for e in entries:
        word = str(e.get("word", "")).strip() if isinstance(e, dict) else ""
        if word:
            heard = [h.strip() for h in e.get("heard") or [] if isinstance(h, str) and h.strip()]
            out.append({"word": word, "heard": heard})
    return out


def _word_pattern(word: str) -> str:
    """Rule 4: the word, with one optional separator between adjacent letters/digits when it has
    four or more of them; whitespace inside it matches any run of whitespace."""
    split = sum(c.isalnum() for c in word) >= 4
    out = []
    for i, c in enumerate(word):
        if c.isspace():
            if not out or out[-1] != r"\s+":
                out.append(r"\s+")
            continue
        if split and i and c.isalnum() and word[i - 1].isalnum():
            out.append(_SEP)
        out.append(re.escape(c))
    return "".join(out)


def _phrase_pattern(phrase: str) -> str:
    """Rule 3: the phrase literally; whitespace runs match any whitespace run."""
    return r"\s+".join(re.escape(p) for p in phrase.split())


def _compiled(entries):
    """(regex, its alternatives, sub function) for `entries`, or None when there are none."""
    alts = []             # (source length, pattern, word, is the word itself)
    for e in clean(entries):
        alts.append((len(e["word"]), _word_pattern(e["word"]), e["word"], True))
        alts += [(len(h), _phrase_pattern(h), e["word"], False) for h in e["heard"]]
    if not alts:
        return None
    alts.sort(key=lambda a: -a[0])      # rule 6: longest source first (stable: dictionary order on ties)
    rx = re.compile(r"(?<!\w)(?:" + "|".join(f"({a[1]})" for a in alts) + r")(?!\w)", re.IGNORECASE)

    def sub(m):
        _, _, word, itself = alts[m.lastindex - 1]
        found = m.group(0)
        if word != word.lower():          # rule 5: a word with a capital is written as in the dictionary
            return word
        if itself and " ".join(found.lower().split()) == " ".join(word.split()):
            return found                  # same characters: the model's case stays
        return word[:1].upper() + word[1:] if found[:1].isupper() else word

    return rx, sub


def compile(entries):
    """A function text -> text applying `entries` (rules 1-7), or `str` when there are none."""
    parts = _compiled(entries)
    if parts is None:
        return str
    rx, sub = parts
    return lambda text: rx.sub(sub, text)


def add(word: str, heard=(), path=None) -> tuple[dict, bool]:
    """Add a word, or add heard-as phrases to the word already there (same spelling, exact case):
    unlike the Dictionary tab's form this never drops phrases. Returns (the entry, is it new)."""
    new = clean([{"word": word, "heard": list(heard)}])
    if not new:
        raise ValueError("word is empty")
    new = new[0]
    with _write:
        entries = load(path)
        old = next((e for e in entries if e["word"] == new["word"]), None)
        if old:
            have = {h.lower() for h in old["heard"]}
            old["heard"] += [h for h in new["heard"] if h.lower() not in have]
        else:
            entries.append(new)
        save(entries, path)
    return (old or new), old is None


def remove(word: str, heard: str | None = None, path=None) -> bool:
    """Remove a word, or only one of its heard-as phrases. False when there was nothing to remove."""
    with _write:
        entries = load(path)
        e = next((e for e in entries if e["word"] == word), None)
        if e is None:
            return False
        if heard is None:
            entries.remove(e)
        else:
            kept = [h for h in e["heard"] if h.lower() != heard.strip().lower()]
            if len(kept) == len(e["heard"]):
                return False
            e["heard"] = kept
        save(entries, path)
    return True


def preview(entries, rows, limit: int = 20, context: int = 40) -> dict:
    """What `entries` would change in `rows` ((id, at, text), e.g. history.texts()), counting only
    real changes: `by_source` is how often each form was found, the way to spot a rule that is too
    broad. Nothing is written."""
    out = {"rows_scanned": 0, "rows_changed": 0, "replacements": 0, "by_source": {}, "samples": []}
    parts = _compiled(entries)
    if parts is None:
        return out
    rx, sub = parts
    seen = Counter()
    for rid, at, text in rows:
        out["rows_scanned"] += 1
        hits = [m for m in rx.finditer(text) if sub(m) != m.group(0)]
        if not hits:
            continue
        out["rows_changed"] += 1
        out["replacements"] += len(hits)
        seen.update(m.group(0) for m in hits)
        if len(out["samples"]) < limit:
            m = hits[0]
            a, b = max(0, m.start() - context), m.end() + context
            out["samples"].append({"id": rid, "at": at, "before": text[a:b],
                                   "after": text[a:m.start()] + sub(m) + text[m.end():b]})
    out["by_source"] = dict(seen.most_common())
    return out

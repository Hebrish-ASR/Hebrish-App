"""Personal dictionary (0.8.0): words the user wants written a certain way, applied to the model's
text after decoding. The rules are shared with Android: ../shared/personal-dictionary.md, test set
../shared/dictionary-cases.json (tests/test_dictionary.py)."""

import re

from .config import CONFIG_DIR, load_json, save_json

PATH = CONFIG_DIR / "dictionary.json"     # {"schema": 1, "words": [{"word": ..., "heard": [...]}]}
_SEP = r"[\s\-']?"                       # rule 4: one space, hyphen or apostrophe between two letters/digits


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


def compile(entries):
    """A function text -> text applying `entries` (rules 1-7), or `str` when there are none."""
    alts = []             # (source length, pattern, word, is the word itself)
    for e in clean(entries):
        alts.append((len(e["word"]), _word_pattern(e["word"]), e["word"], True))
        alts += [(len(h), _phrase_pattern(h), e["word"], False) for h in e["heard"]]
    if not alts:
        return str
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

    return lambda text: rx.sub(sub, text)

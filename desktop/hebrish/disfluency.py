"""Disfluency chop (1.001): hesitation sounds (um, uh, eh, er, hmm) removed from the model's text
right after decoding, always, for every model; from 1.007 also repeated words (stutters, false
starts) and the ellipses the models write for a trailing-off thought. The rules are shared with
Android: ../shared/disfluencies.md, test set ../shared/disfluency-cases.json (tests/test_disfluency.py)."""

import re

_NEXT = r"[\w'’-]"         # a letter, digit, apostrophe or hyphen beside it: part of a longer word
_FILLER = re.compile(rf"([ \t]*)(?<!{_NEXT})(u+h+m*|u+m+|e+h+m*|er|e+r+m+|h+m+)(?!{_NEXT})([,;]?)",
                     re.IGNORECASE)
_SENTENCE_START = re.compile(r"(?:^|[.!?])\s*$")
_AFTER_START = re.compile(r"[,;.…!?]*\s*")
_CAP = "\x00"                 # marks "capitalise the next letter" while the text is rebuilt


def chop(text: str, before: str = "") -> str:
    """`text` without its fillers (rules 1-4 of disfluencies.md), repeated words and phrases
    (rules 5-7) and ellipses (rule 8). `before`: the take's text already out, for a repeat across the seam."""
    return _ellipses(_phrases(_repeats(_fillers(text), before)))


def _fillers(text: str) -> str:
    out, pos = [], 0
    while m := _FILLER.search(text, pos):
        word = m.group(2)
        if len(word) > 1 and word.isupper():        # ER, UM in capitals: an abbreviation
            out.append(text[pos:m.end()])
            pos = m.end()
            continue
        out.append(text[pos:m.start()])
        pos = m.end()
        if _SENTENCE_START.search("".join(out).replace(_CAP, "")):   # rule 2: keep the spaces before, take the marks after
            out.append(m.group(1))
            pos = _AFTER_START.match(text, pos).end()
        if word[0].isupper():                      # rule 3
            out.append(_CAP)
    if not out:
        return text
    out.append(text[pos:])
    result = re.sub(_CAP + r"([^\w]*?)([^\W\d_])", lambda c: c.group(1) + c.group(2).upper(), "".join(out))
    result = result.replace(_CAP, "")
    result = re.sub(r",\s*([.!?])", r"\1", result)     # rule 4
    result = re.sub(r"[ \t]+([,.!?;:])", r"\1", result)
    return result if re.search(r"[^\W_]", result) else ""


# Repeated words (1.007, Daniel 2026-10-27: "I really wanted, wanted to go home", "could we change,
# change, change? change the dataset"). A word said twice on purpose is kept twice when it is one of
# these (intensifiers, doubles English grammar allows, Hebrew doubles), or a number; never more.
KEEP_TWICE = frozenset("""really very so no yes yeah bye ha haha much more many far long ever again had that
is was do did now well there too round around over out on off up down go come knock hey okay ok
please quick slowly bit little away tov ken lo yalla nu dai kol od""".split())
# Numbers are never cut: "five five five" is a phone number.
NUMBERS = frozenset("zero oh one two three four five six seven eight nine ten double triple".split())
_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")
_SOFT_GAP = re.compile(r"[ \t]*(?:[,;]|…|\.{3,})?[ \t]*")      # between two words of one run
_MARK_GAP = re.compile(r"[ \t]*[.?!][ \t]+")                     # ... or a sentence mark, if the next word is lower case
_ELLIPSIS = re.compile(r"[ \t]*(?:…|\.{3,})([ \t]*)")


def _same_run(a: str, gap: str, b: str) -> bool:
    return a.casefold() == b.casefold() and bool(
        _SOFT_GAP.fullmatch(gap) or (_MARK_GAP.fullmatch(gap) and b[0].islower()))


def _twice_ok(word: str) -> bool:
    w = word.casefold()
    return w in KEEP_TWICE or w in NUMBERS or any(c.isdigit() for c in word)


def _repeats(text: str, before: str = "") -> str:
    """Rules 5-7: a run of the same word is cut to one (two for KEEP_TWICE words said at least
    twice); a piece that starts with the word the last piece ended on drops it, unless KEEP_TWICE."""
    words = list(_WORD.finditer(text))
    if not words:
        return text
    cut = []                       # (start, end) spans to delete
    if before:
        prev = list(_WORD.finditer(before))
        tail = before[prev[-1].end():] if prev else ""
        if prev and not tail.strip(" \t,;") and prev[-1].group().casefold() == words[0].group().casefold() \
                and not _twice_ok(words[0].group()):
            nxt = words[1].start() if len(words) > 1 else len(text)
            lead = text[:words[0].start()]
            cut.append((len(lead), nxt))
            words = words[1:]
    i = 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and _same_run(words[j].group(), text[words[j].end():words[j + 1].start()],
                                               words[j + 1].group()):
            j += 1
        n = j - i + 1
        w = words[i].group()
        if n >= 2 and w.casefold() not in NUMBERS and not any(c.isdigit() for c in w):
            keep = 2 if _twice_ok(w) else 1
            if n > keep:
                # keep the first `keep` words as written, drop through the end of the last one
                cut.append((words[i + keep - 1].end(), words[j].end()))
        i = j + 1
    if not cut:
        return text
    out, pos = [], 0
    for a, b in cut:
        out.append(text[pos:a])
        pos = b
    out.append(text[pos:])
    return "".join(out)


def _phrases(text: str) -> str:
    """Rule 7: a phrase of two or three words said again straight away is a false start: "it was,
    it was fine" -> "it was fine". The longer phrase is tried first; numbers are never cut."""
    for k in (3, 2):
        while True:
            words = list(_WORD.finditer(text))
            for i in range(len(words) - 2 * k + 1):
                one, two = words[i:i + k], words[i + k:i + 2 * k]
                if [w.group().casefold() for w in one] != [w.group().casefold() for w in two]:
                    continue
                if all(w.group().casefold() in NUMBERS or any(c.isdigit() for c in w.group()) for w in one):
                    continue
                gap = text[one[-1].end():two[0].start()]
                if _SOFT_GAP.fullmatch(gap) or (_MARK_GAP.fullmatch(gap) and two[0].group()[0].islower()):
                    text = text[:one[-1].end()] + text[two[-1].end():]
                    break
            else:
                break
    return text


def _ellipses(text: str) -> str:
    """Rule 8: an ellipsis (… or ...) is a thought trailing off, not punctuation to keep. Before a
    lower-case word it becomes a space; before a capital, a mark or the end of the piece, a full
    stop (none if a mark already follows)."""
    if "…" not in text and "..." not in text:
        return text

    def fix(m):
        rest = text[m.end():]
        if rest[:1].islower() or rest[:1].isdigit():
            return " "
        if rest[:1] and rest[0] in ".?!,;:":
            return ""
        return "." + m.group(1)
    return _ELLIPSIS.sub(fix, text)

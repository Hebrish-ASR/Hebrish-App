"""Disfluency chop (1.001): hesitation sounds (um, uh, eh, er, hmm) removed from the model's text
right after decoding, always, for every model. The rules are shared with Android:
../shared/disfluencies.md, test set ../shared/disfluency-cases.json (tests/test_disfluency.py)."""

import re

_NEXT = r"[\w'’-]"         # a letter, digit, apostrophe or hyphen beside it: part of a longer word
_FILLER = re.compile(rf"([ \t]*)(?<!{_NEXT})(u+h+m*|u+m+|e+h+m*|er|e+r+m+|h+m+)(?!{_NEXT})([,;]?)",
                     re.IGNORECASE)
_SENTENCE_START = re.compile(r"(?:^|[.!?])\s*$")
_AFTER_START = re.compile(r"[,;.…!?]*\s*")
_CAP = "\x00"                 # marks "capitalise the next letter" while the text is rebuilt


def chop(text: str) -> str:
    """`text` without its fillers (rules 1-4 of disfluencies.md)."""
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

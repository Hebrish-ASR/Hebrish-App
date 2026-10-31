"""Saved transcripts (B-74, Daniel 2026-10-31): Save writes straight to a transcripts folder, no
file dialog. Default <Hebrish folder>/transcripts (cfg `transcripts_dir` "" = default), changed
in Settings → Your data. Layout: <folder>/YYYY/MM/DD/<stem>.md.

Names: `HH-MM-SS` (the transcript's time), or `<title>_HH-MM-SS` with a title, in snake_case
(`slug`). A stem already taken (its .md or .json) gets `-2`, `-3`, … so nothing is overwritten.
Titles come from the title model (titles.py, B-75), when it is downloaded.

Each file (2026-10-31, Daniel: "title as a H1, the timestamp as a H2, generated on this date by
Hebrish using the model, YAML front matter"):

    ---
    title: "Hebrish Android Mic Fix"
    date: 2026-10-31T14:05:09+02:00
    version: transcript            # transcript | raw | cleaned (VERSIONS)
    generator: Hebrish 1.014
    model: Sabich v2.3
    ...
    versions: hebrish_android_mic_fix_14-05-09.json
    ---

    # Hebrish Android Mic Fix

    ## Friday 31 October 2026, 14:05

    *Transcribed by Hebrish 1.014 with Sabich v2.3 on 31 October 2026.*

    <text>

A transcript can have several versions, each its own file beside the first, never overwritten
(Daniel: "we always keep the original one"): `transcript` (<stem>.md, what was in the box when it
was saved, edits included), `raw` (<stem>.raw.md, as the model transcribed it, before clean-up and
edits; written only when it differs) and `cleaned` (<stem>.cleaned.md, -2, …: a clean-up model's
copy). <stem>.json links them (MANIFEST_SCHEMA): the shared details and one entry per version.

No Qt import: tested in tests/test_transcripts.py.
"""

import json
import re
import time
import unicodedata
from pathlib import Path

from . import config

SLUG_MAX = 60
MANIFEST_SCHEMA = 1
VERSIONS = ("transcript", "raw", "cleaned")
SUFFIX = {"transcript": "", "raw": ".raw", "cleaned": ".cleaned"}
UNTITLED = "Transcript"


def default_dir() -> Path:
    return config.default_files_root() / "transcripts"


def folder(setting: str) -> Path:
    """`setting` is the resolved folder (config.transcripts_folder(cfg)) or a bare transcripts_dir."""
    return Path(setting).expanduser() if setting else default_dir()


def slug(title: str) -> str:
    """'Notes on the API, v2!' -> 'notes_on_the_api_v2'. ASCII only (romanized text); at most
    SLUG_MAX characters, cut at a word end. '' when nothing is left."""
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", t)
    out = ""
    for w in words:
        nxt = f"{out}_{w}" if out else w
        if len(nxt) > SLUG_MAX:
            break
        out = nxt
    return out or (words[0][:SLUG_MAX] if words else "")


def path_for(base: Path, when: float | None = None, title: str | None = None) -> Path:
    """Where a transcript from `when` (epoch seconds; default now) goes: <stem>.md, with neither
    it nor <stem>.json taken. Not created."""
    tm = time.localtime(when if when is not None else time.time())
    day = base / time.strftime("%Y", tm) / time.strftime("%m", tm) / time.strftime("%d", tm)
    stamp = time.strftime("%H-%M-%S", tm)
    s = slug(title) if title else ""
    stem = f"{s}_{stamp}" if s else stamp
    p, n = day / stem, 2
    while p.with_suffix(".md").exists() or p.with_suffix(".json").exists():
        p = day / f"{stem}-{n}"
        n += 1
    return p.with_suffix(".md")


def iso(when: float) -> str:
    """2026-10-31T14:05:09+02:00 (local time with its offset)."""
    t = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(when))
    return t[:-2] + ":" + t[-2:]


def _day(when: float) -> str:
    tm = time.localtime(when)
    return f"{tm.tm_mday} {time.strftime('%B %Y', tm)}"


def _yaml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(round(v, 1)) if isinstance(v, float) else str(v)
    return json.dumps(str(v), ensure_ascii=False)       # a JSON string is a valid YAML scalar


def render(text: str, title: str | None, when: float, meta: dict | None = None,
           version: str = "transcript", manifest: str | None = None, extra: dict | None = None) -> str:
    """The Markdown file: YAML front matter, `# title`, `## date, time`, the credit line, the text.
    meta: generator ("Hebrish 1.014"), model ("Sabich v2.3"), audio_seconds, source; extra: keys
    for this version only (cleanup_model, …). Empty values are left out."""
    meta = meta or {}
    fm = {"title": title or "", "date": iso(when), "version": version, **meta, **(extra or {}),
          "versions": manifest or ""}
    plain = ("date", "version")                    # ISO date and a fixed word: no quotes needed
    lines = ["---"] + [f"{k}: {v if k in plain else _yaml(v)}" for k, v in fm.items()
                       if v not in (None, "")] + ["---", ""]
    tm = time.localtime(when)
    lines += [f"# {title.strip() if title and title.strip() else UNTITLED}", "",
              f"## {time.strftime('%A', tm)} {_day(when)}, {time.strftime('%H:%M', tm)}", ""]
    gen, model = meta.get("generator") or "Hebrish", meta.get("model")
    what = {"raw": "Transcribed", "transcript": "Transcribed", "cleaned": "Cleaned up"}[version]
    credit = f"*{what} by {gen}" + (f" with {model}" if model and version != "cleaned" else "")
    if version == "cleaned" and (extra or {}).get("cleanup_model"):
        credit += f" with {extra['cleanup_model']}"
    lines += [credit + f" on {_day(time.time() if version == 'cleaned' else when)}.*", "", ""]
    return "\n".join(lines) + text.strip() + "\n"


def _manifest_path(md: Path) -> Path:
    return md.with_suffix(".json")


def save(text: str, setting: str = "", title: str | None = None, when: float | None = None,
         meta: dict | None = None, raw: str | None = None) -> Path:
    """Write `text` (version `transcript`) under the transcripts folder, plus <stem>.raw.md when
    `raw` (as transcribed) differs from it, and <stem>.json linking them. Returns the .md file.
    `when`: the transcript's time (default now); `meta`: see render(). Raises OSError."""
    when = when if when is not None else time.time()
    title = title.strip() if title and title.strip() else None
    p = path_for(folder(setting), when, title)
    p.parent.mkdir(parents=True, exist_ok=True)
    man = _manifest_path(p)
    p.write_text(render(text, title, when, meta, "transcript", man.name), encoding="utf-8")
    doc = {"schema": MANIFEST_SCHEMA, "title": title, "date": iso(when), **(meta or {}),
           "versions": [_entry("transcript", p, text, when)]}
    if raw is not None and raw.strip() and " ".join(raw.split()) != " ".join(text.split()):
        r = p.with_name(p.stem + SUFFIX["raw"] + ".md")
        r.write_text(render(raw, title, when, meta, "raw", man.name), encoding="utf-8")
        doc["versions"].append(_entry("raw", r, raw, when))
    _write_json(man, doc)
    return p


def _entry(kind: str, path: Path, text: str, when: float, **more) -> dict:
    return {"kind": kind, "file": path.name, "written": iso(time.time()), "words": len(text.split()),
            **{k: v for k, v in more.items() if v not in (None, "")}}


def _write_json(path: Path, doc: dict):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def add_version(md: Path, kind: str, text: str, extra: dict | None = None) -> Path:
    """Add version `kind` (cleaned) of the transcript saved as `md`: a new file beside it
    (<stem>.cleaned.md, then -2, …), never overwriting, and an entry in <stem>.json."""
    md = Path(md)
    man = _manifest_path(md)
    doc = json.loads(man.read_text(encoding="utf-8")) if man.is_file() else {
        "schema": MANIFEST_SCHEMA, "versions": [_entry("transcript", md, md.read_text(encoding="utf-8"), time.time())]}
    when = time.time()
    try:
        when = time.mktime(time.strptime(doc.get("date", "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        pass
    meta = {k: doc[k] for k in ("generator", "model", "audio_seconds", "source") if k in doc}
    base = md.stem + SUFFIX[kind]
    out, n = md.with_name(base + ".md"), 2
    while out.exists():
        out = md.with_name(f"{base}-{n}.md")
        n += 1
    out.write_text(render(text, doc.get("title"), when, meta, kind, man.name, extra), encoding="utf-8")
    doc["versions"].append(_entry(kind, out, text, when, of=md.name, **(extra or {})))
    _write_json(man, doc)
    return out

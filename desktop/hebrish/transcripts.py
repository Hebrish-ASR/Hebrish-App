"""Saved transcripts (B-74, Daniel 2026-10-31): Save writes straight to a transcripts folder, no
file dialog. Default ~/Documents/Hebrish transcripts (cfg `transcripts_dir` "" = default), changed
in Settings → Transcripts. Layout: <folder>/YYYY/MM/DD/<name>.md, Markdown by default.

Names: `HH-MM-SS.md` (the save time), or `<title>_HH-MM-SS.md` when a title is given, the title in
snake_case (`slug`). Titles come from a small title model, an optional add-on that is not built yet
(planning/backlog.md B-75); until then `title` is None. A name already taken gets `-2`, `-3`, …
so nothing is overwritten. With a title the file starts with `# <title>` and a blank line.

No Qt import: tested in tests/test_transcripts.py.
"""

import re
import time
import unicodedata
from pathlib import Path

from . import config

SLUG_MAX = 60


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
    """Where a transcript saved at `when` (epoch seconds; default now) goes. Not created."""
    tm = time.localtime(when if when is not None else time.time())
    day = base / time.strftime("%Y", tm) / time.strftime("%m", tm) / time.strftime("%d", tm)
    stamp = time.strftime("%H-%M-%S", tm)
    s = slug(title) if title else ""
    stem = f"{s}_{stamp}" if s else stamp
    p = day / f"{stem}.md"
    n = 2
    while p.exists():
        p = day / f"{stem}-{n}.md"
        n += 1
    return p


def save(text: str, setting: str = "", title: str | None = None, when: float | None = None) -> Path:
    """Write `text` as Markdown under the transcripts folder; returns the file. Raises OSError."""
    p = path_for(folder(setting), when, title)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = text.strip() + "\n"
    if title and title.strip():
        body = f"# {title.strip()}\n\n{body}"
    p.write_text(body, encoding="utf-8")
    return p

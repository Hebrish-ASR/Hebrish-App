#!/usr/bin/env python3
"""Bake the in-app "What's new" list from hebrish.app's changelog (2026-10-25).

Both apps show a short, offline list of project updates (Android: Updates screen; desktop: the
About tab's "What's new" card). The list is baked in at build time, not fetched: this script
reads the public changelog, keeps the entries dated on or before the build date, newest first,
the last N (default 20), and writes for each one its date, tag ("Desktop 1.003", "Models"),
title and a summary of one or two sentences in plain text.

Source: hebrish.app/changelog (`changelog.html` in the website repo, Hebrish-ASR's Hebrish-App
site, checked out next to this repo as ../Hebrish-App). Each entry there is
`<article class="log">` with `<time datetime>`, `<span class="tag">`, `<h3>` and a `<ul>`; the
summary is cut from the first `<li>`. The site's other feeds were not usable: data/releases.json
has only the numbered model releases (two entries) and data/updates/ holds the voice-note
podcast. If the checkout is missing, the live page is fetched instead.

Writes shared/updates.json and its byte-identical copy desktop/hebrish/data/updates.json (the
Android build copies shared/updates.json into the APK's assets, like catalogue.json).
desktop/tests/test_shared.py checks the copies agree and the file is well formed.

    python3 scripts/bake_updates.py                 # build date today, last 20
    python3 scripts/bake_updates.py --date 2026-10-24 --limit 10
    python3 scripts/bake_updates.py --source https://hebrish.app/changelog

Run by scripts/release-tag.sh before every release tag, so each build carries the entries up to
its own date. Standard library only.
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.path.join(ROOT, "..", "Hebrish-App", "changelog.html")
URL = "https://hebrish.app/changelog"
OUTS = [os.path.join(ROOT, "shared", "updates.json"),
        os.path.join(ROOT, "desktop", "hebrish", "data", "updates.json")]
MAX_SUMMARY = 280


class Changelog(HTMLParser):
    """Collects {date, tag, title, first} from each <article class="log">."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries, self.cur, self.field = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "article" and "log" in (a.get("class") or "").split():
            self.cur = {"date": "", "tag": "", "title": "", "first": "", "lis": 0}
        elif self.cur is None:
            return
        elif tag == "time" and not self.cur["date"]:
            self.cur["date"] = a.get("datetime", "")
        elif tag == "span" and "tag" in (a.get("class") or "").split():
            if self.cur["tag"].strip():
                self.cur["tag"] += " · "      # an entry can carry several tags (Models, Site)
            self.field = "tag"
        elif tag == "h3":
            self.field = "title"
        elif tag == "li":
            self.cur["lis"] += 1
            if self.cur["lis"] == 1:
                self.field = "first"

    def handle_endtag(self, tag):
        if self.cur is None:
            return
        if tag == "article":
            self.entries.append(self.cur)
            self.cur, self.field = None, None
        elif (tag == "span" and self.field == "tag") or (tag == "h3" and self.field == "title"):
            self.field = None
        elif tag == "li" and self.field == "first":
            self.field = None

    def handle_data(self, data):
        if self.cur is not None and self.field:
            self.cur[self.field] += data


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def summarise(text: str, limit: int = MAX_SUMMARY) -> str:
    """The first one or two sentences, within `limit` characters."""
    text = clean(text)
    # Sentence ends: . ! ? followed by a space and a capital, quote or digit.
    # Not inside a quotation ("word. Capital" is an example, not a sentence end).
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s+[A-Z0-9\"“(])", text)
            if text[:m.end()].count('"') % 2 == 0] + [len(text)]
    out = text[:ends[0]]
    if len(ends) > 1 and ends[1] <= limit and len(out) < 120:
        out = text[:ends[1]]
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return out.strip()


def read(source: str) -> str:
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": "hebrish-bake-updates"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8")
    with open(source, encoding="utf-8") as f:
        return f.read()


def bake(page: str, build_date: str, limit: int, source: str) -> dict:
    p = Changelog()
    p.feed(page)
    entries = []
    for e in p.entries:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"]) or e["date"] > build_date or not clean(e["title"]):
            continue
        entries.append({"date": e["date"], "tag": clean(e["tag"]), "title": clean(e["title"]),
                        "summary": summarise(e["first"])})
    # The page is newest first; keep its order within a day, sort across days to be safe.
    entries.sort(key=lambda e: e["date"], reverse=True)
    if not entries:
        raise SystemExit(f"no changelog entries found in {source}: has the page's markup changed?")
    return {
        "_comment": "Baked by scripts/bake_updates.py from hebrish.app/changelog; do not edit by hand. "
                    "Shown offline in the apps' What's new (Android Updates screen, desktop About tab).",
        "schema": 1,
        "built": build_date,
        "source": URL,
        "entries": entries[:limit],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", help=f"changelog.html path or URL (default {LOCAL}, else {URL})")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="build date, YYYY-MM-DD (default today)")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)
    source = args.source or (LOCAL if os.path.exists(LOCAL) else URL)
    doc = bake(read(source), args.date, args.limit, source)
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    for out in OUTS:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    newest = doc["entries"][0]
    print(f"{len(doc['entries'])} entries from {source} (newest {newest['date']}: {newest['title']}) "
          f"-> {', '.join(os.path.relpath(o, ROOT) for o in OUTS)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Import the text transformation prompt library into shared/ (2026-11-02).

Source: the Hugging Face dataset danielrosehill/Text-Transformation-Prompts-300525 (Daniel's own,
CC BY-ND 4.0, frozen since 2025-05-29), file all_prompts.json, pinned to REVISION below so a rerun
gives the same output, merged with the curated tags in scripts/transformation-tags.json (type, style,
language, featured, display label; written 2026-11-02 and edited by hand since). Writes
shared/text-transformation-prompts.json (schema 2) and the desktop
copy desktop/hebrish/data/text-transformation-prompts.json. Android copies the shared file into
the APK's assets at build time (android/app/build.gradle.kts, copyCatalogue).

Prompt text, names and descriptions are kept verbatim (only surrounding whitespace is trimmed):
the licence is no-derivatives, and the wording is the library. `label` is the display name (typos in
`name` fixed). The desktop app loads the file into history.db's builtin_transform_prompts table
(desktop/hebrish/transforms.py); Android ships it in its assets, unused until B-82a.

    python3 scripts/import_transformation_prompts.py            # fetch the pinned revision
    python3 scripts/import_transformation_prompts.py FILE.json  # from a local all_prompts.json
"""
import json
import os
import re
import sys
import urllib.request

DATASET = "danielrosehill/Text-Transformation-Prompts-300525"
REVISION = "f9d3e47a7ee1999dff24ef59c1a4e53425aa66b1"
URL = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/all_prompts.json"
TYPES = ("email", "message", "document", "notes", "list", "data", "ai-prompt", "rewrite", "fun")
STYLES = ("neutral", "formal", "professional", "casual", "playful")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = [os.path.join(ROOT, "shared", "text-transformation-prompts.json"),
       os.path.join(ROOT, "desktop", "hebrish", "data", "text-transformation-prompts.json")]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def or_none(s):
    s = (s or "").strip()
    return s or None


def main():
    if len(sys.argv) > 1:
        raw = json.load(open(sys.argv[1], encoding="utf-8"))
    else:
        with urllib.request.urlopen(URL, timeout=60) as r:
            raw = json.load(r)
    tags = json.load(open(os.path.join(ROOT, "scripts", "transformation-tags.json"), encoding="utf-8"))
    prompts = []
    for e in raw:
        structured = {"yes": True, "no": False}.get((e.get("delivers_structured_output") or "").strip().lower())
        pid = slug(e["name"])
        t = tags[pid]
        assert t["type"] in TYPES and t["style"] in STYLES and t["language"] in ("en", "he"), pid
        prompts.append({
            "id": pid,
            "label": t["label"],
            "name": e["name"].strip(),
            "type": t["type"],
            "style": t["style"],
            "language": t["language"],
            "featured": bool(t["featured"]),
            "prompt": e["system_prompt_text"].strip(),
            "description": or_none(e.get("description")),
            "output_format": or_none(e.get("expected_output_format")),
            "structured_output": structured,
            "source_file": e["source_file"].strip(),
        })
    prompts.sort(key=lambda p: p["id"])
    ids = [p["id"] for p in prompts]
    assert len(ids) == len(set(ids)), "duplicate ids"
    assert all(p["prompt"] for p in prompts), "empty prompt"
    assert set(tags) == set(ids), "scripts/transformation-tags.json must tag every prompt, and only those"
    doc = {
        "schema": 2,
        "source": {
            "dataset": DATASET,
            "revision": REVISION,
            "url": f"https://huggingface.co/datasets/{DATASET}",
            "licence": "CC-BY-ND-4.0",
            "author": "Daniel Rosehill",
            "imported": "2026-11-02",
        },
        "types": list(TYPES),
        "styles": list(STYLES),
        "count": len(prompts),
        "prompts": prompts,
    }
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    for path in OUT:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {path} ({len(prompts)} prompts)")


if __name__ == "__main__":
    main()

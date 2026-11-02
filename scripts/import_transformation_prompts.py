#!/usr/bin/env python3
"""Import the text transformation prompt library into shared/ (2026-11-02).

Source: the Hugging Face dataset danielrosehill/Text-Transformation-Prompts-300525 (Daniel's own,
CC BY-ND 4.0, frozen since 2025-05-29), file all_prompts.json, pinned to REVISION below so a rerun
gives the same output. Writes shared/text-transformation-prompts.json (schema 1) and the desktop
copy desktop/hebrish/data/text-transformation-prompts.json. Android copies the shared file into
the APK's assets at build time (android/app/build.gradle.kts, copyCatalogue).

Prompt text, names and descriptions are kept verbatim (only surrounding whitespace is trimmed):
the licence is no-derivatives, and the wording is the library. Nothing reads the file yet; the
integration plan is I-18 in planning/backlog.md.

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
    prompts = []
    for e in raw:
        structured = {"yes": True, "no": False}.get((e.get("delivers_structured_output") or "").strip().lower())
        prompts.append({
            "id": slug(e["name"]),
            "name": e["name"].strip(),
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
    doc = {
        "schema": 1,
        "source": {
            "dataset": DATASET,
            "revision": REVISION,
            "url": f"https://huggingface.co/datasets/{DATASET}",
            "licence": "CC-BY-ND-4.0",
            "author": "Daniel Rosehill",
            "imported": "2026-11-02",
        },
        "note": "Not used by the apps yet; see planning/backlog.md I-18.",
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

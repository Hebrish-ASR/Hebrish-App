---
date: 2026-10-31
platform: desktop-linux
environment: Ubuntu, Hebrish desktop 1.015 (.deb), cached catalogue fetched before 1.015
component: desktop/hebrish/cleanup.py (_all, entry)
affected: "1.015"
fixed_in: "1.016"
status: fixed
---

# The title model's Download fails ("the catalogue offers no clean-up model")

## Symptom

Reported by Daniel on 2026-10-31, the day 1.015 shipped: Models → Utilities shows the title
model (B-75), but downloading it doesn't work.

## Cause

`cleanup._all(kind)` returned the add-ons from the first catalogue that had *any* of the kinds
asked for: the cached published catalogue (`~/.local/share/hebrish/catalogue-v2.json`), else the
bundled copy.

- The Utilities row asks for kind `text_title`. The cache (fetched before the title model was
  published) has none, so it fell back to the bundled copy and the row was shown.
- Download calls `entry(aid)`, which asks for every llama-server kind (`kind=None`). The cache has
  three `text_cleanup` add-ons, so the bundled copy was never consulted and the title model was
  not found: `RuntimeError: the catalogue offers no clean-up model 'title-gemma-270m'`.

The published catalogue (`catalogue_v2_url`) does have the entry; the cache refreshes only on a
model update check, so any install that hadn't checked since the title model was pushed hit this.

Reproduced on the maintainer's machine (V):

```
titles.entries()                     -> ['title-gemma-270m']
cleanup.entry('title-gemma-270m')    -> RuntimeError: the catalogue offers no clean-up model
```

## Fix

`_all` now merges: the cached catalogue's add-ons, then any bundled add-on whose id the cache
lacks. The cache still wins for an id both have (so a published pin update is used). Test:
`test_cached_catalogue_without_the_title_model_still_finds_it` in `tests/test_cleanup.py`.
After the fix, the same lookup on the same machine returns the entry (V).

## Not verified

The full download through the 1.015 window was not re-run here; the fix shipped in desktop 1.016
(2026-10-31). Workaround on 1.015: Models → Check for updates (refreshes the cache), then
Download.

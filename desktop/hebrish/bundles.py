"""Model bundles and Update all (B-79, Daniel 2026-10-31, R-2026-10-31-6).

Bundles: named sets in the catalogue's `bundles` (shared/catalogue.json), each a list of speech
model ids (`models`) and add-on ids (`addons`: the catalogue's GGUF add-ons, cleanup.py, and
`paragraph-breaks`, paragraphs.py). The Models tab downloads a bundle's missing items in one go.
Items this computer can't run are skipped, so one bundle serves Linux and Windows.

Update all: `check()` looks at every downloaded speech model and add-on, not only the model in
use (before B-79, Check for updates covered the current model alone).

- Speech models: fetch_latest() and needs_update(), as the single-model check does.
- Clean-up and title models: pinned in the catalogue, so a newer version is a catalogue entry whose
  version folder isn't on disk while an older one is.
- Paragraph model: its CDN manifest's version against the installed folder's name.

No Qt import: tested in tests/test_bundles.py.
"""

from dataclasses import dataclass, field

from . import cleanup, model_store, paragraphs


def _all() -> list[dict]:
    """The catalogue's bundles: the cached (published) catalogue's, else the bundled copy's (an
    install whose cache predates bundles still shows them)."""
    for doc in (model_store.catalogue(), model_store.bundled_catalogue()):
        found = [b for b in doc.get("bundles", []) if b.get("id")]
        if found:
            return found
    return []


def addon_ids() -> set[str]:
    """Add-ons this computer can download."""
    return {e["id"] for e in cleanup.entries(None)} | {paragraphs.MODEL_ID}


def addon_installed(aid: str) -> bool:
    if aid == paragraphs.MODEL_ID:
        return paragraphs.installed() is not None
    return cleanup.installed(aid) is not None


def items(b: dict) -> tuple[list[str], list[str]]:
    """(speech model ids, add-on ids) of bundle `b` that run here, in bundle order."""
    models = [m for m in b.get("models", []) if (v := model_store.get_model(m)) and v.available]
    offered = addon_ids()
    return models, [a for a in b.get("addons", []) if a in offered]


def bundles() -> list[dict]:
    """Bundles with at least one item that runs here, the `default: true` one first."""
    out = [b for b in _all() if any(items(b))]
    return sorted(out, key=lambda b: not b.get("default"))


def get(bid: str) -> dict | None:
    return next((b for b in bundles() if b["id"] == bid), None)


def missing(b: dict) -> tuple[list[str], list[str]]:
    """(speech model ids, add-on ids) of `b` not yet downloaded."""
    models, addons = items(b)
    return ([m for m in models if not model_store.installed(m)],
            [a for a in addons if not addon_installed(a)])


def size_mb(b: dict) -> int:
    """Roughly what downloading the missing part of `b` takes, in MB (catalogue sizes; the shared
    llama.cpp runtime and the paragraph model's few MB are not counted)."""
    models, addons = missing(b)
    total = 0
    for m in models:
        v = model_store.get_model(m)
        total += getattr(v, "download_mb", 0) or 0
    for a in addons:
        try:
            total += cleanup.entry(a).get("download_mb", 0) or 0
        except RuntimeError:
            pass
    return total


# -- Update all -------------------------------------------------------------------------------

@dataclass
class Updates:
    models: list = field(default_factory=list)      # [model_store.Manifest] newer than installed
    addons: list = field(default_factory=list)      # [add-on id] with a newer version
    errors: list = field(default_factory=list)      # [(id, str(error))]: checks that failed

    def __len__(self):
        return len(self.models) + len(self.addons)


def _addon_stale(aid: str) -> bool:
    """A clean-up/title model with an older version on disk and the catalogue's not installed."""
    if cleanup.installed(aid) is not None:
        return False
    base = cleanup.root(aid)
    return base.is_dir() and any((d / "manifest.json").is_file() for d in base.iterdir() if d.is_dir())


def _paragraphs_stale() -> bool:
    folder = paragraphs.installed()
    if folder is None:
        return False
    v = paragraphs.fetch_manifest()["version"]
    return folder.name != "".join(c if c.isalnum() or c in "-_." else "_" for c in v)


def check() -> Updates:
    """Every downloaded speech model and add-on with a newer version. Network: call it off the
    GUI thread. A failed check of one item is recorded in `errors` and the rest still run."""
    out = Updates()
    for mid in model_store.installed_ids():
        try:
            latest = model_store.fetch_latest(mid)
            if model_store.needs_update(latest):
                out.models.append(latest)
        except Exception as e:
            out.errors.append((mid, str(e)))
    for e in cleanup.entries(None):
        if _addon_stale(e["id"]):
            out.addons.append(e["id"])
    try:
        if _paragraphs_stale():
            out.addons.append(paragraphs.MODEL_ID)
    except Exception as e:
        out.errors.append((paragraphs.MODEL_ID, str(e)))
    return out

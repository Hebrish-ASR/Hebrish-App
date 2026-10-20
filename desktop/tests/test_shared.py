"""Both apps must read the model catalogue from shared/models.json."""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "desktop"))

from hebrish import model_store  # noqa: E402

SHARED = os.path.join(ROOT, "shared", "models.json")


def test_desktop_bundles_the_shared_catalogue():
    """desktop/hebrish/data/models.json is a copy (PyInstaller and the .deb need it inside
    the package). After editing shared/models.json: cp shared/models.json desktop/hebrish/data/"""
    assert open(model_store.BUNDLED_CATALOGUE).read() == open(SHARED).read()


ANDROID = os.path.join(ROOT, "android", "app")
KT = os.path.join(ANDROID, "..", "core", "src", "main", "java", "app", "hebrish", "core")


def test_android_bundles_the_shared_catalogue():
    """The APK's assets/models.json is copied from shared/ at build time, never by hand."""
    assert "../shared/models.json" in open(os.path.join(ANDROID, "build.gradle.kts")).read()
    import re
    schema = re.search(r"const val SCHEMA = (\d+)", open(os.path.join(KT, "Catalogue.kt")).read())
    assert schema and int(schema.group(1)) == json.load(open(SHARED))["schema"]


def test_android_offline_fallbacks_are_available_models():
    import re
    ids = set(re.findall(r'"(\w+)" to Manifest\(', open(os.path.join(KT, "ModelStore.kt")).read()))
    available = {m["id"] for m in json.load(open(SHARED))["models"] if m["status"] == "available"}
    assert ids and ids <= available


def test_hebrish_ships_only_stock_and_codeswitch():
    """Hebrish is the code-switching app: stock Parakeet and the code-switching model, nothing else.
    The other fine-tunes (tech, personal) belong to Parlance (danielrosehill/Parlance-Dictation)."""
    with open(SHARED) as f:
        assert [m["id"] for m in json.load(f)["models"]] == ["stock", "codeswitch"]

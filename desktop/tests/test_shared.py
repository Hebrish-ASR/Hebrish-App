"""The desktop app must read the model from where shared/model.json says (Android does too)."""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "desktop"))

from voice_to_hebrish import model_store  # noqa: E402

SHARED = json.load(open(os.path.join(ROOT, "shared", "model.json")))


def test_desktop_matches_shared():
    assert model_store.REPO == SHARED["repo"]
    assert model_store.SUBDIR == SHARED["subdir"]
    assert list(model_store.FILES) == SHARED["files"]


def test_android_matches_shared():
    kt = open(os.path.join(ROOT, "android", "app", "src", "main", "java", "com", "danielrosehill",
                           "codeswitchvoice", "ModelStore.kt")).read()
    consts = dict(re.findall(r'const val (\w+) = "([^"]+)"', kt))
    assert consts.get("REPO") == SHARED["repo"]
    assert consts.get("SUBDIR") == SHARED["subdir"]
    assert consts.get("VERSION_FILE") == SHARED["version_file"]

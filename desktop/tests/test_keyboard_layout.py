"""Keyboard layout detection for Hebrew switching (hebrish/keyboard_layout.py): the parsers."""

from hebrish import keyboard_layout as K

KDE_LIST = """method return time=1 sender=:1.25 -> destination=:1.3 serial=1 reply_serial=2
   array [
      struct {
         string "gb"
         string ""
         string "English (UK)"
      }
      struct {
         string "il"
         string ""
         string "Hebrew"
      }
   ]
"""


def kde_index(i):
    return f"method return time=1 sender=:1.25 -> destination=:1.3 serial=1 reply_serial=2\n   uint32 {i}\n"


def test_kde_reply_as_captured_on_plasma_6():
    assert K.parse_kde_layouts(KDE_LIST) == ["gb\tEnglish (UK)", "il\tHebrew"]
    assert K.kde_layout(kde_index(0), KDE_LIST) == "gb\tEnglish (UK)"
    assert K.lang_of(K.kde_layout(kde_index(1), KDE_LIST)) == "he"
    assert K.kde_layout(kde_index(5), KDE_LIST) is None
    assert K.kde_layout("garbage", KDE_LIST) is None


def test_kde_long_name_alone_says_hebrew():
    assert K.lang_of("xx\tHebrew (phonetic)") == "he"


def test_gnome_mru_first_then_current_index():
    assert K.gnome_layout("[('xkb', 'il'), ('xkb', 'us')]", "[('xkb', 'us'), ('xkb', 'il')]", "uint32 0") == "il"
    assert K.gnome_layout("@a(ss) []", "[('xkb', 'us'), ('xkb', 'il')]", "uint32 1") == "il"
    assert K.gnome_layout("@a(ss) []", "[('xkb', 'us'), ('xkb', 'il')]", "") is None
    assert K.gnome_layout("@a(ss) []", "[('xkb', 'gb')]", "") == "gb"
    assert K.parse_gvariant_sources("not a list") == []


def test_setxkbmap_layouts_with_variants():
    out = "rules:      evdev\nmodel:      pc105\nlayout:     us,il\nvariant:    ,phonetic\n"
    assert K.parse_setxkbmap_layouts(out) == ["us", "il(phonetic)"]
    assert K.parse_setxkbmap_layouts("rules: evdev\n") == []


def test_hebrew_layout_names():
    for code in ("il", "IL", "il(phonetic)", "il+lyx", "he", "Hebrew", "m17n:he:kbd", "ibus:he"):
        assert K.is_hebrew_layout(code), code
    for code in ("us", "gb", "ru", "", "ar", "hu", "help"):
        assert not K.is_hebrew_layout(code), code


def test_windows_langid():
    assert K.lang_from_hkl(0x040D040D) == "he"        # Hebrew (Israel), Hebrew keyboard
    assert K.lang_from_hkl(0x0409) == "en"
    assert K.lang_from_hkl(0xF0A8040D) == "he"        # a custom layout over Hebrew: high word differs
    assert K.lang_from_hkl(0x0809) == "en"


def test_detect_never_raises_and_reports_unknown(monkeypatch):
    monkeypatch.setattr(K.sys, "platform", "linux")
    for name in ("_kde", "_gnome", "_x11"):
        monkeypatch.setattr(K, name, lambda: (_ for _ in ()).throw(OSError("no")))
    assert K.detect() == K.Detected("unknown", "none")
    monkeypatch.setattr(K, "_gnome", lambda: "il")
    assert K.detect().lang == "he" and K.detect().method == "gnome"

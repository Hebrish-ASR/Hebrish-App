"""The About tab: a hero (mark, name, versions, main links), then cards: what's new, privacy, models, how
well Jachnun works, how it was trained, how to help, terms.

Code-switching numbers come from the project hub, github.com/Hebrish-ASR/English-Hebrew-Codeswitching-Parakeet-Finetune
(sections "Results" and "Training data"). Update BENCH and TRAINING when a new version is
benchmarked. v1.0 was benchmarked on 2026-10-19 on its own test split (dataset revision
550bfcaa, 387 clips), with stock Parakeet re-scored on the same clips.
"""

import html
import json
import platform
from pathlib import Path
from urllib.parse import quote, urlencode

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .. import __version__, model_store
from .style import BLUE, BRAND_GREEN, GOLD, INK, MUTED, PAPER, display_font

HUB = "https://github.com/Hebrish-ASR/English-Hebrew-Codeswitching-Parakeet-Finetune"
MODEL = "https://huggingface.co/Hebrish/Jachnun"       # the HF home since 2026-10-20 (gated)
LEADERBOARD = "https://huggingface.co/spaces/danielrosehill/English-Hebrew-Codeswitching-ASR-Leaderboard"
DEMO = "https://huggingface.co/spaces/danielrosehill/English-Hebrew-Codeswitching-Parakeet-Demo"
SOURCE = "https://github.com/Hebrish-ASR/Hebrish-App"
AUTHOR_SITE = "https://danielrosehill.com"

# hebrish.app, the website for the code-switching model, its contact topics and the feedback
# address. The only place these URLs live: the About tab, the Model tab and the tray's
# "Hebrish" submenu all read this list. The `topic` values are the ones hebrish.app/contact
# understands. The mailto links open the user's mail client with the app and OS version
# already in the body.
HEBRISH = "https://hebrish.app"
FEEDBACK = "feedback@hebrish.app"
TERMS = f"{HEBRISH}/terms"
CHANGELOG = f"{HEBRISH}/changelog"
# What's new (2026-10-25): baked from hebrish.app/changelog by scripts/bake_updates.py before each
# release (a copy of shared/updates.json), so it is offline and fixed at build time.
UPDATES = Path(__file__).resolve().parent.parent / "data" / "updates.json"
UPDATES_SHOWN = 5       # the rest behind "Show all"


def load_updates() -> dict:
    """The baked list, or an empty one if the file is missing or broken (never an error)."""
    try:
        doc = json.loads(UPDATES.read_text(encoding="utf-8"))
        return doc if isinstance(doc.get("entries"), list) else {"entries": []}
    except (OSError, ValueError, AttributeError):
        return {"entries": []}


def updates_html(entries: list) -> str:
    out = []
    for e in entries:
        meta = " · ".join(x for x in (e.get("date", ""), e.get("tag", "")) if x)
        out.append(f"<p style='margin:0 0 10px 0'><small style='color:gray'>{html.escape(meta)}</small><br>"
                   f"<b>{html.escape(e.get('title', ''))}</b><br>{html.escape(e.get('summary', ''))}</p>")
    return "".join(out)
ACCESS = "access@hebrish.app"


def _mail(subject: str) -> str:
    body = f"\n\n--\nHebrish {__version__}, {platform.system()} {platform.release()}"
    return f"mailto:{FEEDBACK}?" + urlencode(
        {"subject": f"{subject} (Hebrish for desktop)", "body": body}, quote_via=quote)


HEBRISH_LINKS = [
    ("Hebrish website", HEBRISH),
    ("Report a bug", _mail("Bug report")),
    ("Request a feature", _mail("Feature request")),
    ("Send feedback", _mail("Feedback")),
    ("Suggest a word", f"{HEBRISH}/contact?topic=word"),
    ("Send voice samples", f"{HEBRISH}/contact?topic=samples"),
    ("Get involved", f"{HEBRISH}/contact?topic=involved"),
]

BENCH_VERSION = "Jachnun v1.0"        # latest benchmarked (2026-10-19)
# (test, stock Parakeet v2, fine-tune, lower_is_better)
BENCH = [
    ("Word error rate, English with Hebrew words (held-out)", "11.3%", "5.1%", True),
    ("Hebrew words it heard in training, transcribed correctly", "28%", "73%", False),
    ("Hebrew words it never heard, transcribed correctly", "26%", "48%", False),
    ("Word error rate, the speaker's plain English", "3.1%", "1.7%", True),
    ("Word error rate, LibriSpeech test-clean", "1.2%", "1.2%", True),
    ("Word error rate, ~3-minute recordings", "9.6%", "5.0%", True),
]
LEADER = [("Jachnun v1.0", "73.3%"), ("Jachnun PoC-3", "67.4%"),
          ("Whisper Large V3", "45.9%"), ("Stock Parakeet v2", "32.6%")]
TRAINING = {  # v1.0, the version this app downloads as of 2026-10-19
    "version": "Jachnun v1.0", "cs_min": 339, "cs_clips": "3,224", "own_en_min": 95, "replay_min": 49,
    "mix": "70.2% / 19.7% / 10.0%", "gpu": "one L40S", "minutes": 41, "epochs": 20,
}


def _link_button(text: str, url: str, primary=False) -> QPushButton:
    b = QPushButton(text, objectName="primary" if primary else "")
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(url.split("?")[0])
    b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
    return b


def _rich(html: str) -> QLabel:
    lbl = QLabel(html)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.RichText)
    lbl.setOpenExternalLinks(True)
    lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)
    return lbl


class AboutPage(QScrollArea):
    """card(title) and muted(text) are window.py's helpers (passed in: window imports us)."""

    def __init__(self, icon, card, muted):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(12)
        lay.addWidget(self._hero(icon))
        lay.addWidget(self._whats_new(card))

        box, b = card("Private by design")
        b.addWidget(_rich(
            "Everything runs on this computer: the model you picked in Models, through sherpa-onnx. "
            "Nothing you say leaves the machine. The only network traffic is model downloads and "
            "the checks for newer versions."))
        lay.addWidget(box)

        box, b = card("Models")
        b.addWidget(_rich("".join(
            f"<p style='margin:0 0 6px 0'><b>{m.name}</b>"
            f"{'' if m.available else ' <i>(coming soon)</i>'}: {m.summary}"
            + (f" <a href='{m.card}'>Model card</a>" if m.card else "") + "</p>"
            for m in model_store.models())))
        lay.addWidget(box)

        box, b = card(f"How well it works ({BENCH_VERSION})")
        rows = "".join(
            f"<tr><td style='padding:5px 8px 5px 0'>{name}</td>"
            f"<td align='center' style='padding:5px 8px'>{stock}</td>"
            f"<td align='center' style='padding:5px 8px'><b style='color:{BLUE}'>{ft}</b></td></tr>"
            for name, stock, ft, _ in BENCH)
        b.addWidget(_rich(
            "<table width='100%' cellspacing='0'>"
            "<tr><th align='left' style='padding:0 8px 6px 0'>Test</th>"
            "<th style='padding:0 8px 6px'>Stock Parakeet v2</th>"
            f"<th style='padding:0 8px 6px'>{BENCH_VERSION}</th></tr>{rows}</table>"))
        b.addWidget(muted(
            "Error rates roughly halved, and plain English got better, not worse. Scored on "
            "2026-10-19 on recordings it was never trained on. Jachnun is trained on one "
            "speaker's voice; stock Parakeet is the better choice for voices far from it."))
        leader = " · ".join(f"{n} <b>{v}</b>" for n, v in LEADER)
        b.addWidget(_rich(f"<small>Public leaderboard, Hebrew-word recall on a frozen test set: "
                          f"{leader}. <a href='{LEADERBOARD}'>Leaderboard</a></small>"))
        lay.addWidget(box)

        t = TRAINING
        box, b = card(f"How {t['version']} was trained")
        b.addWidget(_rich(
            "English with Hebrew words in it, written in Latin letters: <i>teudat zehut</i>, "
            "<i>bituach leumi</i>, <i>rishayon iski</i>. Parakeet's alphabet has no Hebrew "
            "letters, so the model learns one consistent Latin spelling for each Hebrew word."
            f"<ul style='margin-left:-20px'><li><b>{t['cs_min']} minutes</b> ({t['cs_clips']} clips) "
            "of English sentences with Hebrew words, read aloud on a phone;</li>"
            f"<li><b>{t['own_en_min']} minutes</b> of the same speaker's plain English, so the "
            "model keeps its English;</li>"
            f"<li><b>{t['replay_min']} minutes</b> of LibriSpeech audiobook English, as a "
            "general-English anchor.</li></ul>"
            f"A {t['mix']} mix, because fine-tuning on code-switched speech alone is known to "
            f"damage a model's English. Training took {t['minutes']} minutes on {t['gpu']} "
            f"({t['epochs']} epochs)."))
        lay.addWidget(box)

        box, b = card("Help improve it")
        b.addWidget(muted("Want it to learn your voice, or a word it gets wrong? Send recordings "
                          "or suggest the word. Bugs and ideas go to "
                          f"{FEEDBACK}; your mail client opens with the app and OS version filled in."))
        grid = QHBoxLayout()
        grid.setSpacing(6)
        for label, url in HEBRISH_LINKS[4:]:
            grid.addWidget(_link_button(label, url))
        grid.addStretch(1)
        b.addLayout(grid)
        row = QHBoxLayout()
        row.setSpacing(6)
        for label, url in HEBRISH_LINKS[1:4]:
            row.addWidget(_link_button(label, url))
        row.addStretch(1)
        b.addLayout(row)
        lay.addWidget(box)

        box, b = card("Terms and licences")
        b.addWidget(_rich(
            "The Hebrish models are free for personal, research, education and non-profit use. "
            "Commercial use, including telephony and call centres, needs a commercial licence: "
            f"<a href='mailto:{ACCESS}'>{ACCESS}</a>. Full terms: <a href='{TERMS}'>hebrish.app/terms</a>. "
            "Hebrish is experimental: check transcripts before relying on them. It is provided as "
            "is, without warranty.<br><br>Versions up to v1.0 of Jachnun are CC-BY-4.0, stock "
            "Parakeet is CC-BY-4.0 (NVIDIA), and the app is MIT."))
        lay.addWidget(box)

        foot = muted(f"<a href='{HUB}'>Code-switching project</a> · <a href='{MODEL}'>Jachnun on "
                     f"Hugging Face</a> · <a href='{DEMO}'>Demo</a> · <a href='{SOURCE}'>Source code</a>"
                     f"<br>Open source (MIT) by <a href='{AUTHOR_SITE}'>Daniel Rosehill</a>")
        foot.setTextFormat(Qt.RichText)
        foot.setOpenExternalLinks(True)
        foot.setAlignment(Qt.AlignCenter)
        lay.addWidget(foot)
        lay.addStretch(1)
        self.setWidget(page)

    def _whats_new(self, card) -> QFrame:
        """What's new: the latest changes baked into this build, newest first; Show all expands."""
        doc = load_updates()
        entries = doc["entries"]
        box, b = card("What's new")
        if not entries:
            b.addWidget(_rich(f"This version has no list of changes. See <a href='{CHANGELOG}'>hebrish.app/changelog</a>."))
            return box
        b.addWidget(_rich(f"<small style='color:gray'>The latest changes to Hebrish, up to {doc.get('built', '')} "
                          f"when this version was built. <a href='{CHANGELOG}'>Full changelog</a></small>"))
        self.updates_label = _rich(updates_html(entries[:UPDATES_SHOWN]))
        b.addWidget(self.updates_label)
        if len(entries) > UPDATES_SHOWN:
            more = QLabel()
            more.setTextFormat(Qt.RichText)

            def toggle(_=None):
                full = more.property("full") is not True
                more.setProperty("full", full)
                self.updates_label.setText(updates_html(entries if full else entries[:UPDATES_SHOWN]))
                more.setText(f"<a href='#'>{'Show fewer' if full else f'Show all ({len(entries)})'}</a>")
            more.setProperty("full", True)
            toggle()
            more.linkActivated.connect(toggle)
            b.addWidget(more)
        return box

    def _hero(self, icon) -> QFrame:
        hero = QFrame(objectName="aboutHero")
        hero.setStyleSheet(
            f"#aboutHero {{ background: {PAPER}; border: 1px solid #e2dccf; border-radius: 12px; }}"
            f"#aboutHero QLabel {{ color: {INK}; background: transparent; border: none; }}"
            f"#aboutHero #heroMuted {{ color: {MUTED}; }}"
            f"#aboutHero #chip {{ background: #f1ece1; color: {INK}; border-radius: 10px;"
            "  padding: 2px 9px; font-size: 11px; }"
            f"#aboutHero #chipGold {{ background: transparent; color: {GOLD}; border: 1px solid {GOLD};"
            "  border-radius: 10px; padding: 1px 8px; font-size: 11px; }"
            f"#aboutHero QPushButton {{ background: white; color: {INK}; border: 1px solid #e2dccf;"
            "  border-radius: 6px; padding: 5px 12px; }"
            "#aboutHero QPushButton:hover { background: #f1ece1; }"
            f"#aboutHero QPushButton#primary {{ background: {BRAND_GREEN}; color: white; border: none;"
            "  font-weight: 600; }"
            f"#aboutHero QPushButton#primary:hover {{ background: #0c5a4d; }}")
        lay = QVBoxLayout(hero)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(icon.pixmap(72, 72))
        top.addWidget(logo, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("Hebrish")
        title.setFont(display_font(30))
        col.addWidget(title)
        tag = QLabel("Dictation for English speakers in Israel. Gets the Hebrew words right.",
                     objectName="heroMuted")
        tag.setWordWrap(True)
        col.addWidget(tag)
        by = _rich(f"An open-source project by <a href='{AUTHOR_SITE}' style='color:{BRAND_GREEN}'>"
                   "<b>Daniel Rosehill</b></a> · <a href='{AUTHOR_SITE}' "
                   f"style='color:{BRAND_GREEN}'>danielrosehill.com</a>".replace("{AUTHOR_SITE}", AUTHOR_SITE))
        by.setStyleSheet("font-size: 13px;")
        col.addWidget(by)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        chips.setContentsMargins(0, 6, 0, 0)
        chips.addWidget(QLabel(f"App v{__version__}", objectName="chip"))
        self.model_chip = QLabel(objectName="chip")
        chips.addWidget(self.model_chip)
        chips.addWidget(QLabel("On-device", objectName="chipGold"))
        chips.addStretch(1)
        col.addLayout(chips)
        top.addLayout(col, 1)
        lay.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(_link_button("hebrish.app", HEBRISH, primary=True))
        row.addWidget(_link_button("Report a bug", HEBRISH_LINKS[1][1]))
        row.addWidget(_link_button("Send feedback", HEBRISH_LINKS[3][1]))
        row.addWidget(_link_button("Source code", SOURCE))
        row.addStretch(1)
        lay.addLayout(row)
        self.refresh()
        return hero

    def refresh(self):
        cur = model_store.active()
        self.model_chip.setText(f"Model: {cur[1].full_label}" if cur else "No model yet")

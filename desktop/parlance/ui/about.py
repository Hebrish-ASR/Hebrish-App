"""The About tab: what the app is, the models it offers, and how the code-switching model scores.

Code-switching numbers come from the project hub, github.com/Hebrish-ASR/English-Hebrew-Codeswitching-Parakeet-Finetune
(sections "Results" and "Training data"). Update BENCH and TRAINING when a new version is
benchmarked; v4 was released before its benchmark, so v3 is still the latest measured.
"""

from .. import __version__, model_store

HUB = "https://github.com/Hebrish-ASR/English-Hebrew-Codeswitching-Parakeet-Finetune"
MODEL = "https://huggingface.co/danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching"
LEADERBOARD = "https://huggingface.co/spaces/danielrosehill/English-Hebrew-Codeswitching-ASR-Leaderboard"
DEMO = "https://huggingface.co/spaces/danielrosehill/English-Hebrew-Codeswitching-Parakeet-Demo"
SOURCE = "https://github.com/Hebrish-ASR/Parlance-Dictation"

# hebrish.app, the website for the code-switching model, and its contact topics. The only
# place these URLs live: the About tab, the Model tab and the tray's "Hebrish" submenu all
# read this list. The `topic` values are the ones hebrish.app/contact understands.
HEBRISH = "https://hebrish.app"
HEBRISH_LINKS = [
    ("Hebrish website", HEBRISH),
    ("Report a bug", f"{HEBRISH}/contact?topic=bug"),
    ("Suggest a word", f"{HEBRISH}/contact?topic=word"),
    ("Send voice samples", f"{HEBRISH}/contact?topic=samples"),
    ("Get involved", f"{HEBRISH}/contact?topic=involved"),
]

BENCH_VERSION = "v3"          # latest benchmarked (2026-10-18)
# (test, stock Parakeet v2, fine-tune, lower_is_better)
BENCH = [
    ("Word error rate, English with Hebrew words (held-out)", "10.9%", "5.3%", True),
    ("Hebrew words it heard in training, transcribed correctly", "29%", "66%", False),
    ("Hebrew words it never heard, transcribed correctly", "27%", "48%", False),
    ("Word error rate, the speaker's plain English", "3.5%", "2.9%", True),
    ("Word error rate, LibriSpeech test-clean", "1.2%", "1.0%", True),
    ("Word error rate, ~3-minute recordings", "9.0%", "5.0%", True),
]
LEADER = [("Code-switching fine-tune (v3)", "67.4%"), ("Its v2", "65.7%"),
          ("Whisper Large V3", "45.9%"), ("Stock Parakeet v2", "32.6%")]
TRAINING = {  # v4, the version this app downloads as of 2026-10-18
    "version": "v4", "cs_min": 269, "cs_clips": "2,622", "own_en_min": 73, "replay_min": 39,
    "mix": "70.8% / 19.1% / 10.1%", "gpu": "one L40S", "minutes": 33, "epochs": 20,
}


def html(model_label: str, accent: str) -> str:
    t = TRAINING
    rows = "".join(
        f"<tr><td>{name}</td><td align='center'>{stock}</td>"
        f"<td align='center'><b style='color:{accent}'>{ft}</b></td></tr>"
        for name, stock, ft, _ in BENCH)
    hebrish = " · ".join(f"<a href='{u}'>{n}</a>" for n, u in HEBRISH_LINKS)
    leader = "".join(f"<tr><td>{n}</td><td align='center'>{v}</td></tr>" for n, v in LEADER)
    catalogue = "".join(
        f"<li><b>{m.name}</b>{'' if m.available else ' <i>(coming soon)</i>'}: {m.summary}"
        + (f" <a href='{m.card}'>Model card</a>" if m.card else "") + "</li>"
        for m in model_store.models())
    return f"""
<h2 style="margin-bottom:0">Parlance</h2>
<p style="margin-top:2px">app v{__version__} · model {model_label}</p>

<p>Dictation that runs on your own computer. Press a hotkey, talk, and the text is pasted
where your cursor is. Every model is NVIDIA's <b>Parakeet TDT 0.6B v2</b> (600 million
parameters), either as released or fine-tuned for a particular kind of speech. Nothing you
say leaves the machine; the only network traffic is the model download and the update
check.</p>

<h3>Models</h3>
<ul>{catalogue}</ul>
<p>The fine-tunes are trained on one speaker's voice, so they work best for voices like
that one. Stock Parakeet is the right choice for anyone else.</p>

<h3>English-Hebrew code-switching: how {t['version']} was trained</h3>
<p>English with Hebrew words in it, written in Latin letters: <i>teudat zehut</i>,
<i>bituach leumi</i>, <i>rishayon iski</i>. Parakeet's alphabet has no Hebrew letters, so
the model learns one consistent Latin spelling for each Hebrew word.</p>
<ul>
<li><b>{t['cs_min']} minutes</b> ({t['cs_clips']} clips) of English sentences with Hebrew
words, read aloud on a phone;</li>
<li><b>{t['own_en_min']} minutes</b> of the same speaker's plain English, so the model
keeps its English;</li>
<li><b>{t['replay_min']} minutes</b> of LibriSpeech audiobook English, as a general-English
anchor.</li>
</ul>
<p>That is a {t['mix']} mix, because fine-tuning on code-switched speech alone is known to
damage a model's English. Training took {t['minutes']} minutes on {t['gpu']}
({t['epochs']} epochs).</p>

<h3>How well it works ({BENCH_VERSION}, the latest benchmarked version)</h3>
<table cellpadding="5" cellspacing="0" border="0" width="100%">
<tr><th align="left">Test</th><th>Stock Parakeet v2</th><th>Code-switching fine-tune</th></tr>
{rows}
</table>
<p>Error rates roughly halved, and plain English got slightly better, not worse.
{t['version']} has more training audio but hasn't been benchmarked yet.</p>

<p><b>Public leaderboard</b> (Hebrew-word recall on a frozen test set):</p>
<table cellpadding="4" cellspacing="0">{leader}</table>

<h3>Hebrish: help improve it</h3>
<p>The code-switching model has its own website, <a href="{HEBRISH}">hebrish.app</a>, with
the results and every model, dataset and demo. Report a bug, suggest a Hebrew word it gets
wrong, or send voice samples to help it learn more voices:</p>
<p>{hebrish}</p>

<p>The fine-tuned models are CC-BY-4.0, stock Parakeet is CC-BY-4.0 (NVIDIA), and the app
is MIT.</p>

<p><a href="{HUB}">Code-switching project</a> · <a href="{MODEL}">Model on Hugging Face</a> ·
<a href="{DEMO}">Demo</a> · <a href="{LEADERBOARD}">Leaderboard</a> ·
<a href="{SOURCE}">Source code</a></p>
"""

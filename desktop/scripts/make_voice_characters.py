"""Render the character voice packs in hebrish/data/voice/<voice>/ (Voice feedback: Herman,
Corn, Hilbert, the voices of the My Weird Prompts podcast). Two steps:

    ~/.local/share/uv/tools/modal/bin/python scripts/make_voice_characters.py render [voices]
    .venv/bin/python scripts/make_voice_characters.py pick [voices]

render needs Daniel's Modal account: it calls the deployed `mwp-recording-app` `tts_worker`
(Chatterbox with each character's voice conditionals), which writes .m4a files to the Modal
volume `mwp-working-files` under `private/hebrish-voice/`. They are fetched, cut to the speech
(silence trimmed both ends), written as 16 kHz mono 16-bit WAV (audio.play_wav plays them
without resampling) to TAKES_DIR, TAKES per prompt, and the volume folder is removed.

pick transcribes every take with the installed Hebrish model and keeps the one closest to the
phrase (ties: the shorter). Needed because Chatterbox invents words on one-word prompts: the
first single-take run (2026-10-22) gave "Kept that bit." for Copied, "Boom, it was discarded."
for Discarded, and three near-silent clips. Commit the picked WAVs; the app never generates
speech. Up to 0.6.3 the one voice was Microsoft's en-GB-RyanNeural via edge-tts
(scripts/make_voice.py, removed in 0.7.0).
"""

import difflib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP, VOLUME, VOL_DIR = "mwp-recording-app", "mwp-working-files", "private/hebrish-voice"
VOICES = {"herman": "Herman", "corn": "Corn", "hilbert": "Hilbert"}
DESKTOP = Path(__file__).resolve().parent.parent
OUT = DESKTOP / "hebrish" / "data" / "voice"
TAKES_DIR = Path(tempfile.gettempdir()) / "hebrish-voice-takes"
TAKES = int(__import__("os").environ.get("TAKES", 4))
PHRASES = {   # keys are audio.VOICE_PROMPTS
    "recording": "Recording.",
    "paused": "Paused.",
    "resumed": "Resumed.",
    "transcribing": "Transcribing.",
    "discarded": "Discarded.",
    "retake": "Starting again.",
    "copied": "Copied.",
    "no_speech": "No speech heard.",
    "failed": "Transcription failed.",
}
# Hilbert garbles one-word lines (2026-10-22: 10 takes of "Copied." and "Discarded." gave
# silence, "Well" or invented words), so he gets longer ones.
OVERRIDES = {"hilbert": {"paused": "Dictation paused.", "discarded": "Take discarded.",
                         "copied": "Copied to the clipboard."}}


def phrase(voice, key):
    return OVERRIDES.get(voice, {}).get(key, PHRASES[key])


TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse")


def render(voices):
    import time

    import modal
    run = time.strftime("%H%M%S")      # takes accumulate across runs; pick sees them all
    keys = __import__("os").environ.get("KEYS", "").split() or list(PHRASES)
    items = [{"segment_idx": n, "speaker": VOICES[v], "text": phrase(v, k), "key": k, "take": t}
             for n, (v, k, t) in enumerate((v, k, t) for v in voices for k in keys for t in range(TAKES))]
    fn = modal.Function.from_name(APP, "tts_worker")
    results = fn.remote([{x: it[x] for x in ("segment_idx", "speaker", "text")} for it in items],
                        f"/working/{VOL_DIR}")
    failed = [r for r in results if not r.get("success")]
    if failed:
        print(f"{len(failed)} takes failed: {failed[:3]}")
    with tempfile.TemporaryDirectory() as tmp:
        # Trailing slashes matter: without them every file lands on one local path.
        subprocess.run(["modal", "volume", "get", VOLUME, VOL_DIR + "/", tmp + "/"], check=True)
        files = {int(p.name.split("_")[1]): p for p in Path(tmp).rglob("segment_*.m4a")
                 if not p.name.endswith((".part.m4a", ".eq.m4a"))}
        for it in items:
            if it["segment_idx"] not in files:
                continue
            out = TAKES_DIR / it["speaker"].lower() / f"{it['key']}_{run}_{it['take']}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(files[it["segment_idx"]]),
                            "-af", TRIM, "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(out)],
                           check=True)
    subprocess.run(["modal", "volume", "rm", "-r", VOLUME, VOL_DIR], check=True)
    print("takes in", TAKES_DIR)


def _words(t):
    return re.sub(r"[^a-z ]", "", t.lower()).split()


def pick(voices):
    import wave

    import numpy as np
    sys.path.insert(0, str(DESKTOP))
    from hebrish import model_store
    from hebrish.engine import Engine
    eng = Engine()
    eng.load(model_store.active()[0])
    for v in voices:
        (OUT / v).mkdir(parents=True, exist_ok=True)
        for key in PHRASES:
            text = phrase(v, key)
            scored = []
            for f in sorted((TAKES_DIR / v).glob(f"{key}_*.wav")):
                with wave.open(str(f)) as w:
                    x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
                heard = eng.transcribe(x)
                score = difflib.SequenceMatcher(None, _words(heard), _words(text)).ratio()
                scored.append((-score, len(x), f, heard))
            if not scored:
                print(f"{v} {key}: no takes")
                continue
            neg, n, f, heard = min(scored)
            shutil.copy(f, OUT / v / f"{key}.wav")
            print(f"{v:8} {key:13} {-neg:.2f} {n / 16000:.1f}s {heard!r}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("render", "pick"):
        sys.exit(__doc__)
    if not shutil.which("ffmpeg"):
        sys.exit("needs ffmpeg")
    (render if sys.argv[1] == "render" else pick)(sys.argv[2:] or list(VOICES))

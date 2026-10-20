"""Regenerate the spoken status prompts in hebrish/data/voice/ (the "Voice" feedback mode).

    uv run --no-project --with edge-tts python3 scripts/make_voice.py

Needs ffmpeg and the network (edge-tts sends each phrase to Microsoft's TTS service). Same
voice as Daniel's Voice Notepad app (en-GB-RyanNeural). Output: 16 kHz mono 16-bit WAV, so
audio.play_wav can play it without resampling. Commit the WAVs; the app never generates speech.
"""

import asyncio
import subprocess
import tempfile
from pathlib import Path

import edge_tts

VOICE = "en-GB-RyanNeural"
OUT = Path(__file__).resolve().parent.parent / "hebrish" / "data" / "voice"
PHRASES = {   # keys are audio.VOICE_PROMPTS
    "recording": "Recording",
    "paused": "Paused",
    "resumed": "Resumed",
    "transcribing": "Transcribing",
    "discarded": "Discarded",
    "retake": "Starting again",
    "copied": "Copied",
    "no_speech": "No speech heard",
    "failed": "Transcription failed",
}


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for key, text in PHRASES.items():
        with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
            await edge_tts.Communicate(text, VOICE, rate="+10%").save(tmp.name)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp.name, "-af",
                            "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                            "silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                            "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(OUT / f"{key}.wav")],
                           check=True)
        print(key, (OUT / f"{key}.wav").stat().st_size)


asyncio.run(main())

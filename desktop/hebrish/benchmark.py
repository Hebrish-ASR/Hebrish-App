"""Inference benchmark: how fast and how heavy a transcription is on this machine, measured around
the app's own decode path (Daniel, 2026-11-05, B-94). Qt-free; the window is ui/benchmark.py.

Three sources: the reference file (REFERENCE, recognised by its SHA-256, so runs on different
machines are comparable and its length is a known constant), any audio file, or a recording.
Resources are sampled in-process: a command-line timer such as hyperfine can only time a whole
command, which would mix model load into the result and can't see this process's memory mid-decode.
Rows hold figures only: no transcript, no audio. Voice detection is off, so a run doesn't depend on
the user's settings.
"""

import ctypes
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import threading
import time

from . import __version__, model_store
from .audio import SAMPLE_RATE

# The first Hebrish podcast episode (hebrish.app/updates/2026-10-22). The CDN object is immutable.
# Hashed and probed 2026-11-05: ffprobe gives 4022.577188 s, mp3, mono, 44.1 kHz.
REFERENCE = {
    "name": "Hebrish update 1 (2026-10-22)",
    "url": "https://cdn.hebrish.app/site/updates/2026-10-22/hebrish-update-2026-10-22.mp3",
    "sha256": "38db0f57f42d685650d5b552bb570c952019a6c03d5d3175c60f2209d946ce19",
    "bytes": 48271999,
    "seconds": 4022.577,
}
MODE_LABEL = {"reference": f"Reference file: {REFERENCE['name']}", "file": "Own audio file", "recording": "Recording"}
SAMPLE_EVERY_S = 0.25


def cpu_name() -> str:
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def rss_mb() -> float | None:
    """Resident memory of this process, MB."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024
        except OSError:
            return None
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize",
                                               "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                               "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                               "PagefileUsage", "PeakPagefileUsage")]
        c = PMC()
        c.cb = ctypes.sizeof(c)
        if ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                    ctypes.byref(c), c.cb):
            return c.WorkingSetSize / 2**20
    return None


def ram_total_mb() -> int | None:
    try:
        if sys.platform == "win32":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
                    (n, ctypes.c_ulonglong) for n in ("total", "avail", "pt", "pa", "vt", "va", "ve")]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.total // 2**20
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 2**20
    except (OSError, ValueError, AttributeError):
        return None


def client_os() -> str:
    if sys.platform.startswith("linux"):
        try:
            return f"{platform.freedesktop_os_release()['PRETTY_NAME']} (Linux {platform.release()})"
        except (OSError, KeyError):
            pass
    return f"{platform.system()} {platform.release()}"


def _probe(cmd: list[str]) -> str:
    flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}     # no console flash
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3, **flags).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def gpu_name() -> str | None:
    """The GPU's name, best effort; None when there is none to report. Whether inference uses it
    is a separate question: see gpu_accel in system_info."""
    if shutil.which("nvidia-smi"):
        lines = _probe(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]).strip().splitlines()
        if lines:
            return lines[0].strip()
    if sys.platform == "win32":
        lines = _probe(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance Win32_VideoController).Name"]).strip().splitlines()
        return lines[0].strip() if lines else None
    if shutil.which("lspci"):
        for line in _probe(["lspci"]).splitlines():
            if " VGA " in line or "3D controller" in line or "Display controller" in line:
                return line.split(": ", 1)[-1].strip()
    vendor = model_store.detect_gpu()[0]
    return None if vendor == "none" else vendor


def system_info(engine) -> dict:
    """The machine and the inference setup, as benchmarks columns. Reads no audio; a few subprocess
    probes, so call it off the GUI thread."""
    try:
        import sherpa_onnx
        so = f"sherpa-onnx {sherpa_onnx.__version__}"
    except Exception:
        so = "sherpa-onnx"
    device = getattr(engine, "device", "CPU")
    cur = model_store.active()
    return {"client_os": client_os(), "app_version": __version__, "cpu_name": cpu_name(),
            "cpu_type": platform.machine(), "cpu_logical": os.cpu_count(), "ram_total_mb": ram_total_mb(),
            "gpu_name": gpu_name(), "gpu_accel": int(device != "CPU"), "inference_engine": so,
            "inference_device": device, "threads": engine.threads,
            "model": cur[1].full_label if cur else None, "model_id": model_store.current_id(),
            "model_rev": cur[1].revision if cur else None, "quantization": "int8",
            "streaming": int(engine.streaming)}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def _system_cpu() -> tuple[float, float] | None:
    """Cumulative (busy, total) CPU time of the whole machine, any unit; None if unavailable."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/stat") as f:
                v = [int(x) for x in f.readline().split()[1:9]]
            return sum(v) - v[3] - v[4], sum(v)
        except (OSError, ValueError, IndexError):
            return None
    if sys.platform == "win32":
        ft = [ctypes.c_ulonglong() for _ in range(3)]            # FILETIME: idle, kernel (has idle), user
        if ctypes.windll.kernel32.GetSystemTimes(*(ctypes.byref(x) for x in ft)):
            idle, kernel, user = (x.value for x in ft)
            return kernel + user - idle, kernel + user
    return None


class Sampler:
    """Memory and CPU load of this process over a run, on its own thread. Memory peak is sampled,
    not the OS high-water mark, which covers the process's whole life. CPU averages come from
    start and stop totals, so a run shorter than one interval still gets them. Process CPU covers
    all threads, so it includes the idle UI."""

    def __init__(self, every_s: float = SAMPLE_EVERY_S):
        self.every = every_s
        self._halt = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._rss: list[float] = []
        self._peak_cpu = 0.0

    def _sample(self):
        r = rss_mb()
        if r is not None:
            self._rss.append(r)

    def start(self):
        self._t0 = self._last_t = time.monotonic()
        self._c0 = self._last_c = time.process_time()
        self._s0 = _system_cpu()
        self._sample()
        self._thread.start()

    def _loop(self):
        while not self._halt.wait(self.every):
            self._sample()
            t, c = time.monotonic(), time.process_time()
            if t > self._last_t:
                self._peak_cpu = max(self._peak_cpu, (c - self._last_c) / (t - self._last_t))
            self._last_t, self._last_c = t, c

    def stop(self) -> dict:
        self._halt.set()
        self._thread.join()
        self._sample()
        wall = max(time.monotonic() - self._t0, 1e-9)
        cores = (time.process_time() - self._c0) / wall           # cores' worth of work, on average
        n = os.cpu_count() or 1
        s1 = _system_cpu()
        sys_pct = None
        if self._s0 and s1 and s1[1] > self._s0[1]:
            sys_pct = round(100 * (s1[0] - self._s0[0]) / (s1[1] - self._s0[1]), 1)
        rss = self._rss
        return {"ram_start_mb": round(rss[0]) if rss else None,
                "ram_avg_mb": round(sum(rss) / len(rss)) if rss else None,
                "ram_peak_mb": round(max(rss)) if rss else None,
                "cpu_avg_cores": round(cores, 2), "cpu_avg_pct": round(100 * cores / n, 1),
                "cpu_peak_pct": round(100 * max(self._peak_cpu, cores) / n, 1),
                "system_cpu_avg_pct": sys_pct}


def measure(engine, samples, audio_s: float | None = None, cancel=None) -> tuple[dict, str] | None:
    """Decode `samples` through Engine.transcribe_chunks and measure it: (figures, transcript), or
    None if cancelled. audio_s: the source's known length (the reference file), else from samples.
    inference_s covers the whole pipeline from samples to text, without file reading or model load."""
    audio_s = audio_s or len(samples) / SAMPLE_RATE
    newest = engine.stats[-1]["at"] if engine.stats else 0.0
    parts, first = [], None
    sampler = Sampler()
    sampler.start()
    t0 = time.monotonic()
    try:
        for text in engine.transcribe_chunks(samples, cancel=cancel, record=False):
            first = first if first is not None else time.monotonic() - t0
            parts.append(text)
    finally:
        took = time.monotonic() - t0
        load = sampler.stop()
    if cancel is not None and cancel.is_set():
        return None
    transcript = " ".join(parts)
    words = len(transcript.split())
    return {"audio_s": round(audio_s, 3), "inference_s": round(took, 3), "rtf": round(took / audio_s, 4),
            "speed_x": round(audio_s / took, 2), "first_text_s": None if first is None else round(first, 3),
            "words": words, "words_per_s": round(words / took, 1), "model_load_s": round(engine.load_s, 2),
            "disturbed": int(bool(engine.stats) and engine.stats[-1]["at"] > newest), **load}, transcript


def _clock(s: float) -> str:
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:04.1f}" if s >= 3600 else f"{int(s // 60)}:{s % 60:04.1f}"


def report(r: dict) -> str:
    """A run as Markdown, for the results box. No file name: it may be personal."""
    def v(key, unit=""):
        return "n/a" if r.get(key) is None else f"{r[key]}{unit}"
    gpu = r.get("gpu_name") or "none detected"
    rows = [("Source", MODE_LABEL.get(r["mode"], r["mode"])),
            ("Audio length", f"{_clock(r['audio_s'])} ({r['audio_s']} s)"),
            ("Inference time", f"{_clock(r['inference_s'])} ({r['inference_s']} s)"),
            ("Real-time factor", f"{r['rtf']} ({r['speed_x']}× real time)"),
            ("First text after", v("first_text_s", " s")),
            ("Words", f"{r['words']} ({r['words_per_s']} per second)"),
            ("RAM average / peak", f"{v('ram_avg_mb')} / {v('ram_peak_mb', ' MB')} (app, {v('ram_start_mb', ' MB')} at start)"),
            ("CPU average / peak", f"{v('cpu_avg_pct')}% / {v('cpu_peak_pct', '%')} of the machine ({v('cpu_avg_cores')} cores' worth)"),
            ("Whole system CPU", v("system_cpu_avg_pct", "%")),
            ("Model", f"{v('model')} ({v('quantization')})"),
            ("Inference engine", f"{v('inference_engine')}, {v('inference_device')}, {v('threads')} threads"),
            ("GPU acceleration", "yes" if r.get("gpu_accel") else "no"),
            ("CPU", f"{v('cpu_name')} ({v('cpu_type')}, {v('cpu_logical')} logical CPUs)"),
            ("GPU", gpu), ("RAM installed", v("ram_total_mb", " MB")), ("OS", v("client_os")),
            ("App", f"Hebrish {v('app_version')}")]
    when = time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(r["at"]))
    out = [f"## Hebrish benchmark, {when}", "", "| Measure | Result |", "| --- | --- |"]
    out += [f"| {k} | {val} |" for k, val in rows]
    if r.get("disturbed"):
        out += ["", "Another transcription ran during this benchmark, so these timings aren't clean."]
    return "\n".join(out)

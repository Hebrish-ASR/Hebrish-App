"""Microphones by identity, and the order to use them in (R-2026-10-25-2, Daniel 2026-10-25: "the
app stores ... microphones it's seen, vendor ID, product ID; the user can assign each a nickname
... and then ... input microphone preference ... the order to use upon which are available").

Every input the app sees is remembered in config `mics` under a stable key, with the user's alias
and mic type. With the Microphone setting on "Preferred order" (config `audio_device` ==
PREFERRED), each take opens the first mic in `mic_order` that is connected, else the system
default. The list is read again at every take, so plugging a headset in between takes is enough.

Linux: the sound server's sources (`pactl -f json list sources`) give vendor and product id,
serial and bus; the key is `<bus>:<vendor>:<product>:<serial>` (Bluetooth: `bluetooth:<address>`),
so a mic keeps its key across USB ports and card profiles. PortAudio opens it by the source name,
which its PulseAudio host API lists as a device; without that host API, by the ALSA card
(`(hw:<card>,<device>)`). Elsewhere (Windows, or no pactl), the key is `name:<device name>`: no
ids, and a renamed device counts as a new mic."""

import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass

import sounddevice as sd

PREFERRED = "@preferred"           # config audio_device / tm_audio_device: use mic_order
# Mic types, a label for the user (Daniel listed internal, shotgun, wireless headset, dynamic and
# lav). Nothing in the app depends on the type yet.
TYPES = [("", "Not set"), ("internal", "Built-in"), ("headset", "Headset"),
         ("wireless-headset", "Wireless headset"), ("earbuds", "Earbuds"), ("usb-desk", "USB desk mic"),
         ("condenser", "Condenser"), ("dynamic", "Dynamic"), ("shotgun", "Shotgun"),
         ("lavalier", "Lav (lavalier)"), ("wireless-lav", "Wireless lav"), ("handheld", "Handheld"),
         ("boundary", "Boundary / conference"), ("webcam", "Webcam"), ("interface", "Audio interface"),
         ("other", "Other")]
TYPE_LABELS = dict(TYPES)
_KEEP = ("label", "device", "vendor_id", "product_id", "serial", "bus")


@dataclass
class Mic:
    key: str
    device: str             # the sounddevice name to open it with; "" = can't be opened by name
    label: str              # what the system calls it
    vendor_id: str = ""     # USB/PCI ids, lower-case hex without 0x
    product_id: str = ""
    serial: str = ""
    bus: str = ""           # usb | pci | bluetooth | ...
    type_guess: str = ""    # a TYPES key, from the bus and form factor


def _hex(v) -> str:
    return str(v or "").lower().removeprefix("0x")


def _guess(props: dict) -> str:
    form, bus = props.get("device.form_factor") or "", props.get("device.bus") or ""
    if bus == "bluetooth":
        return "wireless-headset"
    if form in ("headset", "headphone", "handset"):
        return "headset"
    if form == "webcam":
        return "webcam"
    if form == "internal" or bus in ("pci", "platform"):
        return "internal"
    return ""


def _pactl_sources() -> list[dict] | None:
    if not (sys.platform.startswith("linux") and shutil.which("pactl")):
        return None
    try:
        out = subprocess.run(["pactl", "-f", "json", "list", "sources"], capture_output=True,
                             text=True, timeout=2).stdout
        return json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def input_names() -> list[str]:
    seen, out = set(), []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and d["name"] not in seen:
            seen.add(d["name"])
            out.append(d["name"])
    return out


def _from_sources(sources: list[dict], names: list[str]) -> list[Mic]:
    mics = []
    for s in sources:
        p = s.get("properties") or {}
        if p.get("device.class") == "monitor" or s.get("name", "").endswith(".monitor"):
            continue
        name, bus = s.get("name", ""), p.get("device.bus") or ""
        vid, pid, serial = _hex(p.get("device.vendor.id")), _hex(p.get("device.product.id")), p.get("device.serial") or ""
        if p.get("api.bluez5.address"):
            key = f"bluetooth:{p['api.bluez5.address'].lower()}"
        elif vid and pid:
            key = f"{bus or 'dev'}:{vid}:{pid}:{serial}"
        else:
            key = f"name:{name}"
        device = name if name in names else ""
        if not device and p.get("alsa.card") is not None:
            hw = f"(hw:{p['alsa.card']},{p.get('alsa.device', 0)})"
            device = next((n for n in names if hw in n), "")
        mics.append(Mic(key, device, s.get("description") or p.get("device.product.name") or name,
                        vid, pid, serial, bus, _guess(p)))
    return mics


_VIRTUAL = {"default", "pipewire", "pulse", "sysdefault", "Default Source", "dmix", "dsnoop"}


def list_mics() -> list[Mic]:
    """The microphones connected now. Re-reads the device list (refresh), so a mic plugged in
    since the app started is found."""
    refresh()
    names = input_names()
    sources = _pactl_sources()
    if sources is not None:
        return _from_sources(sources, names)
    return [Mic(f"name:{n}", n, n) for n in names if n not in _VIRTUAL]


# Streams open right now (Recorder, TapeRecorder): PortAudio can only be re-initialised without one.
OPEN: set = set()


def refresh():
    """Re-initialise PortAudio so its device list includes mics plugged in since it started
    (sounddevice's documented way). Skipped while a stream is open."""
    if OPEN:
        return
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def remember(known: dict, mics: list[Mic], now: float | None = None) -> bool:
    """Add newly seen mics to config `mics` (in place) and refresh what the system says about
    known ones; last_seen is a date, so a take doesn't rewrite the config every time. True if
    anything changed."""
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    changed = False
    for m in mics:
        e = known.get(m.key)
        if e is None:
            known[m.key] = e = {"alias": "", "type": m.type_guess, "first_seen": day}
            changed = True
        fresh = {k: v for k, v in asdict(m).items() if k in _KEEP}
        fresh["last_seen"] = day
        if any(e.get(k) != v for k, v in fresh.items()):
            e.update(fresh)
            changed = True
    return changed


def ordered(known: dict, order: list[str]) -> list[str]:
    """Every known key, in the user's order first, then the rest as first seen."""
    head = [k for k in order if k in known]
    return head + [k for k in known if k not in head]


def pick(order: list[str], mics: list[Mic]) -> Mic | None:
    """The first mic in order that is connected and can be opened."""
    here = {m.key: m for m in mics if m.device}
    return next((here[k] for k in order if k in here), None)


def name(entry: dict) -> str:
    """How a known mic is shown: its alias, else what the system calls it."""
    return entry.get("alias") or entry.get("label") or "Microphone"


def resolve(cfg, setting: str = "audio_device") -> tuple[str, str]:
    """(device to open, how to name it) for a mic setting: "" (system default), PREFERRED, or a
    device name. PREFERRED also records the mics it sees in cfg["mics"]."""
    dev = cfg[setting]
    if dev != PREFERRED:
        return dev, dev
    mics = list_mics()
    known = cfg["mics"]
    if remember(known, mics):
        cfg.set("mics", known)
    m = pick(ordered(known, cfg["mic_order"]), mics)
    return (m.device, name(known[m.key])) if m else ("", "")

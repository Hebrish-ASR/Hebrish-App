"""R-2026-10-25-2 (Daniel, 2026-10-25): remembered microphones with an alias and a type, used in
a preferred order when connected. pactl output and PortAudio names are faked: nothing opens a mic."""

import os

import pytest

from hebrish import mics

# The shape of `pactl -f json list sources` (PipeWire 1.4, Ubuntu 26.04), trimmed to what is read.
JABRA = {"name": "alsa_input.usb-GN_Audio_A_S_Jabra_EVOLVE_30_II_00034A1A775E08-00.mono-fallback",
         "description": "Jabra EVOLVE 30 II Mono",
         "properties": {"device.vendor.id": "0x0b0e", "device.product.id": "0x0314",
                        "device.serial": "GN_Audio_A_S_Jabra_EVOLVE_30_II_00034A1A775E08", "device.bus": "usb",
                        "device.class": "sound", "alsa.card": "2", "alsa.device": "0"}}
LAPTOP = {"name": "alsa_input.pci-0000_04_00.6.analog-stereo", "description": "Laptop internal mic",
          "properties": {"device.vendor.id": "0x1022", "device.product.id": "0x15e3", "device.bus": "pci",
                         "device.class": "sound", "alsa.card": "1", "alsa.device": "0"}}
MONITOR = {"name": "alsa_output.pci-0000_04_00.6.analog-stereo.monitor", "description": "Monitor of Ryzen",
           "properties": {"device.class": "monitor", "device.bus": "pci"}}
BT = {"name": "bluez_input.AA_BB_CC_DD_EE_FF.0", "description": "WH-1000XM4",
      "properties": {"api.bluez5.address": "AA:BB:CC:DD:EE:FF", "device.bus": "bluetooth"}}
NAMES = [JABRA["name"], LAPTOP["name"], MONITOR["name"], BT["name"], "default", "pulse"]


def test_sources_become_mics_by_identity():
    got = {m.key: m for m in mics._from_sources([JABRA, LAPTOP, MONITOR, BT], NAMES)}
    assert set(got) == {"usb:0b0e:0314:GN_Audio_A_S_Jabra_EVOLVE_30_II_00034A1A775E08",
                        "pci:1022:15e3:", "bluetooth:aa:bb:cc:dd:ee:ff"}      # no monitor
    j = got["usb:0b0e:0314:GN_Audio_A_S_Jabra_EVOLVE_30_II_00034A1A775E08"]
    assert (j.device, j.label, j.vendor_id, j.product_id, j.bus) == (JABRA["name"], "Jabra EVOLVE 30 II Mono",
                                                                    "0b0e", "0314", "usb")
    assert got["pci:1022:15e3:"].type_guess == "internal"
    assert got["bluetooth:aa:bb:cc:dd:ee:ff"].type_guess == "wireless-headset"


def test_alsa_only_portaudio_opens_by_card():
    # PortAudio without its PulseAudio host API lists "<card>: <pcm> (hw:N,M)" names
    m, = mics._from_sources([JABRA], ["Jabra EVOLVE 30 II: USB Audio (hw:2,0)", "HD-Audio (hw:1,0)"])
    assert m.device == "Jabra EVOLVE 30 II: USB Audio (hw:2,0)"


def test_remember_keeps_alias_and_type():
    known = {}
    found = mics._from_sources([JABRA, LAPTOP], NAMES)
    assert mics.remember(known, found, now=0)
    key = found[0].key
    known[key].update(alias="Desk headset", type="headset")
    assert not mics.remember(known, found, now=0)                 # same day, nothing new
    assert mics.remember(known, found, now=86400 * 3)             # a later day: last_seen moves
    assert known[key]["alias"] == "Desk headset" and known[key]["type"] == "headset"
    assert known[key]["first_seen"] == "1970-01-01"


def test_pick_follows_the_order_and_skips_what_is_gone():
    found = mics._from_sources([JABRA, LAPTOP, BT], NAMES)
    keys = [m.key for m in found]
    order = [keys[2], keys[0], keys[1]]
    assert mics.pick(order, found).key == keys[2]
    assert mics.pick(order, found[:2]).key == keys[0]              # Bluetooth headset off
    assert mics.pick(order, []) is None
    assert mics.ordered({k: {} for k in keys}, [keys[1]]) == [keys[1], keys[0], keys[2]]


class Cfg(dict):
    def set(self, k, v):
        self[k] = v


def test_resolve(monkeypatch):
    found = mics._from_sources([JABRA, LAPTOP], NAMES)
    monkeypatch.setattr(mics, "list_mics", lambda: found)
    cfg = Cfg(audio_device=mics.PREFERRED, mics={}, mic_order=[found[1].key, found[0].key])
    assert mics.resolve(cfg) == (LAPTOP["name"], "Laptop internal mic")
    assert set(cfg["mics"]) == {found[0].key, found[1].key}       # seen, so remembered
    cfg["mics"][found[0].key]["alias"] = "Jabra"
    cfg["mic_order"] = [found[0].key]
    assert mics.resolve(cfg) == (JABRA["name"], "Jabra")
    monkeypatch.setattr(mics, "list_mics", lambda: [])
    assert mics.resolve(cfg) == ("", "")                          # nothing connected: system default
    cfg["audio_device"] = "some device"
    assert mics.resolve(cfg) == ("some device", "some device")


def test_refresh_waits_for_open_streams(monkeypatch):
    calls = []
    monkeypatch.setattr(mics.sd, "_terminate", lambda: calls.append("t"))
    monkeypatch.setattr(mics.sd, "_initialize", lambda: calls.append("i"))
    mics.OPEN.add("stream")
    try:
        mics.refresh()
        assert calls == []
    finally:
        mics.OPEN.discard("stream")
    mics.refresh()
    assert calls == ["t", "i"]


def test_settings_card_orders_names_and_switches(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from hebrish.ui.mics import MicsCard, in_use
    found = mics._from_sources([JABRA, LAPTOP], NAMES)
    monkeypatch.setattr(mics, "list_mics", lambda: found)
    cfg = Cfg(audio_device="", mics={}, mic_order=[])
    changed = []
    card = MicsCard(cfg, lambda: changed.append(1))
    assert card.table.rowCount() == 2 and card.table.item(0, 4).text() == "Connected"
    card.table.item(1, 1).setText("Built-in")                      # alias for the laptop mic
    assert cfg["mics"][found[1].key]["alias"] == "Built-in"
    card.table.selectRow(1)
    card._move(-1)
    assert cfg["mic_order"] == [found[1].key, found[0].key]
    card.table.cellWidget(1, 2).setCurrentIndex(card.table.cellWidget(1, 2).findData("headset"))
    assert cfg["mics"][found[0].key]["type"] == "headset"
    card.use.setChecked(True)
    assert cfg["audio_device"] == mics.PREFERRED and changed
    assert in_use(cfg) == "Built-in (preferred order)"
    card.table.selectRow(0)
    card._forget()                                                 # connected: stays
    assert found[1].key in cfg["mics"]

"""The local API's control endpoints that touch the running app (B-87; hebrish.local_api serves
them and owns history and dictionary). Called on HTTP threads: network checks run right there,
anything touching the Controller or the window goes through `_main`, onto the GUI thread.

Raises what local_api turns into a status: LookupError 404, ValueError 400, RuntimeError 409.
"""

import threading

from .. import __version__, app_update, bundles, mics, model_store
from ..config import HISTORY_DB

MAIN_TIMEOUT = 10


def _bool(v):
    if not isinstance(v, bool):
        raise ValueError("must be true or false")
    return v


def _choice(*allowed):
    def check(v):
        if v not in allowed:
            raise ValueError("must be one of " + ", ".join(f'"{a}"' for a in allowed))
        return v
    return check


def _int(lo, hi, also=()):
    def check(v):
        if isinstance(v, bool) or not isinstance(v, int) or not (lo <= v <= hi or v in also):
            extra = "".join(f" or {a}" for a in also)
            raise ValueError(f"must be a whole number from {lo} to {hi}{extra}")
        return v
    return check


def _chord(v):
    from ..inserter import parse_chord
    if not isinstance(v, str) or not v.strip():
        raise ValueError('must be a shortcut such as "ctrl+v"')
    parse_chord(v)              # ValueError names the bad key
    return v.strip().lower()


# GET/POST /v1/app/settings (2026-11-16): the settings an agent may change, each with its check.
# Only settings the app reads when it uses them (no restart, nothing to rebuild), so a change takes
# effect at the next take. Paths, hotkeys, models and the local API's own switches are left out on
# purpose: a wrong value there can lock the user out or needs a dialog. input_language, the
# microphones (/v1/app/mics) and models have their own routes.
SETTINGS = {
    "out_cursor": (_bool, "Output: paste at the cursor"),
    "out_clipboard": (_bool, "Output: copy each take to the clipboard (keeps it there after the paste)"),
    "out_window": (_bool, "Output: show takes in the Hebrish window"),
    "paste_chord": (_chord, "The paste shortcut, e.g. ctrl+v or ctrl+shift+v"),
    "send_chord": (_chord, "The send key for Stop and send / Enter after silence, e.g. enter or ctrl+enter"),
    "trailing_space": (_bool, "A space after each pasted take"),
    "bind_pane": (_bool, "A take goes to the Konsole pane it started in"),
    "bind_window": (_bool, "KDE: a take's pastes go back to the window it started in"),
    "detect_no_field": (_bool, "Ask accessibility whether a text field had focus; offer Paste if not"),
    "auto_enter": (_bool, "Press the send key after a silence"),
    "auto_enter_s": (_int(2, 60), "Seconds of silence before that send key"),
    "enter_stops": (_bool, "Enter during a take stops it"),
    "enter_guard": (_choice("late", "hold", "off"), "Words still coming when you press Enter: late = keep for Paste, hold = hold Enter, off = paste anyway"),
    "live_insert_s": (_int(3, 60, also=(0,)), "Insert as you go: seconds between pastes; 0 = everything when you stop"),
    "stream_release": (_choice("word", "phrase", "sentence"), "Streaming models: paste every word, phrase or sentence"),
    "all_caps": (_bool, "Transcripts in capitals"),
    "no_final_stop": (_bool, "Drop the full stop at the end of a take"),
    "clear_each_take": (_bool, "Clear the Dictate box at each take"),
    "feedback": (_choice("beeps", "voice", "off"), "Start and stop sounds"),
    "beep_volume": (_int(0, 100), "Sound volume, percent"),
    "quiet_hours": (_bool, "Quiet hours on"),
    "vad": (_bool, "Voice detection (skip silence)"),
}
OUTPUTS = ("out_cursor", "out_clipboard", "out_window")
MIC_SETTINGS = {"audio_device": "Voice Typing (dictation)", "tm_audio_device": "Transcription Mode"}

# POST /v1/app/dictation (B-87; the rest 2026-11-17, B-104): each runs the action key's handler
# (Controller.do_action), so the API does exactly what the key does. pause and resume are the
# Pause key split in two, so an agent can't toggle the wrong way.
DICTATION = {
    "start": "Start a take (resumes a paused one)",
    "stop": "Stop the take; its text goes where the outputs say",
    "toggle": "Start, or stop the take",
    "pause": "Pause the take (nothing if already paused)",
    "resume": "Resume a paused take (nothing if not paused)",
    "retake": "Discard the take and start a new one",
    "discard": "Discard the take; text already inserted stays",
    "send": "Stop, then press the send key once the last text is in",
    "paste_last": "Paste the last transcription at the cursor (when idle)",
}


class Control:
    history_path = HISTORY_DB

    def __init__(self, ctl):
        self.ctl = ctl
        self.routes = {
            ("GET", "/v1/app/status"): self.status,
            ("POST", "/v1/app/dictation"): self.dictation,
            ("GET", "/v1/app/update"): self.check_app,
            ("POST", "/v1/app/update"): self.install_app,
            ("POST", "/v1/app/restart"): self.restart,
            ("GET", "/v1/app/models"): self.models,
            ("POST", "/v1/app/models/select"): self.select_model,
            ("GET", "/v1/app/language"): self.language,
            ("POST", "/v1/app/language"): self.set_language,
            ("GET", "/v1/app/settings"): self.settings,
            ("POST", "/v1/app/settings"): self.set_settings,
            ("GET", "/v1/app/mics"): self.mics,
            ("POST", "/v1/app/mics"): self.set_mics,
            ("GET", "/v1/app/models/updates"): self.check_models,
            ("POST", "/v1/app/models/updates"): self.install_models,
        }

    def enabled(self) -> bool:
        return bool(self.ctl.cfg["local_api_control"])

    def handle(self, method: str, path: str, body: dict) -> tuple[int, dict]:
        fn = self.routes.get((method, path))
        if fn is None:
            raise LookupError(f"no route {method} {path}")
        return fn(body)

    def _main(self, fn):
        """Run fn on the GUI thread and return its result. A modal dialog there doesn't stop this:
        it spins its own event loop. A timeout means the app didn't answer, so say so."""
        done, box = threading.Event(), {}

        def run():
            try:
                box["value"] = fn()
            except Exception as e:
                box["error"] = e
            done.set()
        self.ctl.sig.call.emit(run)
        if not done.wait(MAIN_TIMEOUT):
            raise TimeoutError("the app didn't answer in time")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def edit_history(self, rid: int, text: str) -> dict:
        """PATCH /v1/history/{id}: History.update_text through the app's own connection (GUI
        thread), as the History tab's Correct does, then the tab is redrawn. Same text: nothing."""
        c = self.ctl

        def go():
            row = c.history.get(rid)
            if row is None:
                raise LookupError(f"no transcript {rid}")
            if row["text"] == text.strip():
                return row, False
            c.history.update_text(rid, text)
            c.win.show_history(keep_limit=True)
            return c.history.get(rid), True
        row, changed = self._main(go)
        return {**row, "changed": changed}

    def delete_history(self, rid: int) -> dict:
        """DELETE /v1/history/{id}, as the History tab's Delete."""
        c = self.ctl

        def go():
            if c.history.get(rid) is None:
                raise LookupError(f"no transcript {rid}")
            c.history.delete(rid)
            c.win.show_history(keep_limit=True)
        self._main(go)
        return {"id": rid, "deleted": True}

    def dictionary_changed(self):
        self.ctl.sig.call.emit(lambda: self.ctl.win._dict_show())

    def status(self, _body) -> tuple[int, dict]:
        c = self.ctl
        return 200, {
            "app": __version__, **self.take_state(), "model": c.api_info(),
            "input_language": c.cfg["input_language"], "keep_history": bool(c.cfg["keep_history"]),
            "install_method": c.app_method,
            "app_update": {"running": c.app_updating, "available": c.app_release.version if c.app_release else None,
                           "installed_needs_restart": c.app_installed or None, "error": c.app_update_error},
            "models": {"downloading": c.downloading_id, "queued": len(c.model_queue),
                       "addons_downloading": sorted(c.addon_busy)},
        }

    def take_state(self) -> dict:
        c = self.ctl
        return {"state": c.state, "paused": c.state == "recording" and bool(c.recorder.paused)}

    def dictation(self, body) -> tuple[int, dict]:
        """The action keys (DICTATION). 409 when the action has nothing to act on, rather than the
        key's silent no-op, so an agent knows."""
        action = body.get("action")
        if action not in DICTATION:
            raise ValueError("action must be one of " + ", ".join(DICTATION))
        c = self.ctl

        def go():
            rec = c.state == "recording"
            if action in ("pause", "resume", "discard") and not rec:
                raise RuntimeError(f"no take is recording (the app is {c.state})")
            if action == "send" and not (rec or (c.state == "busy" and c.pending)):
                raise RuntimeError(f"no take to send (the app is {c.state})")
            if action == "paste_last" and c.state != "idle":
                raise RuntimeError(f"the app is {c.state}: paste the last take when it is idle")
            if action in ("pause", "resume"):
                if c.recorder.paused != (action == "pause"):
                    c.do_action("pause")
                return
            c.do_action(action)
        self._main(go)
        return 200, {"action": action, **self.take_state()}

    def _mic_list(self):
        """GUI thread: the connected mics (PortAudio re-initialised, as the mic boxes do), each new
        one remembered in config `mics`, and what each mic setting uses now."""
        from .mics import in_use
        c = self.ctl
        found = mics.list_mics()
        known = c.cfg["mics"]
        if mics.remember(known, found):
            c.cfg.set("mics", known)
        here = [{"value": m.device, "key": m.key, "name": mics.name(known.get(m.key, {"label": m.label})),
                 "label": m.label, "type": known.get(m.key, {}).get("type") or m.type_guess or None,
                 "bus": m.bus or None} for m in found if m.device]
        order = [mics.name(known[k]) for k in mics.ordered(known, c.cfg["mic_order"])]
        current = {k: {"for": what, "value": c.cfg[k], "in_use": in_use(c.cfg, k)} for k, what in MIC_SETTINGS.items()}
        return here, order, current

    def mics(self, _body) -> tuple[int, dict]:
        here, order, current = self._main(self._mic_list)
        return 200, {**current, "choices": [
            {"value": "", "name": "System default"},
            {"value": mics.PREFERRED, "name": "Preferred order (Settings → Microphones)", "order": order},
            *here]}

    def set_mics(self, body) -> tuple[int, dict]:
        """Body {"audio_device": ..., "tm_audio_device": ...}, either or both: "" (system default),
        "@preferred", or a connected mic by `value` (device name) or `key`. As choosing in the tab's
        mic box: the boxes are refilled, a running Test mic follows. Transcription Mode's mic is not
        switched under a running recording (409): the tab does that with a dialog on failure."""
        if not isinstance(body, dict) or not body or set(body) - set(MIC_SETTINGS):
            raise ValueError("send audio_device and/or tm_audio_device (GET /v1/app/mics lists the choices)")
        c = self.ctl

        def go():
            here, _, _ = self._mic_list()
            by = {m["value"]: m["value"] for m in here} | {m["key"]: m["value"] for m in here}
            new = {}
            for k, v in body.items():
                if v in ("", mics.PREFERRED):
                    new[k] = v
                elif isinstance(v, str) and v in by:
                    new[k] = by[v]
                else:
                    raise ValueError(f"{k}: {v!r} is not a connected microphone (GET /v1/app/mics lists them)")
            if "tm_audio_device" in new and new["tm_audio_device"] != c.cfg["tm_audio_device"] \
                    and c.win.transcribe.tape.active:
                raise RuntimeError("Transcription Mode is recording: change its mic when it has stopped")
            changed = [k for k, v in new.items() if c.cfg[k] != v]
            for k in changed:
                c.cfg.set(k, new[k])
            if changed:
                c.win.mics_changed()            # both mic boxes and the "In use" line
                if hasattr(c.win, "mics_card"):
                    c.win.mics_card.sync()
                if "audio_device" in changed and c.monitor.active:     # Test mic follows, as in the tab
                    c.stop_monitor()
                    c.win._on_test(True)
            return changed
        changed = self._main(go)
        code, out = self.mics(body)
        return code, {"changed": changed, **out}

    def check_app(self, _body) -> tuple[int, dict]:
        rel = app_update.fetch()
        method = self.ctl.app_method
        newer = app_update.is_newer(rel.version)
        return 200, {"current": __version__, "latest": rel.version, "update_available": newer,
                     "method": method, "can_install": newer and method == "apt",
                     "download_page": app_update.download_page(method)}

    def install_app(self, _body) -> tuple[int, dict]:
        c = self.ctl
        method = c.app_method
        if method != "apt":
            raise RuntimeError(f"this install ({method}) updates from {app_update.download_page(method)}")
        rel = app_update.fetch()
        if not app_update.is_newer(rel.version):
            return 200, {"status": "up_to_date", "current": __version__}
        if c.app_installed and not app_update.is_newer(rel.version, c.app_installed):
            return 200, {"status": "installed_needs_restart", "version": c.app_installed}

        def go():
            if c.app_updating:
                return
            c.app_release, c.app_update_error = rel, None
            c.app_update_action()
        self._main(go)
        return 202, {"status": "started", "version": rel.version,
                     "note": "the user approves a system password prompt; poll GET /v1/app/status"}

    def restart(self, _body) -> tuple[int, dict]:
        c = self.ctl
        if not c.app_installed:
            raise RuntimeError("no update is waiting for a restart")
        if c.state != "idle":
            raise RuntimeError(f"the app is {c.state}: restart when it is idle")
        c.sig.call.emit(c.restart)         # the reply goes out while the app is still up
        return 202, {"status": "restarting"}

    def models(self, _body) -> tuple[int, dict]:
        cur, rec = model_store.current_id(), model_store.recommended_id()
        have = set(model_store.installed_ids())
        data = []
        for m in model_store.models():
            act = model_store.active(m.id) if m.id in have else None
            data.append({"id": m.id, "name": m.name, "line": m.line, "available": m.available,
                         "streaming": m.streaming, "download_mb": m.download_mb, "installed": m.id in have,
                         "version": act[1].label if act else None, "current": m.id == cur,
                         "recommended": m.id == rec, "language": m.language or None})
        return 200, {"object": "list", "data": data}

    def select_model(self, body) -> tuple[int, dict]:
        mid, c = body.get("id"), self.ctl
        m = model_store.get_model(mid) if isinstance(mid, str) else None
        if m is None:
            raise LookupError(f"no model {mid!r}; GET /v1/app/models lists them")
        if m.language:
            raise ValueError(f"{mid} is the Hebrew model: it is used by input language (POST /v1/app/language), "
                             "not selected")
        if c.state != "idle":
            raise RuntimeError(f"the app is {c.state}: switch models when it is idle")
        if mid in model_store.installed_ids():
            self._main(lambda: c.use_model(mid))
            return 200, {"status": "selected", "id": mid}
        if not body.get("download"):
            raise RuntimeError(f'{mid} is not downloaded ({m.download_mb} MB): send "download": true')
        if not m.available:
            raise RuntimeError(f"{mid} can't run on this computer")
        if c.downloading:
            raise RuntimeError("another model is downloading")
        self._main(lambda: c.select_model(mid))
        return 202, {"status": "downloading", "id": mid}

    def language(self, _body) -> tuple[int, dict]:
        """Hebrew switching (2026-11-16): the setting, the Hebrew model, the last take's language."""
        c = self.ctl
        m, cur = c.hebrew_install()
        last = c.last_lang
        return 200, {
            "input_language": c.cfg["input_language"], "choices": ["auto", "en", "he"],
            "hebrew_model": None if m is None else {
                "id": m.id, "installed": cur is not None, "version": cur[1].label if cur else None,
                "loaded": c.he_engine.loaded_dir is not None, "download_mb": m.download_mb},
            "last_take": None if last is None else {k: last[k] for k in ("lang", "wanted", "source", "method", "layout")},
        }

    def set_language(self, body) -> tuple[int, dict]:
        value = body.get("input_language")
        if value not in ("auto", "en", "he"):
            raise ValueError('input_language must be "auto", "en" or "he"')
        self._main(lambda: self.ctl.set_input_language(value))
        return self.language(body)

    def settings(self, _body) -> tuple[int, dict]:
        cfg = self.ctl.cfg
        return 200, {"settings": {k: cfg[k] for k in SETTINGS},
                     "help": {k: d for k, (_, d) in SETTINGS.items()}}

    def set_settings(self, body) -> tuple[int, dict]:
        """Body {"key": value, ...}: all checked first, then all applied, or none (400 names the
        first bad one). At least one output stays on, as in the window."""
        if not isinstance(body, dict) or not body:
            raise ValueError('send the settings to change, e.g. {"out_clipboard": false}')
        unknown = sorted(set(body) - set(SETTINGS))
        if unknown:
            raise ValueError(f"not a setting this route changes: {', '.join(unknown)} (GET /v1/app/settings lists them)")
        new = {}
        for k, v in body.items():
            try:
                new[k] = SETTINGS[k][0](v)
            except ValueError as e:
                raise ValueError(f"{k} {e}") from None
        c = self.ctl
        if not any(new.get(k, c.cfg[k]) for k in OUTPUTS):
            raise ValueError("at least one output (out_cursor, out_clipboard, out_window) must stay on")

        def apply():
            changed = [k for k, v in new.items() if c.cfg[k] != v]
            for k in changed:
                c.cfg.set(k, new[k])
            if changed and (set(changed) & {*OUTPUTS, "paste_chord"}):
                c.win.sync_output()
            if "vad" in changed:
                c.apply_vad()
                c.sync_tray_vad()
            return changed
        changed = self._main(apply)
        code, out = self.settings(body)
        return code, {"changed": changed, **out}

    @staticmethod
    def _updates(ups) -> dict:
        return {"models": [{"id": m.model, "version": m.label} for m in ups.models],
                "addons": list(ups.addons), "errors": [{"id": i, "error": e} for i, e in ups.errors]}

    def check_models(self, _body) -> tuple[int, dict]:
        model_store.refresh_catalogue()
        return 200, self._updates(bundles.check())

    def install_models(self, _body) -> tuple[int, dict]:
        c = self.ctl
        model_store.refresh_catalogue()
        ups = bundles.check()

        def go():
            c.updates = ups
            c.update_all()
        if len(ups):
            self._main(go)
        return (202 if len(ups) else 200), {"status": "started" if len(ups) else "up_to_date", **self._updates(ups)}

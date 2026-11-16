"""The local API's control endpoints that touch the running app (B-87; hebrish.local_api serves
them and owns history and dictionary). Called on HTTP threads: network checks run right there,
anything touching the Controller or the window goes through `_main`, onto the GUI thread.

Raises what local_api turns into a status: LookupError 404, ValueError 400, RuntimeError 409.
"""

import threading

from .. import __version__, app_update, bundles, model_store
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
# effect at the next take. Paths, hotkeys, models, the microphone and the local API's own switches
# are left out on purpose: a wrong value there can lock the user out or needs a dialog.
# input_language has its own route (/v1/app/language).
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

    def dictionary_changed(self):
        self.ctl.sig.call.emit(lambda: self.ctl.win._dict_show())

    def status(self, _body) -> tuple[int, dict]:
        c = self.ctl
        return 200, {
            "app": __version__, "state": c.state, "model": c.api_info(),
            "input_language": c.cfg["input_language"], "keep_history": bool(c.cfg["keep_history"]),
            "install_method": c.app_method,
            "app_update": {"running": c.app_updating, "available": c.app_release.version if c.app_release else None,
                           "installed_needs_restart": c.app_installed or None, "error": c.app_update_error},
            "models": {"downloading": c.downloading_id, "queued": len(c.model_queue),
                       "addons_downloading": sorted(c.addon_busy)},
        }

    def dictation(self, body) -> tuple[int, dict]:
        action = body.get("action")
        if action not in ("start", "stop", "toggle"):
            raise ValueError("action must be start, stop or toggle")
        self._main(getattr(self.ctl, action))
        return 200, {"state": self.ctl.state}

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

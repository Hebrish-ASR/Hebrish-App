"""The local API's control endpoints that touch the running app (B-87; hebrish.local_api serves
them and owns history and dictionary). Called on HTTP threads: network checks run right there,
anything touching the Controller or the window goes through `_main`, onto the GUI thread.

Raises what local_api turns into a status: LookupError 404, ValueError 400, RuntimeError 409.
"""

import threading

from .. import __version__, app_update, bundles, model_store
from ..config import HISTORY_DB

MAIN_TIMEOUT = 10


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
            "app": __version__, "state": c.state, "model": c.api_info(), "keep_history": bool(c.cfg["keep_history"]),
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
                         "recommended": m.id == rec})
        return 200, {"object": "list", "data": data}

    def select_model(self, body) -> tuple[int, dict]:
        mid, c = body.get("id"), self.ctl
        m = model_store.get_model(mid) if isinstance(mid, str) else None
        if m is None:
            raise LookupError(f"no model {mid!r}; GET /v1/app/models lists them")
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

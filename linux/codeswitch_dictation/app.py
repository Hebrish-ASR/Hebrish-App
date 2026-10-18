"""GTK app: tray icon, main window, and the controller tying hotkey, mic, model and paste together.

Threads: the hotkey listener and all slow work (model load, decode, HF check, download)
run off the GTK thread and come back through GLib.idle_add.
"""

import logging
import shutil
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, Gio, GLib, Gtk  # noqa: E402

from . import __version__, audio, model_store  # noqa: E402
from .config import APP_ID, APP_NAME, CONFIG_PATH, STATE_PATH, Config, load_json, save_json  # noqa: E402
from .engine import Engine  # noqa: E402
from .hotkey import HotkeyListener, key_code  # noqa: E402
from .inserter import Inserter, copy_to_clipboard, parse_chord  # noqa: E402

AUTOSTART = GLib.get_user_config_dir() + "/autostart/codeswitch-dictation.desktop"
ICONS = {"idle": "audio-input-microphone-muted", "recording": "media-record",
         "busy": "emblem-synchronizing", "nomodel": "dialog-warning"}
HISTORY = 20
log = logging.getLogger("codeswitch-dictation")


def ui(fn):
    """Run fn(*args) on the GTK thread."""
    def wrapper(*args, **kw):
        GLib.idle_add(lambda: (fn(*args, **kw), False)[1])
    return wrapper


def notify(summary, body=""):
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", APP_NAME, "-i", ICONS["idle"], summary, body])


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.add_main_option("toggle", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Start or stop dictation in the running instance", None)
        self.add_main_option("hidden", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             "Start in the tray without showing the window", None)
        self.cfg = Config()
        self.engine = Engine()
        self.recorder = audio.Recorder()
        self.inserter = None
        self.hotkeys = None
        self.state = "idle"             # idle | recording | busy
        self.history: list[str] = []
        self.latest: model_store.Manifest | None = None
        self.downloading = None         # threading.Event (cancel) while a download runs
        self.reload_pending = False
        self.win = None

    # -- lifecycle ---------------------------------------------------------------
    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()                     # the tray keeps us alive with no window
        self.inserter = Inserter()
        self.hotkeys = HotkeyListener(self.cfg, ui(self.start), ui(self.stop),
                                      ui(self.cancel), lambda: self.state == "recording")
        self.hotkeys.start()
        self._build_tray()
        self.win = MainWindow(self)
        self.load_model()
        GLib.timeout_add_seconds(10, self._first_check)
        GLib.timeout_add_seconds(600, self._periodic_check)
        GLib.timeout_add_seconds(4, self._startup_warnings)

    def do_command_line(self, cmdline):
        opts = cmdline.get_options_dict().end().unpack()
        if opts.get("toggle"):
            self.toggle()
        elif not opts.get("hidden") or not model_store.installed():
            self.win.present()
        return 0

    def _startup_warnings(self):
        if self.hotkeys.permission_denied:
            self.win.banner("Can't read /dev/input, so the hotkey is off. Add yourself to "
                            "the 'input' group (sudo usermod -aG input $USER) and log in "
                            "again. Until then: tray menu, window button, or "
                            "`codeswitch-dictation --toggle` bound to a desktop shortcut.")
        elif self.inserter.error:
            self.win.banner(self.inserter.error)
        return False

    # -- dictation -----------------------------------------------------------------
    def toggle(self):
        self.stop() if self.state == "recording" else self.start()

    def start(self):
        if self.state != "idle":
            return
        if self.engine.loaded_dir is None and not model_store.active():
            self.win.present()
            self.win.banner("The model isn't downloaded yet.")
            return
        try:
            self.recorder.start(self.cfg["audio_device"])
        except Exception as e:
            notify("Microphone error", str(e))
            return
        if self.cfg["beeps"]:
            audio.beep(880)
        self.set_state("recording")

    def cancel(self):
        if self.state == "recording":
            self.recorder.stop()
            self.set_state("idle")

    def stop(self):
        if self.state != "recording":
            return
        samples = self.recorder.stop()
        if self.cfg["beeps"]:
            audio.beep(620)
        self.set_state("busy")
        threading.Thread(target=self._transcribe, args=(samples,), daemon=True).start()

    def _transcribe(self, samples):
        try:
            text = self.engine.transcribe(samples)
            if text:
                if self.cfg["trailing_space"]:
                    text += " "
                self.inserter.insert(text, self.cfg["insert"], self.cfg["paste_chord"])
            ui(self._done)(text, None)
        except Exception as e:
            ui(self._done)("", e)

    def _done(self, text, err):
        log.info("transcript %r err=%r", text, err)
        if err:
            notify("Transcription failed", str(err))
        elif text:
            self.history = ([text.strip()] + self.history)[:HISTORY]
            self.win.show_history()
        self.set_state("idle")
        if self.reload_pending:
            self.load_model()

    def set_state(self, state):
        log.info("state %s -> %s", self.state, state)
        self.state = state
        self._update_tray()
        self.win.update_state()

    # -- model -------------------------------------------------------------------
    def load_model(self):
        """(Re)load the active install. Deferred while a take is in flight."""
        if self.state != "idle":
            self.reload_pending = True
            return
        self.reload_pending = False
        cur = model_store.active()
        if cur is None:
            self.engine.unload()
            self.win.update_model()
            self._update_tray()
            return
        self.set_state("busy")
        self.win.status(f"Loading {cur[1].label}…")

        def work():
            try:
                self.engine.load(cur[0], self.cfg["num_threads"])
                err = None
            except Exception as e:
                err = e
            ui(self._loaded)(err)
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, err):
        if err:
            notify("Couldn't load the model", str(err))
            self.win.banner(f"Couldn't load the model: {err}")
        else:
            self.win.status(f"Loaded {model_store.active()[1].label}.")
        self.set_state("idle")
        self.win.update_model()

    def check_updates(self, manual=False):
        self.win.status("Checking Hugging Face for a newer model…")

        def work():
            try:
                latest, err = model_store.fetch_latest(), None
            except Exception as e:
                latest, err = None, e
            ui(self._checked)(latest, err, manual)
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, latest, err, manual):
        log.info("update check: latest=%s err=%r", latest and latest.label, err)
        state = load_json(STATE_PATH)
        if err:
            self.win.status(f"Update check failed: {err}")
            if manual:
                notify("Update check failed", str(err))
            return
        state["last_check"] = time.time()
        save_json(STATE_PATH, state)
        self.latest = latest
        first_run = model_store.active() is None
        if not model_store.needs_update(latest):
            self.win.status(f"Up to date ({latest.label}).")
        elif first_run or self.cfg["auto_update"]:
            self.download(latest)
        else:
            self.win.status(f"Update available: {latest.label}")
            if not manual:
                notify("Model update available", f"{latest.label} — open {APP_NAME} to install it.")
        self.win.update_model()
        self._update_tray()

    def _first_check(self):
        if model_store.active() is None:
            self.win.present()
            self.check_updates(manual=True)    # first run: fetch the weights
        else:
            self._periodic_check()
        return False

    def _periodic_check(self):
        hours = self.cfg["update_check_hours"]
        last = load_json(STATE_PATH).get("last_check", 0)
        if hours and not self.downloading and time.time() - last >= hours * 3600:
            self.check_updates()
        return True

    def download(self, manifest):
        if self.downloading:
            return
        self.downloading = threading.Event()
        cancel = self.downloading
        self.win.update_model()

        def progress(done, total, name):
            ui(self.win.progress)(done / total, f"{name} — {done >> 20} / {total >> 20} MB")

        def work():
            try:
                model_store.download(manifest, progress, cancel, keep_old=self.cfg["keep_old_versions"])
                err = None
            except Exception as e:
                err = e
            ui(self._downloaded)(manifest, err)
        threading.Thread(target=work, daemon=True).start()

    def _downloaded(self, manifest, err):
        self.downloading = None
        if isinstance(err, model_store.Cancelled):
            self.win.status("Download cancelled. It resumes where it stopped next time.")
        elif err:
            self.win.status(f"Download failed: {err}")
            notify("Model download failed", str(err))
        else:
            notify("Model ready", manifest.label)
            self.win.status(f"Installed {manifest.label}.")
            self.load_model()
        self.win.progress(None)
        self.win.update_model()
        self._update_tray()

    def update_available(self) -> bool:
        return bool(self.latest and model_store.active() and model_store.needs_update(self.latest))

    # -- tray --------------------------------------------------------------------
    def _build_tray(self):
        self.ind = AyatanaAppIndicator3.Indicator.new(
            "codeswitch-dictation", ICONS["idle"],
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self.ind.set_title(APP_NAME)
        menu = Gtk.Menu()

        def item(label, cb):
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", lambda *_: cb())
            menu.append(mi)
            return mi
        self.mi_toggle = item("Start dictation", self.toggle)
        item("Show window", lambda: self.win.present())
        menu.append(Gtk.SeparatorMenuItem())
        self.mi_update = item("Install update", lambda: self.latest and self.download(self.latest))
        item("Check for model update", lambda: self.check_updates(manual=True))
        menu.append(Gtk.SeparatorMenuItem())
        item("Quit", self.quit)
        menu.show_all()
        self.ind.set_menu(menu)
        self.ind.set_secondary_activate_target(self.mi_toggle)   # middle click toggles
        self._update_tray()

    def _update_tray(self):
        icon = ICONS["nomodel"] if model_store.active() is None else ICONS[self.state]
        self.ind.set_icon_full(icon, self.state)
        self.mi_toggle.set_label("Stop dictation" if self.state == "recording" else "Start dictation")
        self.mi_toggle.set_sensitive(self.state != "busy")
        self.mi_update.set_visible(self.update_available() and not self.downloading)
        if self.latest:
            self.mi_update.set_label(f"Install update ({self.latest.version})")


class MainWindow(Gtk.Window):
    def __init__(self, app: App):
        super().__init__(title=APP_NAME, application=app)
        self.app, self.cfg = app, app.cfg
        self.set_default_size(560, 640)
        self.set_icon_name(ICONS["idle"])
        self.connect("delete-event", lambda *_: self.hide() or True)   # close = to tray

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        self.add(outer)

        self.bar = Gtk.InfoBar(message_type=Gtk.MessageType.WARNING, show_close_button=True)
        self.bar_label = Gtk.Label(wrap=True, xalign=0)
        self.bar.get_content_area().add(self.bar_label)
        self.bar.connect("response", lambda b, _r: b.hide())
        self.bar.set_no_show_all(True)
        outer.pack_start(self.bar, False, False, 0)

        # dictation
        row = Gtk.Box(spacing=10)
        self.btn = Gtk.Button(label="Start dictation")
        self.btn.get_style_context().add_class("suggested-action")
        self.btn.connect("clicked", lambda *_: app.toggle())
        self.state_label = Gtk.Label(xalign=0)
        row.pack_start(self.btn, False, False, 0)
        row.pack_start(self.state_label, True, True, 0)
        outer.pack_start(row, False, False, 0)

        self.history = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        sc = Gtk.ScrolledWindow(min_content_height=140, vexpand=True)
        sc.add(self.history)
        outer.pack_start(self._frame("Recent transcripts", sc), True, True, 0)

        outer.pack_start(self._frame("Model", self._model_box()), False, False, 0)
        outer.pack_start(self._frame("Settings", self._settings_grid()), False, False, 0)

        self.status_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.status_label.get_style_context().add_class("dim-label")
        outer.pack_start(self.status_label, False, False, 0)

        outer.show_all()
        self.update_state()
        self.update_model()
        self.show_history()

    @staticmethod
    def _frame(title, child):
        f = Gtk.Frame(label=title)
        child.set_margin_start(10)
        child.set_margin_end(10)
        child.set_margin_top(6)
        child.set_margin_bottom(10)
        f.add(child)
        return f

    # -- model section -------------------------------------------------------------
    def _model_box(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.model_label = Gtk.Label(xalign=0, wrap=True)
        box.pack_start(self.model_label, False, False, 0)

        row = Gtk.Box(spacing=6)
        self.btn_check = Gtk.Button(label="Check for update")
        self.btn_check.connect("clicked", lambda *_: self.app.check_updates(manual=True))
        self.btn_update = Gtk.Button(label="Download")
        self.btn_update.get_style_context().add_class("suggested-action")
        self.btn_update.connect("clicked", self._on_download)
        self.btn_cancel = Gtk.Button(label="Cancel")
        self.btn_cancel.connect("clicked", lambda *_: self.app.downloading and self.app.downloading.set())
        for b in (self.btn_check, self.btn_update, self.btn_cancel):
            row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)

        self.pbar = Gtk.ProgressBar(show_text=True)
        self.pbar.set_no_show_all(True)
        box.pack_start(self.pbar, False, False, 0)

        row = Gtk.Box(spacing=6)
        row.pack_start(Gtk.Label(label="Installed:"), False, False, 0)
        self.versions = Gtk.ComboBoxText()
        row.pack_start(self.versions, True, True, 0)
        b_use = Gtk.Button(label="Use")
        b_use.connect("clicked", self._on_use_version)
        b_del = Gtk.Button(label="Delete")
        b_del.connect("clicked", self._on_delete_version)
        row.pack_start(b_use, False, False, 0)
        row.pack_start(b_del, False, False, 0)
        box.pack_start(row, False, False, 0)
        return box

    def _on_download(self, *_):
        if self.app.latest:
            self.app.download(self.app.latest)
        else:
            self.app.check_updates(manual=True)

    def _on_use_version(self, *_):
        name = self.versions.get_active_id()
        if name:
            model_store.set_active(name)
            self.app.load_model()

    def _on_delete_version(self, *_):
        name = self.versions.get_active_id()
        cur = model_store.active()
        if not name:
            return
        if cur and cur[0].name == name:
            self.banner("That's the version in use. Switch to another one first.")
            return
        model_store.remove(name)
        self.update_model()

    def update_model(self):
        cur = model_store.active()
        app = self.app
        if cur is None:
            text = "Not downloaded yet (~660 MB). It downloads automatically on first run."
        else:
            text = f"In use: <b>{GLib.markup_escape_text(cur[1].label)}</b>"
            if app.engine.loaded_dir != cur[0]:
                text += " (loading…)"
        if app.update_available():
            text += f"\nAvailable: <b>{GLib.markup_escape_text(app.latest.label)}</b>"
        last = load_json(STATE_PATH).get("last_check")
        if last:
            text += f"\n<small>Last checked {time.strftime('%Y-%m-%d %H:%M', time.localtime(last))}</small>"
        self.model_label.set_markup(text)

        busy = bool(app.downloading)
        self.btn_update.set_visible(not busy and (cur is None or app.update_available()))
        self.btn_update.set_label("Download model" if cur is None else
                                  f"Update to {app.latest.version}" if app.latest else "Update")
        self.btn_cancel.set_visible(busy)
        self.btn_check.set_sensitive(not busy)

        self.versions.remove_all()
        for d, m in model_store.installed():
            mark = "  ✓ in use" if cur and d == cur[0] else ""
            self.versions.append(d.name, f"{m.label}{mark}")
        if cur:
            self.versions.set_active_id(cur[0].name)

    def progress(self, frac, text=""):
        if frac is None:
            self.pbar.hide()
            return
        self.pbar.show()
        self.pbar.set_fraction(frac)
        self.pbar.set_text(text)

    # -- settings section ----------------------------------------------------------
    def _settings_grid(self):
        g = Gtk.Grid(column_spacing=10, row_spacing=6)
        r = 0

        def add(label, widget, tip=None):
            nonlocal r
            lbl = Gtk.Label(label=label, xalign=0)
            if tip:
                lbl.set_tooltip_text(tip)
                widget.set_tooltip_text(tip)
            g.attach(lbl, 0, r, 1, 1)
            g.attach(widget, 1, r, 1, 1)
            r += 1

        hk = Gtk.Box(spacing=6)
        self.hk_label = Gtk.Label(label=self.cfg["hotkey"], xalign=0, hexpand=True)
        self.hk_btn = Gtk.Button(label="Change…")
        self.hk_btn.connect("clicked", self._capture_hotkey)
        hk.pack_start(self.hk_label, True, True, 0)
        hk.pack_start(self.hk_btn, False, False, 0)
        add("Hotkey", hk, "Any key on any keyboard or pedal. Read from /dev/input, so it "
            "works on every desktop; pick one nothing else uses (F13–F24 are ideal).")

        add("Mode", self._combo("mode", [("hybrid", "Tap to toggle, hold for push-to-talk"),
                                         ("toggle", "Tap to start, tap to stop"),
                                         ("hold", "Push-to-talk (hold)")]))
        add("Output", self._combo("insert", [("paste", "Paste at the cursor"),
                                             ("clipboard", "Clipboard only")]))
        chord = Gtk.Entry(text=self.cfg["paste_chord"], width_chars=14)
        chord.connect("changed", self._on_chord)
        add("Paste shortcut", chord, "ctrl+v for most apps; ctrl+shift+v for terminals.")

        mics = Gtk.ComboBoxText()
        mics.append("", "System default")
        for name in audio.input_devices():
            mics.append(name, name)
        mics.set_active_id(self.cfg["audio_device"]) or mics.set_active_id("")
        mics.connect("changed", lambda c: self.cfg.set("audio_device", c.get_active_id() or ""))
        add("Microphone", mics)

        spin = Gtk.SpinButton.new_with_range(0, 24 * 7, 1)
        spin.set_value(self.cfg["update_check_hours"])
        spin.connect("value-changed", lambda s: self.cfg.set("update_check_hours", int(s.get_value())))
        add("Check for updates every (h)", spin, "0 turns automatic checks off.")

        for key, label, tip in (
            ("auto_update", "Install updates automatically", None),
            ("keep_old_versions", "Keep previous model versions",
             "Off: the old weights are deleted once the new ones verify. "
             "On: they stay, and you can switch back under Model."),
            ("beeps", "Start/stop beeps", None),
            ("trailing_space", "Add a space after each transcript", None),
        ):
            cb = Gtk.CheckButton(label=label, active=self.cfg[key])
            cb.connect("toggled", lambda c, k=key: self.cfg.set(k, c.get_active()))
            if tip:
                cb.set_tooltip_text(tip)
            g.attach(cb, 0, r, 2, 1)
            r += 1

        auto = Gtk.CheckButton(label="Start at login (in the tray)",
                               active=GLib.file_test(AUTOSTART, GLib.FileTest.EXISTS))
        auto.connect("toggled", lambda c: set_autostart(c.get_active()))
        g.attach(auto, 0, r, 2, 1)
        r += 1

        cfg_lbl = Gtk.Label(xalign=0, selectable=True)
        cfg_lbl.set_markup(f"<small>Config: {GLib.markup_escape_text(str(CONFIG_PATH))}"
                           f" · v{__version__}</small>")
        cfg_lbl.get_style_context().add_class("dim-label")
        g.attach(cfg_lbl, 0, r, 2, 1)
        return g

    def _combo(self, key, options):
        c = Gtk.ComboBoxText()
        for val, label in options:
            c.append(val, label)
        c.set_active_id(self.cfg[key])
        c.connect("changed", lambda w: self.cfg.set(key, w.get_active_id()))
        return c

    def _on_chord(self, entry):
        try:
            parse_chord(entry.get_text())
            entry.get_style_context().remove_class("error")
            self.cfg.set("paste_chord", entry.get_text().strip().lower())
        except ValueError:
            entry.get_style_context().add_class("error")

    def _capture_hotkey(self, *_):
        self.hk_btn.set_sensitive(False)
        self.hk_label.set_text("Press the key you want…")

        def got(name):
            if key_code(name) is not None:
                self.cfg.set("hotkey", name)
            self.hk_label.set_text(self.cfg["hotkey"])
            self.hk_btn.set_sensitive(True)
        self.app.hotkeys.capture_next_key(ui(got))

    # -- state ---------------------------------------------------------------------
    def update_state(self):
        st = self.app.state
        self.btn.set_label("Stop dictation" if st == "recording" else "Start dictation")
        self.btn.set_sensitive(st != "busy")
        mode = {"hold": "hold", "toggle": "tap", "hybrid": "tap or hold"}[self.cfg["mode"]]
        self.state_label.set_text({"idle": f"Ready. {mode.capitalize()} {self.cfg['hotkey']}.",
                                   "recording": "Listening…",
                                   "busy": "Working…"}[st])
        self.hk_label.set_text(self.cfg["hotkey"]) if hasattr(self, "hk_label") else None
        self.update_model()

    def show_history(self):
        for child in self.history.get_children():
            self.history.remove(child)
        for text in self.app.history:
            row = Gtk.Box(spacing=6, margin=4)
            lbl = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True)
            btn = Gtk.Button.new_from_icon_name("edit-copy", Gtk.IconSize.BUTTON)
            btn.set_tooltip_text("Copy")
            btn.connect("clicked", lambda _b, t=text: copy_to_clipboard(t))
            row.pack_start(lbl, True, True, 0)
            row.pack_start(btn, False, False, 0)
            self.history.add(row)
        self.history.show_all()

    def status(self, text):
        self.status_label.set_text(text)

    def banner(self, text):
        self.bar_label.set_text(text)
        self.bar.show()
        self.bar_label.show()


def set_autostart(on: bool):
    path = Gio.File.new_for_path(AUTOSTART)
    if not on:
        if path.query_exists():
            path.delete()
        return
    exe = shutil.which("codeswitch-dictation") or f"{sys.executable} -m codeswitch_dictation"
    GLib.mkdir_with_parents(GLib.path_get_dirname(AUTOSTART), 0o755)
    GLib.file_set_contents(AUTOSTART, (
        "[Desktop Entry]\nType=Application\n"
        f"Name={APP_NAME}\nExec={exe} --hidden\nIcon={ICONS['idle']}\n"
        "X-GNOME-Autostart-enabled=true\n").encode())


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sys.exit(App().run(sys.argv))

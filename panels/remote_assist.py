import logging
import socket
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel
from ks_includes.frpc_session import AssistSession, SessionError

POLL_SECONDS = 15

def _probe_internet():
    for host in ("223.5.5.5", "119.29.29.29", "1.1.1.1"):
        try:
            s = socket.create_connection((host, 53), timeout=2)
            s.close()
            return True
        except OSError:
            continue
    return False

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Remote Assist")
        super().__init__(screen, title)

        self.active = False
        self.busy = False
        self.assist_code = None
        self.error = None
        self._timer = None
        self._loading = False
        self.net_ok = None
        self._net_checking = False
        self._session = AssistSession()

        screen = Gdk.Screen.get_default()
        screen_h = screen.get_height() if screen is not None else 600
        self.code_font = max(28, min(56, int(screen_h * 0.075)))

        scrolled = self._gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self._build_root())
        self.content.add(scrolled)
        self._check_net()
        if self.net_ok is False:
            self._apply_net_ui()
        self._refresh_status()

    # ------------------------------------------------------------------ UI

    def _build_root(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_hexpand(True)
        root.set_vexpand(True)
        root.set_margin_top(8)
        root.set_margin_bottom(8)
        root.set_margin_start(15)
        root.set_margin_end(15)

        self.code_card = self._build_code_card()
        self.notes_card = self._build_notes_card()
        self.offline_card = self._build_offline_card()

        root.pack_start(self.code_card, True, True, 0)
        root.pack_start(self.notes_card, True, True, 0)
        root.pack_start(self.offline_card, True, True, 0)
        return root

    def _build_code_card(self):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("elevated")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_hexpand(True)
        vbox.set_vexpand(True)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_row.set_halign(Gtk.Align.CENTER)
        self.status_img = self._gtk.Image(
            "info", self._gtk.content_width * .04, self._gtk.content_height * .04)
        self.status_img.set_valign(Gtk.Align.CENTER)
        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.START)
        status_row.pack_start(self.status_img, False, False, 0)
        status_row.pack_start(self.status_label, False, False, 0)
        vbox.pack_start(status_row, False, False, 0)

        caption = Gtk.Label()
        caption.set_markup(
            '<span size="small" weight="bold">' + _("Assist code") + '</span>')
        vbox.pack_start(caption, False, False, 0)

        self.code_label = Gtk.Label()
        self.code_label.set_selectable(True)
        self.code_label.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(self.code_label, False, False, 0)

        self.error_label = Gtk.Label()
        self.error_label.set_halign(Gtk.Align.CENTER)
        self.error_label.set_line_wrap(True)
        self.error_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.error_label.set_max_width_chars(40)
        self.error_label.set_no_show_all(True)
        vbox.pack_start(self.error_label, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_top(4)
        long_w = min(280, int(self._gtk.content_width * 0.45))
        self.start_btn = self._gtk.Button(
            "resume", " " + _("Start Assist") + " ", "color1",
            self.bts, Gtk.PositionType.LEFT, 1)
        self.start_btn.set_size_request(long_w, 84)
        self.start_btn.connect("clicked", self.on_start)
        self.stop_btn = self._gtk.Button(
            "cancel", " " + _("Stop Assist") + " ", "color2",
            self.bts, Gtk.PositionType.LEFT, 1)
        self.stop_btn.set_size_request(long_w, 84)
        self.stop_btn.set_no_show_all(True)
        self.stop_btn.connect("clicked", self.on_stop)
        btn_box.pack_start(self.start_btn, False, False, 0)
        btn_box.pack_start(self.stop_btn, False, False, 0)
        vbox.pack_start(btn_box, False, False, 4)

        frame.add(vbox)
        return frame

    def _build_notes_card(self):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("elevated")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox.set_hexpand(True)
        vbox.set_vexpand(True)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon = self._gtk.Image(
            "light_hint", self._gtk.content_width * .03, self._gtk.content_height * .03)
        icon.set_valign(Gtk.Align.START)
        title = Gtk.Label(label=_("Customer Notes"))
        title.set_name("title-bold")
        title.set_halign(Gtk.Align.START)
        title_row.pack_start(icon, False, False, 0)
        title_row.pack_start(title, False, False, 0)
        vbox.pack_start(title_row, False, False, 10)

        notes = [
            _("Share the assist code only with our support engineer."),
            _("The assist code is valid only for this session; "
              "a new code will be generated for the next remote assist."),
            _("Support connects through an encrypted temporary tunnel; "
              "there is no standing connection otherwise."),
            _("Tap Stop Assist to disconnect immediately at any time."),
        ]
        BULLET_W = 24
        grid = Gtk.Grid()
        grid.set_column_spacing(8)
        grid.set_row_spacing(5)
        for i, txt in enumerate(notes):
            dot = Gtk.Label(label="○")
            dot.set_size_request(BULLET_W, -1)
            dot.set_halign(Gtk.Align.START)
            dot.set_valign(Gtk.Align.START)
            lbl = Gtk.Label(label=txt)
            lbl.set_name("usage-item")
            lbl.set_line_wrap(True)
            lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_hexpand(True)
            lbl.set_valign(Gtk.Align.START)
            lbl.set_xalign(0.0)
            lbl.override_font(Pango.FontDescription("small"))
            grid.attach(dot, 0, i, 1, 1)
            grid.attach(lbl, 1, i, 1, 1)
        vbox.pack_start(grid, False, False, 0)

        frame.add(vbox)
        return frame

    def _build_offline_card(self):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("elevated")
        frame.set_no_show_all(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_hexpand(True)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)

        icon = self._gtk.Image(
            "warning", self._gtk.content_width * .08, self._gtk.content_height * .08)
        icon.set_valign(Gtk.Align.CENTER)
        vbox.pack_start(icon, False, False, 0)

        main = Gtk.Label()
        main.set_markup(
            '<span size="x-large" weight="bold">'
            + _("Remote assist requires an internet connection")
            + '</span>')
        main.set_line_wrap(True)
        main.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        main.set_justify(Gtk.Justification.CENTER)
        main.set_max_width_chars(34)
        vbox.pack_start(main, False, False, 0)

        frame.add(vbox)
        vbox.show_all()
        return frame

    # ------------------------------------------------------------- actions

    def on_start(self, widget):
        if self.net_ok is False:
            self._apply_net_ui()
        if self.busy or self.net_ok is False:
            return
        self.busy = True
        self.error = None
        self._set_busy_ui(_("Starting assist..."))
        self._run_session("start", self._start_done)

    def _start_done(self, result):
        self.busy = False
        if isinstance(result, SessionError):
            self.error = str(result)
            logging.error(f"Remote assist start failed: {result}")
        else:
            self.active = True
            self.assist_code = result["assist_code"]
            self.error = None
        self._update_ui()
        if self.active:
            self._refresh_status()
        return False

    def on_stop(self, widget):
        if self.net_ok is False:
            self._apply_net_ui()
        if self.busy or self.net_ok is False:
            return
        self.busy = True
        self._set_busy_ui(_("Stopping assist..."))
        self._run_session("stop", self._stop_done)

    def _stop_done(self, result):
        self.busy = False
        if isinstance(result, SessionError):
            logging.error(f"Remote assist stop failed: {result}")
            self.error = str(result)
        else:
            self.active = False
            self.assist_code = None
            self.error = None
        self._update_ui()
        self._refresh_status()
        return False

    # --------------------------------------------------------------- state

    def activate(self):
        self._check_net()
        self._refresh_status()
        if self._timer is None:
            self._timer = GLib.timeout_add_seconds(POLL_SECONDS, self._on_timer)

    def deactivate(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _on_timer(self):
        if self.busy or self._loading:
            return True
        self._check_net()
        if self.net_ok:
            self._refresh_status()
        return True

    def _check_net(self):
        if self._net_checking:
            return
        self._net_checking = True

        def worker():
            ok = _probe_internet()
            GLib.idle_add(self._net_done, ok)

        threading.Thread(target=worker, daemon=True).start()

    def _net_done(self, ok):
        self._net_checking = False
        if self.net_ok == ok and ok is not False:
            return False
        self.net_ok = ok
        self._apply_net_ui()
        if ok and not self.busy:
            self._refresh_status()
        return False

    def _apply_net_ui(self):
        if self.net_ok is False:
            self.code_card.hide()
            self.notes_card.hide()
            self.offline_card.show()
        else:
            self.offline_card.hide()
            self.code_card.show()
            self.notes_card.show()

    def _refresh_status(self):
        if self._loading or self.busy:
            return
        self._loading = True
        self._run_session("status", self._status_done)

    def _status_done(self, result):
        self._loading = False
        if self.busy:
            return False
        if isinstance(result, SessionError):
            logging.error(f"Remote assist status failed: {result}")
            self.active = False
            self.assist_code = None
        else:
            self.active = result["running"]
            self.assist_code = result["assist_code"] if self.active else None
            if self.active:
                self.error = None
        self._update_ui()
        return False

    def _update_ui(self):
        if self.busy or self.net_ok is False:
            return
        self._gtk.Button_busy(self.start_btn, False)
        self._gtk.Button_busy(self.stop_btn, False)
        if self.active:
            self._set_status_icon("complete")
            self.status_label.set_text(_("Remote assistance is active"))
            self.code_label.set_markup(
                f'<span font="Bold {self.code_font}">'
                f'{self.assist_code or "------"}</span>')
            self.error_label.hide()
            self.start_btn.hide()
            self.stop_btn.show()
        else:
            if self.error:
                self._set_status_icon("warning")
                self.status_label.set_text(_("Failed to start assist"))
                self.error_label.set_text(self.error)
                self.error_label.show()
            else:
                self._set_status_icon("info")
                self.status_label.set_text(_("Remote assistance is not active"))
                self.error_label.hide()
            self.code_label.set_markup(
                f'<span font="Bold {self.code_font}" foreground="#909090">'
                '------</span>')
            self.start_btn.show()
            self.stop_btn.hide()

    def _set_busy_ui(self, text):
        self._gtk.Button_busy(self.start_btn, True)
        self._gtk.Button_busy(self.stop_btn, True)
        self._set_status_icon("hourglass")
        self.status_label.set_text(text)

    def _set_status_icon(self, name):
        parent = self.status_img.get_parent()
        if parent is None:
            return
        parent.remove(self.status_img)
        self.status_img = self._gtk.Image(
            name, self._gtk.content_width * .04, self._gtk.content_height * .04)
        self.status_img.set_valign(Gtk.Align.CENTER)
        parent.pack_start(self.status_img, False, False, 0)
        parent.reorder_child(self.status_img, 0)
        parent.show_all()

    # -------------------------------------------------------------- helpers

    def _run_session(self, action, callback):
        # Run session calls in a worker thread (start/stop include process
        # operations of a few seconds, must not block the GTK main loop),
        # then deliver the result or SessionError back on the main thread.
        session = self._session

        def worker():
            try:
                if action == "start":
                    result = session.start()
                elif action == "stop":
                    result = session.stop()
                else:
                    result = session.status()
            except SessionError as e:
                result = e
            except Exception as e:
                logging.exception(f"Remote assist session {action} crashed")
                result = SessionError(f"{action}_failed: {e}")
            GLib.idle_add(callback, result)

        threading.Thread(target=worker, daemon=True).start()

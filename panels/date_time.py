import datetime
import logging
import os
import subprocess
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from ks_includes import functions

AUTO_TIME_SERVICE = "chrony"
AUTO_TIMEZONE_SERVICE = "autotimezone.service"

COMMON_TIMEZONES = [
    "UTC",
    "Pacific/Honolulu",
    "America/Anchorage",
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "America/Toronto",
    "America/Halifax",
    "America/Sao_Paulo",
    "Atlantic/Azores",
    "Europe/London",
    "Europe/Paris",
    "Europe/Athens",
    "Africa/Cairo",
    "Europe/Moscow",
    "Asia/Tehran",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Dhaka",
    "Asia/Bangkok",
    "Asia/Singapore",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Australia/Sydney",
    "Pacific/Auckland",
    "Pacific/Fiji",
]


def exec_command(cmd):
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        logging.exception(f"Failed to execute {cmd}")
        return 1, "", str(e)


def run_privileged(cmd):
    rc, out, err = exec_command(cmd)
    if rc == 0:
        return True, out, err
    rc_sudo, out_sudo, err_sudo = exec_command(["sudo", "-n"] + cmd)
    if rc_sudo == 0:
        logging.info(f"Command succeeded with sudo: {' '.join(cmd)}")
        return True, out_sudo, err_sudo
    logging.warning(
        f"Command failed: {' '.join(cmd)} ({rc}: {err}) "
        f"and with sudo ({rc_sudo}: {err_sudo})"
    )
    return False, out, err


def auto_time_enabled():
    _, out, _ = exec_command(["systemctl", "is-active", AUTO_TIME_SERVICE])
    return out == "active"


def set_auto_time(enabled):
    action = "enable" if enabled else "disable"
    ok, _, _ = run_privileged(["systemctl", action, "--now", AUTO_TIME_SERVICE])
    return ok


def auto_timezone_enabled():
    _, out, _ = exec_command(["systemctl", "is-enabled", AUTO_TIMEZONE_SERVICE])
    return out == "enabled"


def set_auto_timezone(enabled):
    action = "enable" if enabled else "disable"
    ok, _, _ = run_privileged(["systemctl", action, "--now", AUTO_TIMEZONE_SERVICE])
    return ok


def set_datetime(value):
    if auto_time_enabled():
        set_auto_time(False)

    stamp = value.strftime("%Y-%m-%d %H:%M:%S")
    ok, _, err = run_privileged(["timedatectl", "set-time", stamp])
    if not ok:
        ok, _, err = run_privileged(["date", "-s", stamp])
    if not ok:
        logging.warning(f"Failed to set date to {stamp}: {err}")
        return False
    logging.info(f"System date set to {stamp}")
    return True


def current_timezone():
    rc, out, err = exec_command(["timedatectl", "show", "-p", "Timezone", "--value"])
    if out:
        return out
    if rc != 0:
        logging.warning(f"timedatectl failed ({rc}): {err}")
    link = os.path.realpath("/etc/localtime")
    pos = link.find("zoneinfo/")
    if pos != -1:
        return link[pos + len("zoneinfo/"):]
    logging.warning(f"Unable to detect the current time zone (localtime: {link})")
    return ""


def set_timezone(zone):
    ok, _, err = run_privileged(["timedatectl", "set-timezone", zone])
    if ok:
        logging.info(f"Time zone set to {zone}")
        return True
    zone_file = f"/usr/share/zoneinfo/{zone}"
    if os.path.isfile(zone_file):
        try:
            tmp_link = "/etc/localtime.tmp"
            if os.path.lexists(tmp_link):
                os.remove(tmp_link)
            os.symlink(zone_file, tmp_link)
            os.replace(tmp_link, "/etc/localtime")
            logging.info(f"Time zone set to {zone} via /etc/localtime")
            return True
        except OSError:
            logging.exception(f"Failed to link /etc/localtime to {zone_file}")
    logging.warning(f"Failed to set time zone to {zone}: {err}")
    return False


def zone_display_name(zone):
    pos = zone.find("/")
    if pos == -1:
        return zone
    return zone[pos + 1:].replace("_", " ")


def zone_utc_offset(zone):
    try:
        from zoneinfo import ZoneInfo
        total = int(datetime.datetime.now(ZoneInfo(zone)).utcoffset().total_seconds())
    except Exception:
        return ""
    sign = "+" if total >= 0 else "-"
    hours, minutes = divmod(abs(total) // 60, 60)
    return f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else "")


def zone_text(zone):
    offset = zone_utc_offset(zone)
    name = zone_display_name(zone)
    return f"{name}  {offset}" if offset else name


def days_in_month(year, month):
    if month == 12:
        return 31
    return (datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)).day


class DateTimePage(Gtk.ScrolledWindow):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_overlay_scrolling(False)
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._updating = False
        self.zone_dialog = None
        self.picker = []
        self.picker_labels = []
        self.current_zone = ""
        self.auto_time = False
        self.auto_timezone = False
        self._poll_id = None
        self._zone_signature = None

        self.grid = Gtk.Grid()
        self.grid.set_vexpand(False)
        self.add(self.grid)
        self._row_count = 0

        self._build()
        self.refresh()
        self._poll_id = GLib.timeout_add_seconds(1, self._poll_zone)

    def _build(self):
        self.auto_time_switch = Gtk.Switch()
        self.auto_time_switch.set_valign(Gtk.Align.CENTER)
        self.auto_time_switch.set_vexpand(False)
        self.auto_time_switch.connect("notify::active", self._on_auto_time_toggled)
        self._add_row(_("Automatic Date & Time"), self.auto_time_switch)

        self.date_button, self.time_label = self._value_button()
        self.date_button.connect("clicked", self.open_datetime_dialog)
        self._add_row(_("Set Date & Time"), self.date_button)

        self.auto_timezone_switch = Gtk.Switch()
        self.auto_timezone_switch.set_valign(Gtk.Align.CENTER)
        self.auto_timezone_switch.set_vexpand(False)
        self.auto_timezone_switch.connect("notify::active", self._on_auto_timezone_toggled)
        self._add_row(_("Automatic Time Zone"), self.auto_timezone_switch)

        self.zone_button, self.zone_label = self._value_button()
        self.zone_button.connect("clicked", self.open_timezone_dialog)
        self._add_row(_("Time Zone"), self.zone_button)

        self.hour24_switch = Gtk.Switch()
        self.hour24_switch.set_valign(Gtk.Align.CENTER)
        self.hour24_switch.set_vexpand(False)
        self.hour24_switch.connect("notify::active", self._on_hour24_toggled)
        self._add_row(_("24 Hour Time"), self.hour24_switch, tooltip=_("Disable for 12hs with am / pm"))

    def _add_row(self, name, control, tooltip=None):
        row = Gtk.Box(spacing=5, valign=Gtk.Align.CENTER, hexpand=True, vexpand=False)
        row.get_style_context().add_class("frame-item")

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, hexpand=True,
                         valign=Gtk.Align.CENTER)
        label = Gtk.Label(
            hexpand=True, halign=Gtk.Align.START, valign=Gtk.Align.CENTER,
            wrap=True, wrap_mode=Pango.WrapMode.CHAR
        )
        label.set_markup(f"<big><b>{GLib.markup_escape_text(name)}</b></big>")
        labels.add(label)
        if tooltip:
            tip = Gtk.Label(label=tooltip, xalign=0, halign=Gtk.Align.START, wrap=True,
                            wrap_mode=Pango.WrapMode.CHAR)
            tip.set_opacity(0.7)
            labels.add(tip)
        row.add(labels)
        row.add(control)

        self.grid.attach(row, 0, self._row_count, 1, 1)
        self._row_count += 1

    def _value_button(self):
        btn_box = Gtk.Box(spacing=5)
        value_label = Gtk.Label()
        value_label.set_ellipsize(Pango.EllipsizeMode.END)
        arrow = Gtk.Image.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON)
        btn_box.pack_start(value_label, True, True, 0)
        btn_box.pack_end(arrow, False, False, 0)

        button = Gtk.Button()
        button.add(btn_box)
        button.set_vexpand(False)
        button.set_valign(Gtk.Align.CENTER)
        button.get_style_context().add_class("dropdown")
        return button, value_label

    def refresh(self):
        self._updating = True
        self.current_zone = current_timezone()
        self.auto_time = auto_time_enabled()
        self.auto_timezone = auto_timezone_enabled()
        self.auto_time_switch.set_active(self.auto_time)
        self.auto_timezone_switch.set_active(self.auto_timezone)
        self.hour24_switch.set_active(
            self.panel._config.get_main_config().getboolean("24htime", True)
        )
        self._updating = False
        self._update_time_label()
        self._update_zone_label()
        self._update_sensitivity()
        self.grid.show_all()
        self._zone_signature = functions.timezone_signature()
        logging.info(
            f"Date & Time refreshed: zone={self.current_zone!r} auto_time={self.auto_time} "
            f"auto_timezone={self.auto_timezone}"
        )

    def _format_now(self):
        use_24h = self.panel._config.get_main_config().getboolean("24htime", True)
        fmt = "%Y-%m-%d %H:%M:%S" if use_24h else "%Y-%m-%d %I:%M:%S %p"
        return datetime.datetime.now().strftime(fmt)

    def _update_time_label(self):
        self.time_label.set_text(self._format_now())

    def _update_zone_label(self):
        self.zone_label.set_text(zone_text(self.current_zone) if self.current_zone else "-")

    def _update_sensitivity(self):
        self.date_button.set_sensitive(not self.auto_time)
        self.date_button.set_opacity(0.5 if self.auto_time else 1.0)
        self.zone_button.set_sensitive(not self.auto_timezone)
        self.zone_button.set_opacity(0.5 if self.auto_timezone else 1.0)

    def _on_auto_time_toggled(self, switch, _param):
        if self._updating:
            return
        enabled = switch.get_active()
        if not set_auto_time(enabled):
            self._updating = True
            switch.set_active(not enabled)
            self._updating = False
            self.panel._screen.show_popup_message(_("Failed to change automatic time"))
            return
        self.auto_time = enabled
        self._update_sensitivity()
        self._update_time_label()

    def _on_auto_timezone_toggled(self, switch, _param):
        if self._updating:
            return
        enabled = switch.get_active()
        if not set_auto_timezone(enabled):
            self._updating = True
            switch.set_active(not enabled)
            self._updating = False
            self.panel._screen.show_popup_message(_("Failed to change automatic time zone"))
            return
        self.auto_timezone = enabled
        self._update_sensitivity()

    def _on_hour24_toggled(self, switch, _param):
        if self._updating:
            return
        self.panel._config.set("main", "24htime", "True" if switch.get_active() else "False")
        self.panel._config.save_user_config_options()
        self._update_time_label()

    def _zone_button(self, zone):
        button = Gtk.Button()
        button.set_name(zone)
        button.get_style_context().add_class("zone-card")
        button.connect("clicked", self._on_zone_selected)

        row = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        row.set_margin_start(10)
        row.set_margin_end(10)

        name = Gtk.Label(xalign=0, hexpand=True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        if zone == self.current_zone:
            name.set_markup(f"<b>{GLib.markup_escape_text(zone_display_name(zone))}</b>")
        else:
            name.set_text(zone_display_name(zone))
        row.pack_start(name, True, True, 0)

        offset = Gtk.Label(label=zone_utc_offset(zone), xalign=1)
        offset.set_opacity(0.7)
        row.pack_start(offset, False, False, 0)

        if zone == self.current_zone:
            check = Gtk.Label()
            check.set_markup("<span foreground='#06A54F' size='large'><b>✓</b></span>")
            check.set_valign(Gtk.Align.CENTER)
            row.pack_end(check, False, False, 0)
            button.get_style_context().add_class("button_active")
        button.add(row)
        return button

    def _zone_columns(self):
        width = self.panel._screen.width
        if width >= 900:
            return 4
        if width >= 650:
            return 3
        if width >= 450:
            return 2
        return 1

    def _build_zone_grid(self, grid):
        zones = list(COMMON_TIMEZONES)
        if self.current_zone and self.current_zone not in zones:
            zones.insert(0, self.current_zone)

        columns = self._zone_columns()
        current_button = None
        for index, zone in enumerate(zones):
            button = self._zone_button(zone)
            if zone == self.current_zone:
                current_button = button
            grid.attach(button, index % columns, index // columns, 1, 1)
        return current_button

    def _scroll_to_current(self, scrolled, button):
        if not scrolled.get_mapped():
            return False
        adjustment = scrolled.get_vadjustment()
        position = button.get_allocation().y - 10
        limit = adjustment.get_upper() - adjustment.get_page_size()
        adjustment.set_value(max(adjustment.get_lower(), min(position, limit)))
        return False

    def open_timezone_dialog(self, _widget):
        logging.info(f"Opening time zone picker (current: {self.current_zone!r})")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(15)
        content.set_margin_bottom(15)
        content.set_margin_start(15)
        content.set_margin_end(15)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(xalign=0)
        title.set_markup(
            f"<span size='x-large'><b>{GLib.markup_escape_text(_('Time Zone'))}</b></span>"
        )
        header.pack_start(title, False, False, 0)
        subtitle = Gtk.Label(
            label=f"{_('Current')}: {zone_text(self.current_zone) if self.current_zone else '-'}",
            xalign=0
        )
        subtitle.set_opacity(0.7)
        header.pack_start(subtitle, False, False, 0)
        content.add(header)

        grid = Gtk.Grid(row_spacing=6, column_spacing=6, vexpand=False)
        grid.set_column_homogeneous(True)
        current_button = self._build_zone_grid(grid)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_overlay_scrolling(False)
        scrolled.set_vexpand(True)
        scrolled.add(grid)
        content.add(scrolled)

        buttons = [
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-default"},
        ]
        self.zone_dialog = self.panel._gtk.Dialog(_("Time Zone"), buttons, content, self._timezone_response)
        if current_button is not None:
            GLib.timeout_add(150, self._scroll_to_current, scrolled, current_button)

    def _timezone_response(self, dialog, _response_id):
        self.panel._gtk.remove_dialog(dialog)
        self.zone_dialog = None

    def _on_zone_selected(self, button):
        zone = button.get_name()
        logging.info(f"Time zone selected: {zone} (previous: {self.current_zone!r})")
        if self.zone_dialog is not None:
            self.panel._gtk.remove_dialog(self.zone_dialog)
            self.zone_dialog = None
        if zone == self.current_zone:
            return
        if not set_timezone(zone):
            self.panel._screen.show_popup_message(_("Failed to set time zone"))
            return
        self.current_zone = zone
        time.tzset()
        self._update_zone_label()
        self._update_time_label()
        self._zone_signature = functions.timezone_signature()

    def _poll_zone(self):
        if not self.get_mapped():
            return True
        signature = functions.timezone_signature()
        if signature != self._zone_signature:
            self._zone_signature = signature
            time.tzset()
            self.current_zone = current_timezone()
            self._update_zone_label()
            logging.info(f"Time zone changed externally: {self.current_zone!r}")
        self._update_time_label()
        return True

    def stop(self):
        if self._poll_id is not None:
            GLib.source_remove(self._poll_id)
            self._poll_id = None

    def open_datetime_dialog(self, _widget):
        now = datetime.datetime.now()
        self.picker = [now.year, now.month, now.day, now.hour, now.minute]

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        content.set_valign(Gtk.Align.CENTER)
        content.set_margin_top(20)
        content.set_margin_bottom(15)
        content.set_margin_start(20)
        content.set_margin_end(20)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(xalign=0)
        title.set_markup(
            f"<span size='x-large'><b>{GLib.markup_escape_text(_('Set Date & Time'))}</b></span>"
        )
        header.pack_start(title, False, False, 0)
        self.picker_preview = Gtk.Label(xalign=0)
        self.picker_preview.set_opacity(0.7)
        header.pack_start(self.picker_preview, False, False, 0)
        content.add(header)

        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, vexpand=False)
        card.get_style_context().add_class("elevated")

        self.picker_labels = []
        for index, name in enumerate((_("Year"), _("Month"), _("Day"), _("Hour"), _("Minute"))):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
            column.set_margin_top(12)
            column.set_margin_bottom(12)
            column.set_margin_start(14)
            column.set_margin_end(14)

            label = Gtk.Label(label=name)
            label.set_opacity(0.7)
            column.pack_start(label, False, False, 0)

            up = self.panel._gtk.Button("arrow-up", scale=0.7)
            up.get_style_context().add_class("picker-arrow")
            up.set_vexpand(False)
            up.set_size_request(-1, int(self.panel._gtk.font_size * 2.6))
            up.connect("clicked", self._step_picker, index, 1)
            column.pack_start(up, False, False, 0)

            value = Gtk.Label(valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, hexpand=True)
            value.set_size_request(-1, int(self.panel._gtk.font_size * 3))
            column.pack_start(value, False, False, 0)

            down = self.panel._gtk.Button("arrow-down", scale=0.7)
            down.get_style_context().add_class("picker-arrow")
            down.set_vexpand(False)
            down.set_size_request(-1, int(self.panel._gtk.font_size * 2.6))
            down.connect("clicked", self._step_picker, index, -1)
            column.pack_start(down, False, False, 0)

            card.pack_start(column, True, True, 0)
            if index == 2:
                card.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)
            self.picker_labels.append(value)
        content.add(card)

        buttons = [
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-default"},
            {"name": _("Accept"), "response": Gtk.ResponseType.OK, "style": "dialog-default"},
        ]
        self._refresh_picker()
        self.panel._gtk.Dialog(_("Set Date & Time"), buttons, content, self._datetime_response)

    def _refresh_picker(self):
        for index, label in enumerate(self.picker_labels):
            digits = 4 if index == 0 else 2
            label.set_markup(
                f"<span size='xx-large'><b>{self.picker[index]:0{digits}d}</b></span>"
            )
        use_24h = self.panel._config.get_main_config().getboolean("24htime", True)
        fmt = "%Y-%m-%d %H:%M" if use_24h else "%Y-%m-%d %I:%M %p"
        self.picker_preview.set_text(datetime.datetime(*self.picker).strftime(fmt))

    def _step_picker(self, _widget, index, delta):
        year, month, day, hour, minute = self.picker
        if index == 0:
            year = min(max(year + delta, 1970), 2099)
            day = min(day, days_in_month(year, month))
        elif index == 1:
            month = (month - 1 + delta) % 12 + 1
            day = min(day, days_in_month(year, month))
        elif index == 2:
            day = (day - 1 + delta) % days_in_month(year, month) + 1
        elif index == 3:
            hour = (hour + delta) % 24
        else:
            minute = (minute + delta) % 60
        self.picker = [year, month, day, hour, minute]
        self._refresh_picker()

    def _datetime_response(self, dialog, response_id):
        self.panel._gtk.remove_dialog(dialog)
        if response_id != Gtk.ResponseType.OK:
            return
        value = datetime.datetime(*self.picker, second=0)
        if not set_datetime(value):
            self.panel._screen.show_popup_message(_("Failed to set date and time"))
            return
        self.auto_time = auto_time_enabled()
        self._updating = True
        self.auto_time_switch.set_active(self.auto_time)
        self._updating = False
        self._update_sensitivity()
        self._update_time_label()

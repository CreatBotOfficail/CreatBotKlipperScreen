import json
import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

try:
    import qrcode
    import qrcode.image.svg

    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False
    logging.warning(
        "qrcode library not available. QR code generation will be disabled."
    )


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Cloud")
        super().__init__(screen, title)

        try:
            self.cloud_status = self._printer.creatcloud or {}
        except (AttributeError, TypeError):
            self.cloud_status = {}
            logging.warning("Failed to get creatcloud data, using empty dict")

        self._ensure_required_keys()
        self._lan_only_timer = None
        self._pending_lan_only = None
        self.qr_url = "https://www.creatbot.com/creatcloud"
        self.create_ui()

    def _ensure_required_keys(self):
        required_keys = {
            "hostname": "Unknown",
            "machine_id": "Unknown",
            "local_ip": "0.0.0.0",
            "actived": False,
            "online": False,
        }

        for key, default_value in required_keys.items():
            if key not in self.cloud_status or self.cloud_status[key] is None:
                self.cloud_status[key] = default_value

    def create_ui(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        root = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=0, homogeneous=True
        )
        root.set_margin_left(15)
        root.set_margin_right(15)
        root.set_margin_top(15)
        root.set_margin_bottom(15)

        root.pack_start(self._build_left(), True, True, 10)
        root.pack_start(self._build_right(), True, True, 10)

        scrolled.add(root)
        self.content.add(scrolled)

    def _build_left(self):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("menu")
        frame.set_hexpand(True)
        frame.set_vexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_margin_left(20)
        vbox.set_margin_right(20)
        vbox.set_valign(Gtk.Align.CENTER)

        self.qr_image = Gtk.Image()
        self.qr_image.set_halign(Gtk.Align.CENTER)
        self.qr_image.set_valign(Gtk.Align.CENTER)
        vbox.pack_start(self.qr_image, True, True, 0)

        self.network_tip_label = Gtk.Label()
        self.network_tip_label.set_markup('<span size="small" weight="bold">' + _("Connect device to network") + '</span>')
        self.network_tip_label.set_halign(Gtk.Align.CENTER)
        self.network_tip_label.set_no_show_all(True)
        vbox.pack_start(self.network_tip_label, False, False, 0)

        self.generate_qr_code()

        frame.add(vbox)
        frame.get_style_context().add_class("elevated")
        return frame

    def _build_right(self):
        screen = Gdk.Screen.get_default()
        avail_h = screen.get_height()
        scale = max(1, min(8, avail_h * 0.01 - 2))

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_vexpand(True)
        root.set_margin_top(int(1 * scale))
        root.set_margin_bottom(int(1 * scale))
        root.set_margin_left(int(1 * scale))
        root.set_margin_right(int(1 * scale))

        pad = max(10, int(2 * scale))

        root.pack_start(self._build_toggle_card(scale, pad), False, False, 0)

        root.pack_start(self._build_info_card(scale, pad), True, True, int(2 * scale))

        root.pack_end(self._build_usage_card(scale, pad), True, True, 0)

        return root

    def _build_usage_card(self, scale, pad):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("elevated")

        frame.set_hexpand(True)
        frame.set_vexpand(False)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(3 * scale))
        vbox.set_margin_top(pad)
        vbox.set_margin_bottom(pad)
        vbox.set_margin_start(pad)
        vbox.set_margin_end(pad)

        texts = [
            _("Scan left QR to install CreatCloud"),
            _("○ Open the app - click \"+\" to add a printer"),
            _("○ Rescan left QR to add printe"),
            _("○ Follow the prompts to complete the setup"),
            _("[After turning on LAN only] Connect phone and printer to the same Wi-Fi, then use the APP to connect the device."),
        ]

        for idx, txt in enumerate(texts):
            if idx == 0 or idx == 4:
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                hbox.set_halign(Gtk.Align.START)

                icon_name = "hint" if idx == 0 else "light_hint"
                icon = self._gtk.Image(icon_name, self._gtk.content_width * .03, self._gtk.content_height * .03)
                icon.set_valign(Gtk.Align.START)
                hbox.pack_start(icon, False, False, 0)

                lbl = Gtk.Label()
                lbl.set_name("usage-item")
                lbl.set_line_wrap(True)
                lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                lbl.set_halign(Gtk.Align.START)
                lbl.set_hexpand(True)
                lbl.set_vexpand(False)

                if idx == 0:
                    lbl.override_font(Pango.FontDescription("small"))
                    lbl.set_markup(f'<span size="small"><b>{txt}</b></span>')
                else:
                    lbl.override_font(Pango.FontDescription("small"))
                    lbl.set_markup(f'<span size="small">{txt}</span>')

                hbox.pack_start(lbl, True, True, 0)
                vbox.pack_start(hbox, False, False, 0)
            else:
                lbl = Gtk.Label()
                lbl.set_name("usage-item")
                lbl.set_line_wrap(True)
                lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                lbl.set_halign(Gtk.Align.START)
                lbl.set_hexpand(True)
                lbl.set_vexpand(False)
                lbl.override_font(Pango.FontDescription("small"))
                lbl.set_markup(f'<span size="small">{_(txt)}</span>')
                vbox.pack_start(lbl, False, False, 0)

        frame.add(vbox)
        return frame

    def _build_info_card(self, scale, pad):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("elevated")

        grid = Gtk.Grid()
        grid.set_margin_top(pad)
        grid.set_margin_bottom(pad)
        grid.set_margin_left(pad)
        grid.set_margin_right(pad)
        grid.set_row_spacing(int(2 * scale))
        grid.set_column_spacing(int(6 * scale))
        grid.set_valign(Gtk.Align.CENTER)

        def add_row(row, label, value_label):
            lab = Gtk.Label()
            lab.set_name("title-bold")
            lab.set_markup('<span weight="bold" size="small">' + _(label) + "</span>")
            lab.set_halign(Gtk.Align.START)
            grid.attach(lab, 0, row, 1, 1)
            value_label.set_halign(Gtk.Align.START)
            value_label.set_selectable(True)
            value_label.override_font(Pango.FontDescription.from_string("small"))
            grid.attach(value_label, 1, row, 1, 1)

        self.hostname_value = Gtk.Label(
            str(self.cloud_status.get("hostname", "Unknown"))
        )
        self.serial_value = Gtk.Label(
            str(self.cloud_status.get("machine_id", "Unknown"))
        )
        self.ip_value = Gtk.Label(str(self.cloud_status.get("local_ip", "0.0.0.0")))
        self.update_local_ip()

        add_row(0, _("Hostname:"), self.hostname_value)
        add_row(1, _("Serial Number:"), self.serial_value)
        add_row(2, _("IP Address:"), self.ip_value)

        frame.add(grid)
        return frame

    def _build_toggle_card(self, scale, pad):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("elevated")

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(8 * scale))
        hbox.set_margin_top(pad)
        hbox.set_margin_bottom(pad)
        hbox.set_margin_left(2 * pad)
        hbox.set_margin_right(pad)

        switch_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        switch_label = Gtk.Label()
        switch_label.set_name("title-bold")
        switch_label.set_markup(
            '<span weight="bold" size="small">' + _("LAN Only") + "</span>"
        )
        switch_label.set_halign(Gtk.Align.START)
        switch_hbox.pack_start(switch_label, False, False, 0)

        self.lan_only_switch = Gtk.Switch()
        actived = self.cloud_status.get("actived", False)
        self.lan_only_switch.set_active(not actived)

        self.lan_only_switch.connect("button-release-event", self.on_lan_only_toggled)
        self.lan_only_switch.set_halign(Gtk.Align.END)
        switch_hbox.pack_end(self.lan_only_switch, False, False, 0)

        hbox.pack_start(switch_hbox, True, True, 0)
        frame.add(hbox)
        return frame

    def generate_qr_code(self):
        local_ip = self.cloud_status.get("local_ip", "")
        has_network = local_ip and local_ip != "0.0.0.0"

        if not has_network:
            self._show_no_network_state()
            return

        self._hide_network_tip()

        if not QR_AVAILABLE:
            self.qr_image.set_from_icon_name("dialog-error", Gtk.IconSize.DIALOG)
            return

        try:
            if not self.cloud_status:
                logging.warning("No cloud status data for QR code")
                self.qr_image.set_from_icon_name("dialog-warning", Gtk.IconSize.DIALOG)
                return

            qr_data = self.cloud_status
            qr_payload = f"{self.qr_url}?{json.dumps(qr_data)}"
            screen = Gdk.Screen.get_default()
            min_dim = min(screen.get_width(), screen.get_height())
            qr_size = max(150, min(400, int(min_dim * 0.45)))

            qr = qrcode.QRCode(
                version=3,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=2,
            )
            qr.add_data(qr_payload)
            qr.make(fit=True)

            factory = qrcode.image.svg.SvgFillImage
            qr_img = qr.make_image(
                image_factory=factory, fill_color="black", back_color="white"
            )
            svg_path = "/tmp/creatcloud_qr.svg"
            qr_img.save(svg_path)

            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(svg_path, qr_size, qr_size)
            self.qr_image.set_from_pixbuf(pixbuf)

        except Exception as e:
            logging.error(f"QR error: {e}")
            self.qr_image.set_from_icon_name("dialog-error", Gtk.IconSize.DIALOG)

    def _show_no_network_state(self):
        try:
            screen = Gdk.Screen.get_default()
            min_dim = min(screen.get_width(), screen.get_height())
            icon_size = max(150, min(400, int(min_dim * 0.40)))

            icon = self._gtk.Image("without_network", icon_size, icon_size)
            self.qr_image.set_from_pixbuf(icon.get_pixbuf())

        except Exception as e:
            logging.error(f"Error loading without_network icon: {e}")
            self.qr_image.set_from_icon_name("network-offline", Gtk.IconSize.DIALOG)

        if hasattr(self, 'network_tip_label'):
            self.network_tip_label.show()
        else:
            logging.warning("network_tip_label not found, skipping tip display")

    def _hide_network_tip(self):
        if hasattr(self, 'network_tip_label'):
            self.network_tip_label.hide()

    def update_local_ip(self):
        ip_address = self.cloud_status.get("local_ip") or "0.0.0.0"
        self.ip_value.set_text(str(ip_address))
        self.generate_qr_code()

    def on_lan_only_toggled(self, switch, gparam):
        self._pending_lan_only = switch.get_active()

        if self._lan_only_timer is not None:
            GLib.source_remove(self._lan_only_timer)
            self._lan_only_timer = None

        self._lan_only_timer = GLib.timeout_add(3000, self._on_lan_only_debounced)

    def _on_lan_only_debounced(self):

        lan_only = self._pending_lan_only
        self._pending_lan_only = None
        self._lan_only_timer = None

        def _do_post():
            try:
                self._screen.apiclient.post_request(
                    "/server/creatcloud/enable", json={"active": lan_only}
                )
                logging.info("LAN Only toggled (debounced): %s", not lan_only)
            except Exception as e:
                logging.error("Failed to update LAN Only: %s", e)

        GLib.idle_add(_do_post)
        return GLib.SOURCE_REMOVE

    def auto_refresh_qr_code(self):
        try:
            self.generate_qr_code()
            self.update_local_ip()
        except Exception as e:
            logging.error("Auto refresh failed: %s", e)
        return True

    def activate(self):
        GLib.timeout_add(500, self._delayed_refresh)

    def _delayed_refresh(self):
        self.auto_refresh_qr_code()
        return False

    def process_update(self, action, data):
        if action != "notify_creatcloud_info_update":
            return
        if "actived" in data:
            self.lan_only_switch.set_active(not data["actived"])
        GLib.timeout_add(300, self._delayed_refresh)

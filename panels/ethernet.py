import logging
import ipaddress
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib
from ks_includes.screen_panel import ScreenPanel
from ks_includes.sdbus_nm import SdbusNm


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Ethernet")
        super().__init__(screen, title)
        try:
            self.sdbus_nm = SdbusNm(self.popup_callback)
        except Exception as e:
            logging.exception("Failed to initialize")
            self.sdbus_nm = None
            self.error_box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                hexpand=True,
                vexpand=True
            )
            message = (
                _("Failed to initialize") + "\n"
                + "This panel needs NetworkManager installed into the system\n"
                + "And the apropriate permissions, without them it will not function.\n"
                + f"\n{e}\n"
            )
            self.error_box.add(
                Gtk.Label(
                    label=message,
                    wrap=True,
                    wrap_mode=Pango.WrapMode.WORD_CHAR,
                )
            )
            self.error_box.set_valign(Gtk.Align.CENTER)
            self.content.add(self.error_box)
            self._screen.panels_reinit.append(self._screen._cur_panels[-1])
            return

        self.interface = self.sdbus_nm.get_wired_interface()
        if not self.interface:
            label = Gtk.Label(_("No wired interface has been found"))
            label.set_halign(Gtk.Align.CENTER)
            label.set_valign(Gtk.Align.CENTER)
            self.content.add(label)
            self.content.show_all()
            return

        self.info = {}
        self.labels = {}
        self.refresh_timer_id = None
        self.main_box = None

        self.create_ui()
        self.refresh_info()

    def create_ui(self):
        scroll = self._gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.main_box.set_margin_start(20)
        self.main_box.set_margin_end(20)
        self.main_box.set_margin_top(20)
        self.main_box.set_margin_bottom(20)

        top_frame = Gtk.Frame()
        top_frame.get_style_context().add_class("menu")
        top_frame.get_style_context().add_class("elevated")

        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        top_box.set_margin_start(20)
        top_box.set_margin_end(20)
        top_box.set_margin_top(15)
        top_box.set_margin_bottom(15)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        status_box.set_hexpand(True)
        status_box.set_halign(Gtk.Align.START)

        self.cable_icon = self._gtk.Image("ethernet", self._gtk.font_size * 2.5, self._gtk.font_size * 2.5)
        status_box.pack_start(self.cable_icon, False, False, 0)

        self.cable_status_label = Gtk.Label()
        self.cable_status_label.set_markup('<span weight="bold" size="large">' + _("Cable Disconnected") + '</span>')
        status_box.pack_start(self.cable_status_label, False, False, 0)

        dhcp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        dhcp_box.set_hexpand(False)
        dhcp_box.set_halign(Gtk.Align.END)

        dhcp_label = Gtk.Label(label=_("DHCP"))
        dhcp_label.get_style_context().add_class("settings-label")
        dhcp_box.pack_start(dhcp_label, False, False, 0)

        self.dhcp_switch = Gtk.Switch()
        self.dhcp_switch.set_active(self.sdbus_nm.get_wired_dhcp_state(self.interface))
        self.dhcp_switch.connect("notify::active", self.on_dhcp_toggled)
        dhcp_box.pack_start(self.dhcp_switch, False, False, 0)

        top_box.pack_start(status_box, True, True, 0)
        top_box.pack_end(dhcp_box, False, False, 0)
        top_frame.add(top_box)
        self.main_box.pack_start(top_frame, False, False, 0)

        config_frame = Gtk.Frame()
        config_frame.get_style_context().add_class("menu")
        config_frame.get_style_context().add_class("elevated")
        config_frame.set_vexpand(True)

        config_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        config_vbox.set_margin_start(10)
        config_vbox.set_margin_end(10)
        config_vbox.set_margin_top(10)
        config_vbox.set_margin_bottom(10)

        config_list = Gtk.ListBox()
        config_list.set_selection_mode(Gtk.SelectionMode.NONE)
        config_list.get_style_context().add_class("settings_list")
        config_list.set_hexpand(True)

        info = self.sdbus_nm.get_wired_info(self.interface)
        info["mac_address"] = self.sdbus_nm.get_wired_mac_address(self.interface)

        self.mac_label = self._create_info_row(config_list, _("MAC Address"),
                                                info.get("mac_address", ""), readonly=True)

        self.ip_entry = self._create_config_row(config_list, _("IP Address"),
                                                 info.get("ip_address", ""), "")

        self.netmask_entry = self._create_config_row(config_list, _("Subnet Mask"),
                                                       info.get("netmask", ""), "")

        self.gateway_entry = self._create_config_row(config_list, _("Gateway"),
                                                       info.get("gateway", ""), "")

        self.dns_entry = self._create_config_row(config_list, _("DNS"),
                                                  info.get("dns", ""), "")

        config_vbox.pack_start(config_list, True, True, 0)

        hint_label = Gtk.Label()
        hint_label.set_markup(f'<span size="small" color="gray">{_("Multiple DNS separated by comma")}</span>')
        hint_label.set_margin_top(10)
        hint_label.set_xalign(0)
        hint_label.set_margin_start(5)
        config_vbox.pack_start(hint_label, False, False, 0)

        config_frame.add(config_vbox)
        self.main_box.pack_start(config_frame, True, True, 0)

        self.save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.save_box.set_halign(Gtk.Align.END)

        self.save_button = self._gtk.Button("complete", _("Save"), "color3")
        self.save_button.connect("clicked", self.save_config)
        self.save_box.pack_end(self.save_button, False, False, 0)
        self.main_box.pack_start(self.save_box, False, False, 0)

        scroll.add(self.main_box)
        self.content.add(scroll)

        is_dhcp = self.dhcp_switch.get_active()
        self.set_entries_sensitive(not is_dhcp)
        self.update_save_button_visibility(not is_dhcp)

        self.content.show_all()

    def _create_info_row(self, listbox, label_text, value, readonly=False):
        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_margin_top(12)
        hbox.set_margin_bottom(12)
        hbox.set_margin_start(15)
        hbox.set_margin_end(15)

        label = Gtk.Label(label=label_text, hexpand=True, halign=Gtk.Align.START)
        label.get_style_context().add_class("settings-label")

        value_label = Gtk.Label(label=value, halign=Gtk.Align.END)
        value_label.set_opacity(0.5)

        hbox.pack_start(label, True, True, 0)
        hbox.pack_end(value_label, False, False, 0)

        row.add(hbox)
        listbox.add(row)

        return value_label

    def _create_config_row(self, listbox, label_text, value, placeholder):
        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_margin_top(12)
        hbox.set_margin_bottom(12)
        hbox.set_margin_start(15)
        hbox.set_margin_end(15)

        label = Gtk.Label(label=label_text, hexpand=True, halign=Gtk.Align.START)
        label.get_style_context().add_class("settings-label")

        entry = Gtk.Entry(hexpand=False, halign=Gtk.Align.END)
        entry.set_text(value)
        entry.set_placeholder_text(placeholder)
        entry.connect("focus-in-event", self._on_entry_focus)
        entry.set_width_chars(18)

        hbox.pack_start(label, True, True, 0)
        hbox.pack_end(entry, False, False, 0)

        row.add(hbox)
        listbox.add(row)

        return entry

    def _on_entry_focus(self, widget, event):
        self._screen.remove_keyboard()
        self._screen.show_keyboard(widget)

    def set_entries_sensitive(self, sensitive):
        entries = [
            self.ip_entry,
            self.netmask_entry,
            self.gateway_entry,
            self.dns_entry
        ]
        for entry in entries:
            entry.set_sensitive(sensitive)
            if sensitive:
                entry.set_opacity(1.0)
            else:
                entry.set_opacity(0.5)

    def update_save_button_visibility(self, sensitive):
        self.save_button.set_sensitive(sensitive)
        if sensitive:
            self.save_button.set_opacity(1.0)
        else:
            self.save_button.set_opacity(0.5)

    def popup_callback(self, message, level=2):
        self._screen.show_popup_message(message, level)

    def refresh_info(self):
        cable_connected = self.sdbus_nm.get_wired_carrier_state(self.interface)
        if cable_connected:
            self.cable_status_label.set_markup('<span weight="bold" size="large" color="#4CAF50">' + _("Cable Connected") + '</span>')
            self.cable_icon.set_opacity(1.0)
        else:
            self.cable_status_label.set_markup('<span weight="bold" size="large" color="#F44336">' + _("Cable Disconnected") + '</span>')
            self.cable_icon.set_opacity(0.5)

        self.info = self.sdbus_nm.get_wired_info(self.interface)
        self.info["mac_address"] = self.sdbus_nm.get_wired_mac_address(self.interface)

        self.mac_label.set_text(self.info.get("mac_address", ""))

        self.ip_entry.set_text(self.info.get("ip_address", ""))
        self.netmask_entry.set_text(self.info.get("netmask", ""))
        self.gateway_entry.set_text(self.info.get("gateway", ""))
        self.dns_entry.set_text(self.info.get("dns", ""))

    def on_dhcp_toggled(self, switch, gparam):
        enable = switch.get_active()
        logging.info(f"DHCP toggled: {enable}")

        self.set_entries_sensitive(not enable)
        self.update_save_button_visibility(not enable)

        result = self.sdbus_nm.set_wired_dhcp(self.interface, enable)
        if "error" in result:
            self._screen.show_popup_message(result.get("message", _("Failed to update network")))
            switch.set_active(not enable)
            self.set_entries_sensitive(enable)
            self.update_save_button_visibility(enable)
            return

        self.refresh_info()

    def save_config(self, widget):
        self._screen.remove_keyboard()

        is_dhcp = self.dhcp_switch.get_active()
        logging.info(f"Saving ethernet config, DHCP={is_dhcp}")

        if is_dhcp:
            result = self.sdbus_nm.set_wired_dhcp(self.interface, True)
        else:
            ip = self.ip_entry.get_text().strip()
            netmask = self.netmask_entry.get_text().strip()
            gateway = self.gateway_entry.get_text().strip()
            dns = self.dns_entry.get_text().strip()

            if not self.sdbus_nm.is_valid_ipv4(ip):
                self._screen.show_popup_message(_("Invalid IP address"))
                return

            logging.info(f"Setting static IP: {ip}, netmask: {netmask}, gateway: {gateway}, dns: {dns}")
            dns_list = [d.strip() for d in dns.split(",") if d.strip()]
            result = self.sdbus_nm.set_wired_manual(self.interface, ip, netmask, gateway, dns_list)

        logging.info(f"Save result: {result}")
        if "error" in result:
            self._screen.show_popup_message(result.get("message", _("Failed to save configuration")))
        else:
            self.dhcp_switch.grab_focus()
            self._screen.show_popup_message(_("Configuration saved"), level=1)
            self.refresh_info()

    def activate(self):
        is_dhcp = self.dhcp_switch.get_active()
        self.update_save_button_visibility(not is_dhcp)

        self.refresh_timer_id = GLib.timeout_add_seconds(2, self._periodic_refresh)

    def deactivate(self):
        if self.refresh_timer_id:
            GLib.source_remove(self.refresh_timer_id)
            self.refresh_timer_id = None

    def _periodic_refresh(self):
        if self.sdbus_nm:
            cable_connected = self.sdbus_nm.get_wired_carrier_state(self.interface)
            if cable_connected:
                self.cable_status_label.set_markup('<span weight="bold" size="large" color="#4CAF50">' + _("Cable Connected") + '</span>')
                self.cable_icon.set_opacity(1.0)
            else:
                self.cable_status_label.set_markup('<span weight="bold" size="large" color="#F44336">' + _("Cable Disconnected") + '</span>')
                self.cable_icon.set_opacity(0.5)

            if self.dhcp_switch.get_active():
                self.info = self.sdbus_nm.get_wired_info(self.interface)
                self.ip_entry.set_text(self.info.get("ip_address", ""))
                self.netmask_entry.set_text(self.info.get("netmask", ""))
                self.gateway_entry.set_text(self.info.get("gateway", ""))
                self.dns_entry.set_text(self.info.get("dns", ""))

        return True
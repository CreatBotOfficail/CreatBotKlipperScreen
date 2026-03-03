import subprocess
import logging
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango
from ks_includes.screen_panel import ScreenPanel
from ks_includes.sdbus_nm import SdbusNm


class Panel(ScreenPanel):

    def __init__(self, screen, title):
        title = title or _("Network")
        super().__init__(screen, title)
        self.show_add = False
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
        self.reload_timer_id = None
        self.monitor_timer_id = None
        self.delay_reload_timer_id = None
        self.config_refresh_timer_id = None
        self.init_status = False
        self.reload = False
        self.last_state = None
        self.network_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.network_rows = {}
        self.networks = {}
        self.wifi_signal_icons = {
            "excellent": self._gtk.PixbufFromIcon(
                "wifi_excellent", width=self._gtk.content_width * 0.06, height=self._gtk.content_height * 0.06
            ),
            "good": self._gtk.PixbufFromIcon(
                "wifi_good", width=self._gtk.content_width * 0.06, height=self._gtk.content_height * 0.06
            ),
            "fair": self._gtk.PixbufFromIcon(
                "wifi_fair", width=self._gtk.content_width * 0.06, height=self._gtk.content_height * 0.06
            ),
            "weak": self._gtk.PixbufFromIcon(
                "wifi_weak", width=self._gtk.content_width * 0.06, height=self._gtk.content_height * 0.06
            ),
        }

        self.network_interfaces = self.sdbus_nm.get_interfaces()
        logging.info(f"Network interfaces: {self.network_interfaces}")

        self.wireless_interfaces = [iface.interface for iface in self.sdbus_nm.get_wireless_interfaces()]
        logging.info(f"Wireless interfaces: {self.wireless_interfaces}")

        self.interface = self.sdbus_nm.get_primary_interface()
        logging.info(f"Primary interface: {self.interface}")

        self.labels['interface'] = Gtk.Label(hexpand=True)
        self.labels['ip'] = Gtk.Label(hexpand=True)
        self.network_interface_refresh()

        self.reload_button = self._gtk.Button("refresh", None, "custom-icon-button", self.bts)
        self.reload_button.set_no_show_all(True)
        self.reload_button.connect("clicked", self.reload_networks)
        self.reload_button.set_hexpand(False)

        self.wifi_toggle = Gtk.Switch(
            width_request=round(self._gtk.font_size * 2),
            height_request=round(self._gtk.font_size),
            active=self.sdbus_nm.is_wifi_enabled()
        )
        self.wifi_toggle.connect("notify::active", self.toggle_wifi)

        sbox = Gtk.Box(hexpand=True, vexpand=False)
        sbox.add(self.labels['interface'])
        sbox.add(self.labels['ip'])
        sbox.add(self.reload_button)
        sbox.add(self.wifi_toggle)

        scroll = self._gtk.ScrolledWindow()
        self.labels['main_box'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)

        if self.sdbus_nm.wifi:
            self.labels['main_box'].pack_start(sbox, False, False, 5)
            scroll.add(self.network_list)
            if self.sdbus_nm.nm.wireless_enabled:
                self.reload_button.show()
                self.sdbus_nm.enable_monitoring(True)
                self.monitor_timer_id = GLib.timeout_add(500, self.sdbus_nm.monitor_connection_status)
        else:
            self._screen.show_popup_message(_("No wireless interface has been found"), level=2)
            self.labels["networkinfo"] = Gtk.Label()
            scroll.add(self.labels["networkinfo"])

        self.labels["main_box"].pack_start(scroll, True, True, 0)
        self.content.add(self.labels["main_box"])
        self.network_list.connect("row-activated", self.handle_wifi_selection)

    def popup_callback(self, msg, level=3):
        self.network_interface_refresh()
        if not self.refresh_status(msg):
            for item in self.network_rows:
                if self.network_rows[item]["label_state"] is not None:
                    self.network_rows[item]["label_state"].set_no_show_all(True)
                    self.network_rows[item]["label_state"].hide()
            self._screen.show_popup_message(msg, level)

    def network_interface_refresh(self):
        mac_address = self.sdbus_nm.get_wireless_mac_address()
        ip_address = self.sdbus_nm.get_wireless_ip_address()
        self.labels['interface'].set_text(_("MAC") + f': {mac_address}')
        self.labels['ip'].set_text(f"IP: {ip_address}")

    def handle_wifi_selection(self, list_box, row):
        index = row.get_index()
        logging.info(f"clicked SSID is {self.networks[index]['SSID']}")
        self.connect_network(list_box, self.networks[index]["SSID"])

    def add_network_item(self, ssid, lock, known, signal, is_connected=False):
        self.network_rows[ssid] = {}
        self.network_rows[ssid]["row"] = Gtk.ListBoxRow()
        self.network_rows[ssid]["hbox"] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        self.network_rows[ssid]["row"].add(self.network_rows[ssid]["hbox"])
        self.network_rows[ssid]["row"].get_style_context().add_class("frame-item")

        self.network_rows[ssid]["signal_ico"] = self._gtk.Image()
        self.network_rows[ssid]["signal_ico"].set_from_pixbuf(self.get_signal_strength_icon(signal))
        self.network_rows[ssid]["signal_ico"].set_margin_start(50)
        self.network_rows[ssid]["hbox"].pack_start(self.network_rows[ssid]["signal_ico"], False, True, 20)

        self.network_rows[ssid]["label_box"] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.network_rows[ssid]["label_ssid"] = Gtk.Label(label=ssid, xalign=0)
        self.network_rows[ssid]["label_state"] = Gtk.Label(label="", xalign=0)
        self.network_rows[ssid]["label_state"].set_ellipsize(Pango.EllipsizeMode.END)
        self.network_rows[ssid]["label_state"].set_no_show_all(True)
        self.network_rows[ssid]["label_box"].pack_start(self.network_rows[ssid]["label_ssid"], True, False, 0)
        self.network_rows[ssid]["label_box"].pack_start(self.network_rows[ssid]["label_state"], True, False, 0)
        self.network_rows[ssid]["hbox"].pack_start(self.network_rows[ssid]["label_box"], False, True, 10)

        if is_connected:
            self.network_rows[ssid]["edit"] = self._gtk.Button("settings", None, "custom-icon-button", self.bts)
            self.network_rows[ssid]["edit"].connect("clicked", self.show_network_config_dialog, ssid)
            self.network_rows[ssid]["edit"].set_hexpand(False)
            self.network_rows[ssid]["edit"].set_halign(Gtk.Align.END)
            self.network_rows[ssid]["hbox"].pack_end(self.network_rows[ssid]["edit"], False, True, 10)

        if known:
            self.network_rows[ssid]["delete"] = self._gtk.Button("delete", None, "custom-icon-button", self.bts)
            self.network_rows[ssid]["delete"].connect("clicked", self.remove_confirm_dialog, ssid, ssid)
            self.network_rows[ssid]["delete"].set_hexpand(False)
            self.network_rows[ssid]["delete"].set_halign(Gtk.Align.END)
            self.network_rows[ssid]["hbox"].pack_end(self.network_rows[ssid]["delete"], False, True, 10)

        if "Open" not in lock:
            self.network_rows[ssid]["lock_image"] = self._gtk.Image(
                "lock", self._gtk.content_width * 0.04, self._gtk.content_height * 0.04
            )
            self.network_rows[ssid]["lock_image"].set_hexpand(False)
            self.network_rows[ssid]["lock_image"].set_halign(Gtk.Align.END)
            self.network_rows[ssid]["hbox"].pack_end(self.network_rows[ssid]["lock_image"], False, True, 10)

        self.network_rows[ssid]["hbox"].set_margin_end(50)
        self.network_list.add(self.network_rows[ssid]["row"])

    def move_network_to_front(self, networks, target_name):
        if not target_name or (networks and networks[0].get("SSID") == target_name):
            return networks
        target_index = next((i for i, network in enumerate(networks) if network.get("SSID") == target_name), None)
        if target_index is not None:
            target_network = networks.pop(target_index)
            networks.insert(0, target_network)
        return networks

    def load_networks(self):
        self.connected_ap = self.sdbus_nm.get_connected_ap()
        ap_ssid = None
        if self.connected_ap:
            ap_ssid = self.connected_ap.ssid.decode("utf-8")
        self.networks = self.move_network_to_front(self.sdbus_nm.get_networks(), ap_ssid)
        if self.last_state != self.sdbus_nm.wifi_state:
            self.last_state = self.sdbus_nm.wifi_state
            self.sdbus_nm.wifi_state = -1
            self.sdbus_nm.monitor_connection_status()

        for item in self.networks:
            ssid = item.get("SSID")
            if ssid:
                is_connected = (ssid == ap_ssid)
                self.add_network_item(
                    ssid,
                    item.get("security", "unknown"),
                    item.get("known", False),
                    item.get("signal_level", 0),
                    is_connected,
                )
        self.network_list.show_all()

    def remove_confirm_dialog(self, widget, ssid, bssid):

        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(_("Do you want to forget or disconnect %s?") % ssid)
        buttons = [
            {"name": _("Forget"), "response": Gtk.ResponseType.OK, "style": 'dialog-warning'},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": 'dialog-error'},
        ]
        if bssid == self.sdbus_nm.get_connected_bssid():
            buttons.insert(0, {"name": _("Disconnect"), "response": Gtk.ResponseType.APPLY, "style": 'dialog-info'})
        self._gtk.Dialog(_("Remove network"), buttons, label, self.confirm_removal, ssid)

    def confirm_removal(self, dialog, response_id, ssid):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.CANCEL:
            return
        if response_id == Gtk.ResponseType.OK:
            logging.info(f"Deleting {ssid}")
            self.sdbus_nm.delete_network(ssid)
        if response_id == Gtk.ResponseType.APPLY:
            logging.info(f"Disconnecting {ssid}")
            self.sdbus_nm.disconnect_network()
        self.delay_reload_networks(100)

    def add_new_network(self, widget, ssid):
        self._screen.remove_keyboard()
        psk = self.labels["network_psk"].get_text()
        identity = self.labels["network_identity"].get_text()
        eap_method = self.get_dropdown_value(self.labels["network_eap_method"])
        phase2 = self.get_dropdown_value(self.labels["network_phase2"])
        logging.debug(f"{phase2=}")
        logging.debug(f"{eap_method=}")
        result = self.sdbus_nm.add_network(ssid, psk, eap_method, identity, phase2)
        if "error" in result:
            self._screen.show_popup_message(result["message"])
            if result["error"] == "psk_invalid":
                return
        else:
            self.connect_network(widget, ssid, showadd=False)
        self.close_add_network()

    def get_dropdown_value(self, dropdown, default=None):
        tree_iter = dropdown.get_active_iter()
        model = dropdown.get_model()
        result = model[tree_iter][0]
        return result if result != "disabled" else None

    def back(self):
        if self.show_add:
            self._screen.remove_keyboard()
            for child in self.content.get_children():
                self.content.remove(child)
            self.content.add(self.labels['main_box'])
            self.content.show_all()
            for i in ['add_network', 'edit_config', 'network_psk', 'network_identity']:
                if i in self.labels:
                    del self.labels[i]
            self.show_add = False
            return True
        return False

    def close_add_network(self):
        if not self.show_add:
            return

        for child in self.content.get_children():
            self.content.remove(child)
        self.content.add(self.labels['main_box'])
        self.content.show()
        for i in ['add_network', 'network_psk', 'network_identity']:
            if i in self.labels:
                del self.labels[i]
        self.show_add = False

    def get_network_index(self, ssid):
        for index, network in enumerate(self.networks):
            if network.get("SSID") == ssid:
                return index
        return -1

    def connect_network(self, widget, ssid, showadd=True):
        index = self.get_network_index(ssid)
        ssid = self.networks[index]["SSID"]
        if showadd and not self.networks[index]["known"]:  # self.sdbus_nm.is_known(ssid):
            sec_type = self.networks[index]["security"]  # self.sdbus_nm.get_security_type(ssid)
            if sec_type == "Open" or "OWE" in sec_type:
                logging.debug("Network is Open do not show psk")
                result = self.sdbus_nm.add_network(ssid, "", "")
                self.sdbus_nm.connect(ssid)
                if "error" in result:
                    self._screen.show_popup_message(result["message"])
            else:
                self.show_add_network(widget, ssid)
            return
        self.sdbus_nm.connect(ssid)
        self.delay_reload_networks(1000)
        if self.monitor_timer_id is None:
            self.sdbus_nm.enable_monitoring(True)
            self.monitor_timer_id = GLib.timeout_add(500, self.sdbus_nm.monitor_connection_status)

    def remove_network_list(self):
        for row in self.network_list.get_children():
            self.network_list.remove(row)
            row.destroy()
        self.network_rows.clear()

    def show_add_network(self, widget, ssid):
        if self.show_add:
            return

        for child in self.content.get_children():
            self.content.remove(child)
        if "add_network" in self.labels:
            del self.labels["add_network"]
        eap_method = Gtk.ComboBoxText(hexpand=True)
        for method in ("peap", "ttls", "pwd", "leap", "md5"):
            eap_method.append(method, method.upper())
        self.labels["network_eap_method"] = eap_method
        eap_method.set_active(0)

        phase2 = Gtk.ComboBoxText(hexpand=True)
        for method in ("mschapv2", "gtc", "pap", "chap", "mschap", "disabled"):
            phase2.append(method, method.upper())
        self.labels["network_phase2"] = phase2
        phase2.set_active(0)

        self.labels["network_identity"] = Gtk.Entry(hexpand=True, no_show_all=True)
        self.labels["network_identity"].connect("focus-in-event", self._screen.show_keyboard)

        self.labels["network_psk"] = Gtk.Entry(hexpand=True)
        self.labels["network_psk"].set_visibility(False)
        self.labels["network_psk"].connect("activate", self.add_new_network, ssid)
        self.labels["network_psk"].connect("focus-in-event", self._screen.show_keyboard)

        save = self._gtk.Button("load", style="color3")
        save.set_hexpand(False)
        save.connect("clicked", self.add_new_network, ssid)

        user_label = Gtk.Label(label=_("User"), hexpand=False, no_show_all=True)
        auth_grid = Gtk.Grid()
        auth_grid.attach(user_label, 0, 0, 1, 1)
        auth_grid.attach(self.labels["network_identity"], 1, 0, 1, 1)
        auth_grid.attach(Gtk.Label(label=_("Password"), hexpand=False), 0, 1, 1, 1)
        auth_grid.attach(self.labels["network_psk"], 1, 1, 1, 1)
        auth_grid.attach(save, 2, 0, 1, 2)

        self.labels["add_network"] = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=5, valign=Gtk.Align.CENTER, hexpand=True, vexpand=True
        )
        self.labels["add_network"].add(Gtk.Label(label=_("Connecting to %s") % ssid))
        self.labels["add_network"].add(auth_grid)
        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.labels["add_network"])
        self.content.add(scroll)
        self.labels["network_psk"].grab_focus_without_selecting()
        self.content.show_all()
        self.show_add = True

    def get_signal_strength_icon(self, signal_level):
        # networkmanager uses percentage not dbm
        if signal_level > 75:
            return self.wifi_signal_icons["excellent"]
        elif signal_level > 60:
            return self.wifi_signal_icons["good"]
        elif signal_level > 30:
            return self.wifi_signal_icons["fair"]
        else:
            return self.wifi_signal_icons["weak"]

    def refresh_status(self, state=None):
        if state:
            self.connected_ap = self.sdbus_nm.get_connected_ap()
            if self.connected_ap:
                ap_ssid = self.connected_ap.ssid.decode("utf-8")
                self.set_connect_state(ap_ssid, state)
                return True
            else:
                return False

    def set_connect_state(self, ssid, state):
        for item in self.network_rows:
            if self.network_rows[item]["label_state"] is not None:
                self.network_rows[item]["label_state"].set_no_show_all(True)
                self.network_rows[item]["label_state"].hide()
        if ssid and state and ssid in self.network_rows:
            if self.network_rows[ssid]["label_state"] is not None:
                self.network_rows[ssid]["label_state"].set_markup(f'<span color="gray" size="small">{state}</span>')
                self.network_rows[ssid]["label_state"].set_no_show_all(False)
        self.network_list.show_all()

    def reload_networks(self, widget=None):
        if self.reload:
            return
        self.reload = True
        self.remove_network_list()
        del self.network_rows
        self.network_rows = {}
        if self.sdbus_nm is not None and self.sdbus_nm.wifi:
            self._gtk.Button_busy(self.reload_button, True)
            if not self.init_status:
                self.sdbus_nm.rescan()
            else:
                self.init_status = False
            self.load_networks()
        if self.sdbus_nm.get_is_connected():
            self.refresh_status(_('Network connected'))

        self._gtk.Button_busy(self.reload_button, False)
        self.reload = False

        if self.delay_reload_timer_id:
            GLib.source_remove(self.delay_reload_timer_id)
            self.delay_reload_timer_id = None
        self.network_interface_refresh()

        return self.sdbus_nm.nm.wireless_enabled

    def delay_reload_networks(self, s):
        self._gtk.Button_busy(self.reload_button, True)
        if not self.delay_reload_timer_id:
            self.delay_reload_timer_id = GLib.timeout_add(s, self.reload_networks)

    def start_refresh_timer(self):
        if not self.sdbus_nm.monitor_connection_status():
            self.sdbus_nm.enable_monitoring(True)
        if self.monitor_timer_id is None:
            self.monitor_timer_id = GLib.timeout_add(600, self.sdbus_nm.monitor_connection_status)
        if self.reload_timer_id is None:
            self.reload_timer_id = GLib.timeout_add_seconds(10, self.reload_networks)
        return False

    def stop_refresh_timer(self):
        if self.monitor_timer_id is not None:
            self.sdbus_nm.enable_monitoring(False)
            GLib.source_remove(self.monitor_timer_id)
            self.monitor_timer_id = None
        if self.reload_timer_id is not None:
            GLib.source_remove(self.reload_timer_id)
            self.reload_timer_id = None

    def activate(self):
        if self.sdbus_nm is None:
            return
        if self.sdbus_nm.wifi:
            if self.sdbus_nm.is_wifi_enabled():
                self.delay_reload_networks(2000)
                self.start_refresh_timer()

    def deactivate(self):
        if self.sdbus_nm is None:
            return
        self.stop_refresh_timer()

    def toggle_wifi(self, switch, gparams):
        enable = switch.get_active()
        logging.info(f"WiFi {enable}")
        self.sdbus_nm.toggle_wifi(enable)
        if enable:
            self.reload_button.set_no_show_all(False)
            self.reload_button.show()
            self.network_list.set_no_show_all(False)
            self.network_list.show()
            self.init_status = True
            self.delay_reload_networks(3000)
            self.start_refresh_timer()
        else:
            self.stop_refresh_timer()
            self.reload_button.set_no_show_all(True)
            self.reload_button.hide()
            self.network_list.set_no_show_all(True)
            self.network_list.hide()
        self.network_interface_refresh()

    def show_network_config_dialog(self, widget, ssid):
        if self.show_add:
            return

        for child in self.content.get_children():
            self.content.remove(child)

        info = self.sdbus_nm.get_wireless_connection_info()
        is_dhcp = self.sdbus_nm.get_wireless_dhcp_state()
        self._config_ssid = ssid

        scroll = self._gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)

        top_frame = Gtk.Frame()
        top_frame.get_style_context().add_class("menu")
        top_frame.get_style_context().add_class("elevated")

        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        top_box.set_margin_start(20)
        top_box.set_margin_end(20)
        top_box.set_margin_top(15)
        top_box.set_margin_bottom(15)

        wifi_info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        wifi_info_box.set_hexpand(True)
        wifi_info_box.set_halign(Gtk.Align.START)

        wifi_icon = self._gtk.Image("wifi", self._gtk.font_size * 2.5, self._gtk.font_size * 2.5)
        wifi_info_box.pack_start(wifi_icon, False, False, 0)

        ssid_label = Gtk.Label()
        ssid_label.set_markup(f'<span weight="bold" size="large">{ssid}</span>')
        wifi_info_box.pack_start(ssid_label, False, False, 0)

        dhcp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        dhcp_box.set_hexpand(False)
        dhcp_box.set_halign(Gtk.Align.END)

        dhcp_label = Gtk.Label(label=_("DHCP"))
        dhcp_label.get_style_context().add_class("settings-label")
        dhcp_box.pack_start(dhcp_label, False, False, 0)

        self.dhcp_switch = Gtk.Switch()
        self.dhcp_switch.set_active(is_dhcp)
        self.dhcp_switch.connect("notify::active", self.on_dhcp_switch_toggled)
        dhcp_box.pack_start(self.dhcp_switch, False, False, 0)

        top_box.pack_start(wifi_info_box, True, True, 0)
        top_box.pack_end(dhcp_box, False, False, 0)
        top_frame.add(top_box)
        main_box.pack_start(top_frame, False, False, 0)

        config_frame = Gtk.Frame()
        config_frame.get_style_context().add_class("menu")
        config_frame.get_style_context().add_class("elevated")
        config_frame.set_vexpand(False)

        config_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        config_vbox.set_margin_start(10)
        config_vbox.set_margin_end(10)
        config_vbox.set_margin_top(10)
        config_vbox.set_margin_bottom(10)

        config_list = Gtk.ListBox()
        config_list.set_selection_mode(Gtk.SelectionMode.NONE)
        config_list.get_style_context().add_class("settings_list")
        config_list.set_hexpand(True)

        self.ip_entry = self._create_config_row(config_list, _("IP Address"),
                                                  info.get("ip_address", "0.0.0.0"), "192.168.1.100")

        self.netmask_entry = self._create_config_row(config_list, _("Subnet Mask"),
                                                      info.get("netmask", "255.255.255.0"), "255.255.255.0")

        self.gateway_entry = self._create_config_row(config_list, _("Gateway"),
                                                      info.get("gateway", ""), "192.168.1.1")

        self.dns_entry = self._create_config_row(config_list, _("DNS"),
                                                  info.get("dns", ""), "8.8.8.8, 8.8.4.4")

        config_vbox.pack_start(config_list, True, True, 0)

        hint_label = Gtk.Label()
        hint_label.set_markup(f'<span size="small" color="gray">{_("Multiple DNS separated by comma")}</span>')
        hint_label.set_margin_top(10)
        hint_label.set_xalign(0)
        hint_label.set_margin_start(5)
        config_vbox.pack_start(hint_label, False, False, 0)

        config_frame.add(config_vbox)
        main_box.pack_start(config_frame, True, True, 0)

        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        save_box.set_halign(Gtk.Align.END)

        self.save_button = self._gtk.Button("complete", _("Save"), "color3")
        self.save_button.connect("clicked", self.save_network_config_inline)
        save_box.pack_end(self.save_button, False, False, 0)
        main_box.pack_start(save_box, False, False, 0)

        scroll.add(main_box)
        self.content.add(scroll)

        self.set_ip_entries_sensitive(not is_dhcp)
        self.set_save_button_sensitive(not is_dhcp)
        self.ip_entry.grab_focus_without_selecting()
        self.content.show_all()
        self.show_add = True

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

    def on_dhcp_switch_toggled(self, switch, gparams):

        is_dhcp = switch.get_active()
        self.set_ip_entries_sensitive(not is_dhcp)
        self.set_save_button_sensitive(not is_dhcp)

        if is_dhcp:
            self.save_network_config_inline(None)

    def set_ip_entries_sensitive(self, sensitive):

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

    def set_save_button_sensitive(self, sensitive):
        if not hasattr(self, "save_button") or self.save_button is None:
            return
        self.save_button.set_sensitive(sensitive)
        self.save_button.set_opacity(1.0 if sensitive else 0.5)

    def close_network_config(self):

        if not self.show_add:
            return

        if self.config_refresh_timer_id:
            GLib.source_remove(self.config_refresh_timer_id)
            self.config_refresh_timer_id = None

        self._screen.remove_keyboard()
        for child in self.content.get_children():
            self.content.remove(child)
        self.content.add(self.labels['main_box'])
        self.content.show_all()
        if "edit_config" in self.labels:
            del self.labels["edit_config"]
        self.show_add = False
        self.delay_reload_networks(500)

    def refresh_network_config_entries(self):
        self.config_refresh_timer_id = None

        if not self.show_add:
            return False

        info = self.sdbus_nm.get_wireless_connection_info()
        self.ip_entry.set_text(info.get("ip_address", "0.0.0.0"))
        self.netmask_entry.set_text(info.get("netmask", "255.255.255.0"))
        self.gateway_entry.set_text(info.get("gateway", ""))
        self.dns_entry.set_text(info.get("dns", ""))
        self.network_interface_refresh()
        return False

    def schedule_network_config_refresh(self, delay_ms=1500):
        if self.config_refresh_timer_id:
            GLib.source_remove(self.config_refresh_timer_id)
        self.config_refresh_timer_id = GLib.timeout_add(delay_ms, self.refresh_network_config_entries)

    def save_network_config_inline(self, widget):

        self._screen.remove_keyboard()

        is_dhcp = self.dhcp_switch.get_active()
        logging.info(f"Saving network config, DHCP={is_dhcp}")

        if is_dhcp:
            logging.info("Enabling DHCP for wireless")
            result = self.sdbus_nm.set_wireless_dhcp(True)
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
            result = self.sdbus_nm.set_wireless_manual(ip, netmask, gateway, dns_list)

        logging.info(f"Save result: {result}")
        if "error" in result:
            self._screen.show_popup_message(result.get("message", _("Failed to save configuration")))
        else:
            self.dhcp_switch.grab_focus()
            self._screen.show_popup_message(_("Configuration saved"), level=1)
            # Keep config page open when save is triggered automatically by DHCP toggle.
            if widget is not None:
                self.close_network_config()
            else:
                self.delay_reload_networks(500)
                self.schedule_network_config_refresh()

# -*- coding: utf-8 -*-
import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango
from jinja2 import Environment
from datetime import datetime
from math import log
from ks_includes.sdbus_nm import SdbusNm
from ks_includes.screen_panel import ScreenPanel


class BasePanel(ScreenPanel):
    def __init__(self, screen, title=None):
        super().__init__(screen, title)
        self.current_panel = None
        self.time_min = -1
        self.time_format = self._config.get_main_config().getboolean("24htime", True)
        self.time_update = None
        self.network_update = None
        self.titlebar_items = []
        self.titlebar_name_type = None
        self.current_extruder = None
        self.last_usage_report = datetime.now()
        self.usage_report = 0
        self.load_titlebar_icons()
        try:
            self.sdbus_nm = SdbusNm(self.network_interface_refresh)
        except Exception as e:
            logging.exception("Failed to initialize SdbusNm: %s", e)
            self.sdbus_nm = None
        # Action bar buttons
        abscale = self.bts * 1.1
        self.control['back'] = self._gtk.Button('back', scale=abscale)
        self.control['back'].connect("clicked", self.back)
        self.control['back'].set_no_show_all(True)
        self.control['home'] = self._gtk.Button('main', scale=abscale)
        self.control['home'].connect("clicked", self._screen._menu_go_back, True)
        self.control['home'].set_no_show_all(True)
        self.move = {
            "panel": "move",
        }
        self.control['move'] = self._gtk.Button('move', scale=abscale)
        self.control['move'].connect("clicked", self.menu_item_clicked, self.move)
        self.control['move'].set_no_show_all(True)
        self.extrude = {
            "panel": "extrude",
        }
        self.control['extrude'] = self._gtk.Button('filament', scale=abscale)
        self.control['extrude'].connect("clicked", self.menu_item_clicked, self.extrude)
        self.control['extrude'].set_no_show_all(True)

        self.files = {
            "panel": "gcodes",
        }
        self.control['files'] = self._gtk.Button('files', scale=abscale)
        self.control['files'].connect("clicked", self.menu_item_clicked, self.files)
        self.control['files'].set_no_show_all(True)
        self.more = {
            "panel": "more",
        }
        self.control['more'] = self._gtk.Button('settings', scale=abscale)
        self.control['more'].connect("clicked", self._screen._go_to_submenu, "more")
        self.control['more'].set_no_show_all(True)
        for control in self.control:
            self.set_control_sensitive(False, control)
        self.control['estop'] = self._gtk.Button('emergency', scale=abscale)
        self.control['estop'].connect("clicked", self.emergency_stop)
        self.control['estop'].set_no_show_all(True)
        self.control['printer_select'] = self._gtk.Button('shuffle', scale=abscale)
        self.control['printer_select'].connect("clicked", self._screen.show_printer_select)
        self.control['printer_select'].set_no_show_all(True)

        self.shorcut = {
            "panel": "gcode_macros",
            "icon": "custom-script",
        }

        # Any action bar button should close the keyboard
        for item in self.control:
            self.control[item].connect("clicked", self._screen.remove_keyboard)

        # Action bar
        self.action_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        if self._screen.vertical_mode:
            self.action_bar.set_hexpand(True)
            self.action_bar.set_vexpand(False)
        else:
            self.action_bar.set_hexpand(False)
            self.action_bar.set_vexpand(True)
        self.action_bar.get_style_context().add_class('action_bar')
        self.action_bar.add(self.control['back'])
        self.action_bar.add(self.control['home'])
        self.action_bar.add(self.control['move'])
        self.action_bar.add(self.control['extrude'])
        self.action_bar.add(self.control['files'])
        self.action_bar.add(self.control['more'])
        self.action_bar.add(self.control['printer_select'])
        self.action_bar.add(self.control['estop'])
        self.show_printer_select(len(self._config.get_printers()) > 1)

        # Titlebar

        # This box will be populated by show_heaters
        self.control['temp_box'] = Gtk.Box(spacing=10)

        self.titlelbl = Gtk.Label(hexpand=True, halign=Gtk.Align.CENTER, ellipsize=Pango.EllipsizeMode.END)

        if self._screen.license.is_interface_valid() and not self._screen.license.is_active():
            img_size = self._gtk.img_scale * self.bts
            self.control["license"] = self._gtk.Image("license", img_size, img_size)
            license_eventbox = Gtk.EventBox()
            license_eventbox.add(self.control["license"])
            license_eventbox.connect("button-press-event", self.show_license_key_page)
            self.control["license_box"] = Gtk.Box(halign=Gtk.Align.END)
            self.control["license_box"].pack_end(license_eventbox, True, True, 5)

        if self.sdbus_nm:
            img_size = self._gtk.img_scale * self.bts
            self.control["network_ico"] = self._gtk.Image("wifi_excellent", img_size, img_size)
            network_eventbox = Gtk.EventBox()
            network_eventbox.add(self.control["network_ico"])
            network_eventbox.connect("button-press-event", self.show_network_page)
            self.control["network_box"] = Gtk.Box(halign=Gtk.Align.END)
            self.control["network_box"].pack_end(network_eventbox, True, True, 5)
            self.control["network_ico"].set_no_show_all(True)
            self.control["network_ico"].set_visible(False)


        img_size = self._gtk.img_scale * self.bts
        self.control["cloud_ico"] = self._gtk.Image("cloud", img_size, img_size)
        cloud_eventbox = Gtk.EventBox()
        cloud_eventbox.add(self.control["cloud_ico"])
        cloud_eventbox.connect("button_press-event", self.show_creatcloud_page)
        self.control['cloud_box'] = Gtk.Box(halign=Gtk.Align.END)
        self.control["cloud_box"].pack_end(cloud_eventbox, True, True, 5)
        self.control["cloud_ico"].set_no_show_all(True)
        self.control["cloud_ico"].set_visible(False)
        self.control["cloud_ico"].set_sensitive(False)

        self.control['time'] = Gtk.Label(label="00:00 AM")
        self.control['time_box'] = Gtk.Box(halign=Gtk.Align.END)
        self.control['time_box'].pack_end(self.control['time'], True, True, 10)

        self.titlebar = Gtk.Box(spacing=5, valign=Gtk.Align.CENTER)
        self.titlebar.get_style_context().add_class("title_bar")
        self.titlebar.add(self.control['temp_box'])
        self.titlebar.add(self.titlelbl)
        if self._screen.license.is_interface_valid() and not self._screen.license.is_active():
            self.titlebar.add(self.control["license_box"])
        if self.sdbus_nm:
            self.titlebar.add(self.control["network_box"])
        self.titlebar.add(self.control["cloud_box"])
        self.titlebar.add(self.control['time_box'])
        self.set_title(title)

        # Main layout
        self.main_grid = Gtk.Grid()

        if self._screen.vertical_mode:
            self.main_grid.attach(self.titlebar, 0, 0, 1, 1)
            self.main_grid.attach(self.content, 0, 1, 1, 1)
            self.main_grid.attach(self.action_bar, 0, 2, 1, 1)
            self.action_bar.set_orientation(orientation=Gtk.Orientation.HORIZONTAL)
        else:
            self.main_grid.attach(self.action_bar, 0, 0, 1, 2)
            self.action_bar.set_orientation(orientation=Gtk.Orientation.VERTICAL)
            self.main_grid.attach(self.titlebar, 1, 0, 1, 1)
            self.main_grid.attach(self.content, 1, 1, 1, 1)

        self.update_time()

    def show_license_key_page(self, widget, event):
        if "license" not in self._screen._cur_panels:
            self._screen.show_panel("license", remove_all=False)

    def show_network_page(self, widget, event):
        if "network" not in self._screen._cur_panels:
            self._screen.show_panel("network", remove_all=False)

    def show_creatcloud_page(self, widget, event):
        if "creatcloud" not in self._screen._cur_panels:
            self._screen.show_panel("creatcloud", remove_all=False)

    def reload_icons(self):
        button: Gtk.Button
        for button in self.action_bar.get_children():
            img = button.get_image()
            name = button.get_name()
            pixbuf = img.get_pixbuf()
            width = pixbuf.get_width()
            height = pixbuf.get_height()
            button.set_image(self._gtk.Image(name, width, height))
        self.load_titlebar_icons()

    def show_heaters(self, show=True):
        try:
            for child in self.control['temp_box'].get_children():
                self.control['temp_box'].remove(child)
            devices = self._printer.get_temp_devices()
            if not show or not devices:
                return

            img_size = self._gtk.img_scale * self.bts
            for device in devices:
                self.labels[device] = Gtk.Label(ellipsize=Pango.EllipsizeMode.START)
                self.labels[f'{device}_box'] = Gtk.Box()
                icon = self.get_icon(device, img_size)
                if icon is not None:
                    self.labels[f'{device}_box'].pack_start(icon, False, False, 3)
                self.labels[f'{device}_box'].pack_start(self.labels[device], False, False, 0)

            # Limit the number of items according to resolution
            nlimit = int(round(log(self._screen.width, 10) * 5 - 10.5))
            n = 0
            if len(self._printer.get_tools()) > (nlimit - 1):
                self.current_extruder = self._printer.get_stat("toolhead", "extruder")
                if self.current_extruder and f"{self.current_extruder}_box" in self.labels:
                    self.control['temp_box'].add(self.labels[f"{self.current_extruder}_box"])
            else:
                self.current_extruder = False
            for device in devices:
                if n >= nlimit:
                    break
                if device.startswith("extruder") and self.current_extruder is False:
                    self.control['temp_box'].add(self.labels[f"{device}_box"])
                    n += 1
                elif device.startswith("heater"):
                    self.control['temp_box'].add(self.labels[f"{device}_box"])
                    n += 1
            for device in devices:
                # Users can fill the bar if they want
                if n >= nlimit + 1:
                    break
                name = device.split()[1] if len(device.split()) > 1 else device
                for item in self.titlebar_items:
                    if name == item:
                        self.control['temp_box'].add(self.labels[f"{device}_box"])
                        n += 1
                        break

            self.control['temp_box'].show_all()
        except Exception as e:
            logging.debug(f"Couldn't create heaters box: {e}")

    def get_icon(self, device, img_size):
        if device.startswith("extruder"):
            if self._printer.extrudercount > 1:
                if device == "extruder":
                    device = "extruder0"
                return self._gtk.Image(f"extruder-{device[8:]}", img_size, img_size)
            return self._gtk.Image("extruder", img_size, img_size)
        elif device.startswith("heater_bed"):
            return self._gtk.Image("bed", img_size, img_size)
        elif device.startswith("heater_generic chamber") or device.startswith("heater_chamber"):
            return self._gtk.Image("chamber", img_size, img_size)
        # Extra items
        elif self.titlebar_name_type is not None:
            # The item has a name, do not use an icon
            return None
        elif device.startswith("temperature_fan"):
            return self._gtk.Image("fan", img_size, img_size)
        elif device.startswith("heater_generic"):
            return self._gtk.Image("heater", img_size, img_size)
        else:
            return self._gtk.Image("heat-up", img_size, img_size)

    def activate(self):
        if self.time_update is None:
            self.time_update = GLib.timeout_add_seconds(1, self.update_time)
        if self.sdbus_nm and self.network_update is None:
            self.network_update = GLib.timeout_add_seconds(5, self.network_interface_refresh)

    def add_content(self, panel):
        printing = self._printer and self._printer.state in {"printing", "paused"}
        connected = self._printer and self._printer.state not in {'disconnected', 'startup', 'shutdown', 'error'}
        self.control['estop'].set_visible(printing)
        self.control['move'].set_visible(not printing and connected)
        self.control['extrude'].set_visible(not printing and connected)
        self.control['files'].set_visible(not printing and connected)
        self.control['more'].set_visible(not printing and connected)
        self.control['home'].set_visible(connected)
        self.show_shortcut(connected)
        self.show_heaters(connected)
        for control in ('back', 'home'):
            self.set_control_sensitive(len(self._screen._cur_panels) > 1, control=control)
        panels_has_back = ['gcodes', 'temperature']
        cur_panel_count = len(self._screen._cur_panels)
        is_last_panel_in_back_list = self._screen._cur_panels[-1] in panels_has_back

        should_show_back = (cur_panel_count > 2 or is_last_panel_in_back_list or
                    (self._screen._cur_panels[0] != 'main_menu' and cur_panel_count >= 2))
        self.control['back'].set_visible(should_show_back)
        if any(child.get_visible() for child in self.action_bar.get_children()):
            self.show_action_bar()
        else:
            self.hide_action_bar()

        self.current_panel = panel
        self.set_title(panel.title)
        self.content.add(panel.content)

    def back(self, widget=None):
        if self.current_panel is None:
            return
        self._screen.remove_keyboard()
        if hasattr(self.current_panel, "back") \
                and not self.current_panel.back() \
                or not hasattr(self.current_panel, "back"):
            self._screen._menu_go_back()

    def process_update(self, action, data):
        if action == "notify_proc_stat_update":
            cpu = data["system_cpu_usage"]["cpu"]
            memory = (data["system_memory"]["used"] / data["system_memory"]["total"]) * 100
            error = "message_popup_error"
            ctx = self.titlebar.get_style_context()
            msg = f"CPU: {cpu:2.0f}%    RAM: {memory:2.0f}%"
            if cpu > 80 or memory > 85:
                if self.usage_report < 3:
                    self.usage_report += 1
                    return
                self.last_usage_report = datetime.now()
                if not ctx.has_class(error):
                    ctx.add_class(error)
                self._screen.log_notification(f"{self._screen.connecting_to_printer}: {msg}", 2)
                self.titlelbl.set_label(msg)
            elif ctx.has_class(error):
                if (datetime.now() - self.last_usage_report).seconds < 5:
                    self.titlelbl.set_label(msg)
                    return
                self.usage_report = 0
                ctx.remove_class(error)
                self.titlelbl.set_label(f"{self._screen.connecting_to_printer}")
            return

        if action == "notify_update_response":
            if self.update_dialog is None:
                self.show_update_dialog()
            if 'message' in data:
                self.labels['update_progress'].set_text(
                    f"{self.labels['update_progress'].get_text().strip()}\n"
                    f"{data['message']}\n")
            if 'complete' in data and data['complete']:
                logging.info("Update complete")
                if self.update_dialog is not None:
                    try:
                        self.update_dialog.set_response_sensitive(Gtk.ResponseType.OK, True)
                        self.update_dialog.get_widget_for_response(Gtk.ResponseType.OK).show()
                    except AttributeError:
                        logging.error("error trying to show the updater button the dialog might be closed")
                        self._screen.updating = False
                        for dialog in self._screen.dialogs:
                            self._gtk.remove_dialog(dialog)
            return

        if action == "notify_creatcloud_info_update":
            self.refresh_creatcloud(data)
            return

        if action != "notify_status_update" or self._screen.printer is None:
            return
        for device in self._printer.get_temp_devices():
            temp = self._printer.get_stat(device, "temperature")
            if temp and device in self.labels:
                name = ""
                if not (device.startswith("extruder") or device.startswith("heater_bed")):
                    if self.titlebar_name_type == "full":
                        name = device.split()[1] if len(device.split()) > 1 else device
                        name = f'{self.prettify(name)}: '
                    elif self.titlebar_name_type == "short":
                        name = device.split()[1] if len(device.split()) > 1 else device
                        name = f"{name[:1].upper()}: "
                self.labels[device].set_label(f"{name}{temp:.0f}°")

        if (self.current_extruder and 'toolhead' in data and 'extruder' in data['toolhead']
                and data["toolhead"]["extruder"] != self.current_extruder):
            self.control['temp_box'].remove(self.labels[f"{self.current_extruder}_box"])
            self.current_extruder = data["toolhead"]["extruder"]
            self.control['temp_box'].pack_start(self.labels[f"{self.current_extruder}_box"], True, True, 3)
            self.control['temp_box'].reorder_child(self.labels[f"{self.current_extruder}_box"], 0)
            self.control['temp_box'].show_all()

        return False

    def remove(self, widget):
        self.content.remove(widget)

    def set_control_sensitive(self, value=True, control='home'):
        self.control[control].set_sensitive(value)

    def show_shortcut(self, show=True):
        show = (
            show
            and self._config.get_main_config().getboolean('side_macro_shortcut', True)
            and self._printer.get_printer_status_data()["printer"]["gcode_macros"]["count"] > 0
            and self._screen._cur_panels[-1] != 'printer_select'
        )
        self.set_control_sensitive(self._screen._cur_panels[-1] != self.shorcut['panel'])
        self.set_control_sensitive(self._screen._cur_panels[-1] != self.move['panel'], control='move')
        self.set_control_sensitive(self._screen._cur_panels[-1] != self.extrude['panel'], control='extrude')
        self.set_control_sensitive(self._screen._cur_panels[-1] != self.files['panel'], control='files')
        self.set_control_sensitive(self._screen._cur_panels[-1] != self.more['panel'], control='more')

    def show_action_bar(self):
        self.action_bar.set_size_request(self._gtk.action_bar_width, self._gtk.action_bar_height)
        self.control['home'].set_visible(True)

    def hide_action_bar(self):
        self.action_bar.set_size_request(-1, -1)
        self.control['home'].set_visible(False)

    def show_printer_select(self, show=True):
        self.control['printer_select'].set_visible(
            show and 'printer_select' not in self._screen._cur_panels
        )

    def set_title(self, title):
        self.titlebar.get_style_context().remove_class("message_popup_error")
        if not title:
            self.titlelbl.set_label(f"{self._screen.connecting_to_printer}")
            return
        try:
            env = Environment(extensions=["jinja2.ext.i18n"], autoescape=True)
            env.install_gettext_translations(self._config.get_lang())
            j2_temp = env.from_string(title)
            title = j2_temp.render()
        except Exception as e:
            logging.debug(f"Error parsing jinja for title: {title}\n{e}")

        title_text = f"{self._screen.connecting_to_printer} | {title}" if self._screen.connecting_to_printer is not None else title
        self.titlelbl.set_label(title_text)

    def refresh_creatcloud(self, data):
        if "actived" in data:
            self.control["cloud_ico"].set_visible(data["actived"])
            self.control["cloud_ico"].set_sensitive(False)
        if "online" in data:
            self.control["cloud_ico"].set_sensitive(data["online"])

    def update_time(self):
        now = datetime.now()
        confopt = self._config.get_main_config().getboolean("24htime", True)
        if now.minute != self.time_min or self.time_format != confopt:
            if confopt:
                self.control['time'].set_text(f'{now:%H:%M }')
            else:
                self.control['time'].set_text(f'{now:%I:%M %p}')
            self.time_min = now.minute
            self.time_format = confopt
        return True

    def network_interface_refresh(self, msg=None, level=3):
        if self.sdbus_nm:
            self.interface = self.sdbus_nm.get_primary_interface()
            if self.interface:
                if '?' not in self.sdbus_nm.get_ip_address(): 
                    if self.interface == "eth0":
                        self.control["network_ico"].set_from_pixbuf(self.network_icons["ethernet"])
                        self.control["network_ico"].set_visible(True)
                    elif self.interface == "wlan0":
                        strength = self.sdbus_nm.get_signal_strength()
                        if strength:
                            self.control["network_ico"].set_from_pixbuf(self.get_signal_strength_icon(strength))
                            self.control["network_ico"].set_visible(True)
                        else:
                            self.control["network_ico"].set_visible(False)
                else:
                    self.control["network_ico"].set_visible(False)
        return True

    def get_signal_strength_icon(self, signal_level):
        if signal_level > 75:
            return self.network_icons["excellent"]
        elif signal_level > 60:
            return self.network_icons["good"]
        elif signal_level > 30:
            return self.network_icons["fair"]
        else:
            return self.network_icons["weak"]

    def load_titlebar_icons(self):
        icon_size_width = self._gtk.content_width * 0.05
        icon_size_height = self._gtk.content_height * 0.05
        network_icons_map = {
            "excellent": "wifi_excellent",
            "good": "wifi_good",
            "fair": "wifi_fair",
            "weak": "wifi_weak",
            "ethernet": "ethernet",
        }
        self.network_icons = {
            key: self._gtk.PixbufFromIcon(value, width=icon_size_width, height=icon_size_height)
            for key, value in network_icons_map.items()
        }
        if self.control:
            img_size = self._gtk.img_scale * self.bts
            cloud_buf = self._gtk.PixbufFromIcon("cloud", img_size, img_size)
            self.control["cloud_ico"].set_from_pixbuf(cloud_buf)

    def set_ks_printer_cfg(self, printer):
        ScreenPanel.ks_printer_cfg = self._config.get_printer_config(printer)
        if self.ks_printer_cfg is not None:
            self.titlebar_name_type = self.ks_printer_cfg.get("titlebar_name_type", None)
            titlebar_items = self.ks_printer_cfg.get("titlebar_items", None)
            if titlebar_items is not None:
                self.titlebar_items = [str(i.strip()) for i in titlebar_items.split(',')]
                logging.info(f"Titlebar name type: {self.titlebar_name_type} items: {self.titlebar_items}")
            else:
                self.titlebar_items = []

    def show_update_dialog(self):
        if self.update_dialog is not None:
            return
        button = [{"name": _("Finish"), "response": Gtk.ResponseType.OK}]
        self.labels['update_progress'] = Gtk.Label(hexpand=True, vexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.labels['update_scroll'] = self._gtk.ScrolledWindow(steppers=False)
        self.labels['update_scroll'].set_property("overlay-scrolling", True)
        self.labels['update_scroll'].add(self.labels['update_progress'])
        self.labels['update_scroll'].connect("size-allocate", self._autoscroll)
        dialog = self._gtk.Dialog(_("Updating"), button, self.labels['update_scroll'], self.finish_updating)
        dialog.connect("delete-event", self.close_update_dialog)
        dialog.set_response_sensitive(Gtk.ResponseType.OK, False)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).hide()
        self.update_dialog = dialog
        self._screen.updating = True

    def finish_updating(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
            return
        logging.info("Finishing update")
        self._screen.updating = False
        self._gtk.remove_dialog(dialog)
        self._screen._menu_go_back(home=True)

    def close_update_dialog(self, *args):
        logging.info("Closing update dialog")
        if self.update_dialog in self._screen.dialogs:
            self._screen.dialogs.remove(self.update_dialog)
        self.update_dialog = None
        self._screen._menu_go_back(home=True)

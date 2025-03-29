import configparser
import logging
import os.path
import pathlib

import gi

gi.require_version("Gtk", "3.0")
from datetime import datetime

from gi.repository import GLib, Gtk

from ks_includes.KlippyFactory import KlippyFactory
from ks_includes.ModelConfig import ModelConfig
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or "factory settings"
        super().__init__(screen, title)
        klipperscreendir = pathlib.Path(__file__).parent.resolve().parent
        self.model_list_path = os.path.join(klipperscreendir, "config", "model_menu.conf")
        self.model_list_config = configparser.ConfigParser()
        self.model_list_config.read(self.model_list_path, encoding="utf-8")
        self.last_drop_time = datetime.now()
        self.factory_settings_list = [
            {
                "Select Model": {
                    "section": "main",
                    "name": _("Select Model"),
                    "type": "button",
                    "callback": self.show_select_model,
                }
            },
            {
                "Enable Guide": {
                    "section": "main",
                    "name": _("Pack"),
                    "type": "button",
                    "callback": self.reset_factory_settings,
                }
            },
            {
                "License key": {
                    "section": "main",
                    "name": _("License key"),
                    "type": "button",
                    "callback": self.license_key,
                }
            },
            {
                "version_info": {
                    "section": "main",
                    "name": _("Version Selection"),
                    "type": "dropdown",
                    "value": "stable",
                    "callback": self.version_selection,
                    "options": [
                        {"name": _("Stable") + " " + _("(default)"), "value": "stable"},
                        {"name": _("Beta"), "value": "beta"},
                        {"name": _("Dev"), "value": "dev"},
                    ],
                }
            },
        ]
        self.settings = {}
        self.select_model = False
        self.select_model_version = False
        self.labels["setting_menu"] = self._gtk.ScrolledWindow()
        self.labels["settings"] = Gtk.Grid()
        self.labels["setting_menu"].add(self.labels["settings"])
        self.option_res = {}
        for option in self.factory_settings_list:
            name = list(option)[0]
            self.option_res.update(self.add_option("settings", self.settings, name, option[name]))

        version_dropdown = self.option_res.get("version_info")
        version_dropdown.connect("notify::popup-shown", self.on_popup_shown)

        self.content.add(self.labels["setting_menu"])
        self.content.show_all()

    def back(self):
        if self.select_model_version:
            self.hide_select_model_version()
            return True
        if self.select_model:
            self.hide_select_model()
            return True
        return False

    def on_popup_shown(self, combo_box, param):
        if combo_box.get_property("popup-shown"):
            logging.debug("Dropdown popup show")
            self.last_drop_time = datetime.now()
        else:
            elapsed = (datetime.now() - self.last_drop_time).total_seconds()
            if elapsed < 0.2:
                logging.debug(f"Dropdown closed too fast ({elapsed}s)")
                GLib.timeout_add(50, lambda: self.dropdown_keep_open(combo_box))
                return
            logging.debug("Dropdown popup close")

    def dropdown_keep_open(self, combo_box):
        if isinstance(combo_box, Gtk.ComboBox):
            combo_box.popup()
        return False

    def create_list_menu(self, menu_list, callback=None):
        if "model_menu" in self.labels:
            del self.labels["model_menu"]
        self.labels["model_menu"] = self._gtk.ScrolledWindow()
        self.labels["model"] = Gtk.Grid()
        self.labels["model_menu"].add(self.labels["model"])
        self.models = {}
        for value in menu_list:
            self.models[value] = {
                "name": value,
                "type": "button",
                "callback": callback,
            }
            self.add_option("model", self.models, value, self.models[value])

    def show_select_model(self, widget=None, option=None):
        self.create_list_menu(self.model_list_config.sections(), self._on_model_selected)
        for child in self.content.get_children():
            self.content.remove(child)
        self.content.add(self.labels["model_menu"])
        self.content.show_all()
        self.select_model = True

    def show_select_model_version(self, model):
        versions_str = self.model_list_config[model].get("versions", "")
        versions = [v.strip() for v in versions_str.split(",") if v.strip()]
        self.create_list_menu(versions, self._on_version_selected)
        self.select_model_version = True

    def _on_model_selected(self, widget, event):
        for child in self.content.get_children():
            self.content.remove(child)
        self.show_select_model_version(event)
        self.content.add(self.labels["model_menu"])
        self.content.show_all()

    def _on_version_selected(self, widget, version):
        if not hasattr(self, "model_config") or self.model_config is None:
            self.model_config = ModelConfig()
            self.model_config.generate_config(self.select_model, version)

    def hide_select_model_version(self):
        for child in self.content.get_children():
            self.content.remove(child)
        self.show_select_model()
        self.select_model_version = False

    def hide_select_model(self):
        for child in self.content.get_children():
            self.content.remove(child)
        if "setting_menu" in self.labels:
            self.content.add(self.labels["setting_menu"])
            self.content.show_all()
        self.select_model = False

    def license_key(self, *args):
        self._screen.show_panel("license", title="license", remove_all=False, full=True)

    def reset_factory_settings(self, *args):
        buttons = [
            {"name": _("Accept"), "response": Gtk.ResponseType.OK, "style": "dialog-error"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-info"},
        ]

        text = _("Are you sure?\n") + "\n\n" + _("The system will reboot!")
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(text)
        label.set_margin_top(100)

        checkbox = Gtk.CheckButton(label=" " + _("Enable Registration Code"))
        checkbox.set_halign(Gtk.Align.CENTER)
        checkbox.set_valign(Gtk.Align.CENTER)

        grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        grid.set_row_spacing(20)
        grid.set_column_spacing(0)
        grid.attach(label, 0, 0, 1, 1)
        if self._screen.license.is_interface_valid() and self._screen.license.is_active():
            grid.attach(checkbox, 0, 1, 1, 1)

        self._gtk.Dialog(
            _("factory settings"),
            buttons,
            grid,
            self.confirm_factory_reset_production,
            checkbox,
        )

    def confirm_factory_reset_production(self, dialog, response_id, checkbox):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            if checkbox.get_active():
                if self._screen.license.is_interface_valid():
                    self._screen.license.enabled_registration()
            KlippyFactory.production_factory_reset(self._screen._ws.klippy, self._config)

    def version_selection(self, val):
        config_updater = ConfigMoonrakerUpdateManager()
        config_updater.enable_version_selection(val)
        if val == "stable":
            self._screen._send_action(None, "machine.update.rollback", {"name": "klipper"})
            self._screen._send_action(None, "machine.update.rollback", {"name": "KlipperScreen"})
            self._screen._send_action(None, "machine.update.rollback", {"name": "moonraker"})
        else:
            self._screen._send_action(None, "machine.services.restart", {"service": "moonraker"})
        logging.info(f"version selection:{val}")

class ConfigMoonrakerUpdateManager:
    def __init__(self):
        self.moonraker_config = configparser.ConfigParser()
        self.moonraker_config_path = "/home/klipper/printer_data/config/moonraker.conf"

    def _set_update_manager_channel(self, section, channel="dev"):
        if not self.moonraker_config.has_section(section):
            self.moonraker_config.add_section(section)
        self.moonraker_config.set(section, "channel", channel)

    def enable_version_selection(self, val):
        update_managet_list = ["update_manager", "update_manager klipper", "update_manager KlipperScreen"]
        try:
            self.moonraker_config.read(self.moonraker_config_path)

            if "dev" == val or "beta" == val:
                for section in update_managet_list:
                    self._set_update_manager_channel(section, val)
            else:
                for section in update_managet_list:
                    self.moonraker_config.remove_section(section)

            with open(self.moonraker_config_path, "w") as configfile:
                self.moonraker_config.write(configfile)
        except Exception as e:
            msg = f"Error reading or writing config: \n{e}"
            logging.exception(msg)

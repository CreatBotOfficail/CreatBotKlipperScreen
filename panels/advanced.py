import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from ks_includes.KlippyFactory import KlippyFactory
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from datetime import datetime


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Advanced")
        super().__init__(screen, title)
        self.last_drop_time = datetime.now()
        self.advanced = {}
        self.menu_list = {}
        self.advanced_options = [
            {
                "adaptive_leveling": {
                    "section": "main",
                    "name": _("Auto Bed Leveling"),
                    "type": "binary",
                    "tooltip": _("Automatic compensation based on the data of the bed mesh"),
                    "value": "False",
                    "callback": self.set_adaptive_leveling,
                }
            },
            {
                "power_loss_recovery": {
                    "section": "main",
                    "name": _("Power Loss Recovery"),
                    "type": "binary",
                    "tooltip": _("Restores your print job after a power outage"),
                    "value": "True",
                    "callback": self.set_power_loss_recovery,
                }
            },
            {
                "auto_change_nozzle": {
                    "section": "main",
                    "name": _("Auto Change Nozzle"),
                    "type": "binary",
                    "tooltip": _("Auto change nozzle when filament runout")
                    + _("(Disable during dual extrusion printing)"),
                    "value": "False",
                    "callback": self.set_auto_change_nozzle,
                }
            },
            {
                "factory_settings": {
                    "section": "main",
                    "name": _("Restore Factory Settings"),
                    "type": "button",
                    "tooltip": _("This operation will clear the user data"),
                    "value": "True",
                    "callback": self.reset_factory_settings,
                }
            },
        ]
        if self._printer.get_macro("_door_detection"):
            self.advanced_options.append(
                {
                    "door_open_detection": {
                        "section": "main",
                        "name": _("Door Open Protection Mode"),
                        "type": "dropdown",
                        "tooltip": _(
                            "This feature allows you to customize the printer's response when door opening is detected"
                        ),
                        "value": "Disabled",
                        "callback": self.door_open_detection,
                        "options": [
                            {"name": _("Disabled") + " " + _("(default)"), "value": "Disabled"},
                            {"name": _("Pause Print"), "value": "Pause Print"},
                            {"name": _("Emergency Stop"), "value": "Emergency Stop"},
                        ],
                    }
                }
            )

        options = self.advanced_options
        self.labels["advanced_menu"] = self._gtk.ScrolledWindow()
        self.labels["advanced"] = Gtk.Grid()
        self.labels["advanced_menu"].add(self.labels["advanced"])
        for option in options:
            name = list(option)[0]
            res = self.add_option("advanced", self.advanced, name, option[name])
            self.menu_list.update(res)
        self.content.add(self.labels["advanced_menu"])

        if "door_open_detection" in self.menu_list:
            self.menu_list["door_open_detection"].connect("notify::popup-shown", self.on_popup_shown)

    def reset_factory_settings(self, *args):
        text = _("Confirm factory reset?\n") + "\n\n" + _("The system will reboot!")
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(text)
        label.set_margin_top(100)

        clear_files_checkbox = Gtk.CheckButton(label=" " + _("Clear Internal G-code Files"))
        clear_files_checkbox.set_halign(Gtk.Align.CENTER)
        clear_files_checkbox.set_valign(Gtk.Align.CENTER)

        buttons = [
            {
                "name": _("Accept"),
                "response": Gtk.ResponseType.OK,
                "style": "dialog-error",
            },
            {
                "name": _("Cancel"),
                "response": Gtk.ResponseType.CANCEL,
                "style": "dialog-info",
            },
        ]

        grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        grid.set_row_spacing(20)
        grid.set_column_spacing(0)
        grid.attach(label, 0, 0, 1, 1)
        grid.attach(clear_files_checkbox, 0, 1, 1, 1)

        self._gtk.Dialog(
            _("factory settings"),
            buttons,
            grid,
            self.confirm_reset_factory_settings,
            clear_files_checkbox,
        )

    def confirm_reset_factory_settings(self, dialog, response_id, clear_files_checkbox):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            KlippyFactory.user_factory_reset(self._screen._ws.klippy, self._config, clear_files_checkbox.get_active())

    def on_popup_shown(self, combo_box, param):
        if combo_box.get_property("popup-shown"):
            logging.debug("Dropdown popup show")
            self.last_drop_time = datetime.now()
        else:
            elapsed = (datetime.now() - self.last_drop_time).total_seconds()
            if elapsed < 0.1:
                logging.debug(f"Dropdown closed too fast ({elapsed}s)")
                GLib.timeout_add(50, lambda: self.dropdown_keep_open(combo_box))
                return
            logging.debug("Dropdown popup close")

    def dropdown_keep_open(self, combo_box):
        if isinstance(combo_box, Gtk.ComboBox):
            combo_box.popup()
        return False

    def door_open_detection(self, str):
        self.set_configuration_string("door_detect", str)

    def set_adaptive_leveling(self, *args):
        self.set_configuration_feature("adaptive_meshing", *args)

    def set_power_loss_recovery(self, *args):
        self.set_configuration_feature("power_loss_recovery", *args)

    def set_auto_change_nozzle(self, *args):
        self.set_configuration_feature("auto_change_nozzle", *args)

    def set_configuration_string(self, feature_name, str):
        script = KlippyGcodes.set_save_variables(feature_name, str)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set {feature_name}: {str}")

    def set_configuration_feature(self, feature_name, *args):
        enable_feature = any(args)
        script_value = True if enable_feature else False
        script = KlippyGcodes.set_save_variables(feature_name, script_value)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set {feature_name}: {script_value}")

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        if "save_variables" in data and "variables" in data["save_variables"]:
            variables = data["save_variables"]["variables"]
            if "adaptive_meshing" in variables:
                self.menu_list["adaptive_leveling"].set_active(variables["adaptive_meshing"])
            else:
                self.menu_list["adaptive_leveling"].set_active(False)

            if "power_loss_recovery" in variables:
                self.menu_list["power_loss_recovery"].set_active(variables["power_loss_recovery"])
            if "auto_change_nozzle" in variables:
                self.menu_list["auto_change_nozzle"].set_active(variables["auto_change_nozzle"])
            else:
                self.menu_list["auto_change_nozzle"].set_active(False)

            if self._printer.get_macro("_door_detection"):
                if "door_detect" in variables:
                    model = self.menu_list["door_open_detection"].get_model()
                    for i, row in enumerate(model):
                        if row[0] == _(variables["door_detect"]):
                            self.menu_list["door_open_detection"].set_active(i)

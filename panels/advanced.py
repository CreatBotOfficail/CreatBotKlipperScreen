import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.KlippyFactory import KlippyFactory
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Advanced")
        super().__init__(screen, title)
        self.advanced = {}
        self.menu_list = {}
        self.advanced_options = [
            {
                "adaptive_leveling": {
                    "section": "main",
                    "name": _("Adaptive Bed Leveling"),
                    "type": "binary",
                    "tooltip": _("Leveling Only in the Actual Print Area"),
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
                    "tooltip": _("Auto change nozzle when filament runout"),
                    "value": "False",
                    "callback": self.set_auto_change_nozzle,
                }
            },
            {
                "factory_settings": {
                    "section": "main",
                    "name": _("Restore factory settings"),
                    "type": "button",
                    "tooltip": _("This operation will clear the user data"),
                    "value": "True",
                    "callback": self.reset_factory_settings,
                }
            },
        ]
        options = self.advanced_options
        self.labels["advanced_menu"] = self._gtk.ScrolledWindow()
        self.labels["advanced"] = Gtk.Grid()
        self.labels["advanced_menu"].add(self.labels["advanced"])
        for option in options:
            name = list(option)[0]
            res = self.add_option("advanced", self.advanced, name, option[name])
            self.menu_list.update(res)
        self.content.add(self.labels["advanced_menu"])

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

    def set_adaptive_leveling(self, *args):
        self.set_configuration_feature("adaptive_meshing", *args)

    def set_power_loss_recovery(self, *args):
        self.set_configuration_feature("power_loss_recovery", *args)

    def set_auto_change_nozzle(self, *args):
        self.set_configuration_feature("auto_change_nozzle", *args)

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

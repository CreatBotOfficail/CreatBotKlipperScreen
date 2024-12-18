import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Advanced")
        super().__init__(screen, title)
        self.advanced = {}
        self.menu_list ={}
        self.advanced_options = [
            {"adaptive_leveling": {"section": "main", "name": _("Adaptive Bed Leveling"), "type": "binary",
                               "tooltip": _("Leveling Only in the Actual Print Area"),
                               "value": "False", "callback": self.set_adaptive_leveling}},
            {"power_loss_recovery": {"section": "main", "name": _("Power Loss Recovery"), "type": "binary",
                               "tooltip": _("Restores your print job after a power outage"),
                               "value": "True", "callback": self.set_power_loss_recovery}},
            {"auto_change_nozzle": {"section": "main", "name": _("Auto Change Nozzle"), "type": "binary",
                               "tooltip": _("Auto change nozzle when filament runout"),
                               "value": "False", "callback": self.set_auto_change_nozzle}},
        ]
        options = self.advanced_options
        self.labels['advanced_menu'] = self._gtk.ScrolledWindow()
        self.labels['advanced'] = Gtk.Grid()
        self.labels['advanced_menu'].add(self.labels['advanced'])
        for option in options:
            name = list(option)[0]
            res = self.add_option('advanced', self.advanced, name, option[name])
            self.menu_list.update(res)
        self.content.add(self.labels['advanced_menu'])

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
        if 'save_variables' in data and 'variables' in data['save_variables']:
            variables = data['save_variables']['variables']
            if 'adaptive_meshing' in variables:
                self.menu_list['adaptive_leveling'].set_active(variables['adaptive_meshing'])
            else:
                self.menu_list["adaptive_leveling"].set_active(False)

            if 'power_loss_recovery' in variables:
                self.menu_list['power_loss_recovery'].set_active(variables['power_loss_recovery'])
            if 'auto_change_nozzle' in variables:
                self.menu_list['auto_change_nozzle'].set_active(variables['auto_change_nozzle'])
            else:
                self.menu_list["auto_change_nozzle"].set_active(False)

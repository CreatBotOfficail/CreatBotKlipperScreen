import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Move setting")
        super().__init__(screen, title)
        printer_cfg = self._printer.get_config_section("printer")
        max_velocity = max(int(float(printer_cfg["max_velocity"])), 2)
        if "max_z_velocity" in printer_cfg:
            self.max_z_velocity = max(int(float(printer_cfg["max_z_velocity"])), 2)
        else:
            self.max_z_velocity = max_velocity

        self.settings = {}
        configurable_options = [
            {
                "move_speed_xy": {
                    "section": "main",
                    "name": _("XY Speed (mm/s)"),
                    "type": "scale",
                    "tooltip": _("Only for the move panel"),
                    "value": "50",
                    "range": [1, max_velocity],
                    "step": 1,
                }
            },
            {
                "move_speed_z": {
                    "section": "main",
                    "name": _("Z Speed (mm/s)"),
                    "type": "scale",
                    "tooltip": _("Only for the move panel"),
                    "value": "10",
                    "range": [1, self.max_z_velocity],
                    "step": 1,
                }
            },
        ]

        self.labels["options_menu"] = self._gtk.ScrolledWindow()
        self.labels["options"] = Gtk.Grid()
        self.labels["options_menu"].add(self.labels["options"])
        self.options = {}
        for option in configurable_options:
            name = list(option)[0]
            self.options.update(self.add_option("options", self.settings, name, option[name]))

        self.content.add(self.labels["options_menu"])
        self.content.show_all()


def process_update(self, action, data):
    if action != "notify_status_update":
        return

    if "toolhead" in data and "max_velocity" in data["toolhead"]:
        max_vel = max(int(float(data["toolhead"]["max_velocity"])), 2)
        adj = self.options["move_speed_xy"].get_adjustment()
        adj.set_upper(max_vel)

import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from contextlib import suppress
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.keypad import Keypad


class Panel(ScreenPanel):

    def __init__(self, screen, title, extra=None):
        title = title or _("Numpad")
        super().__init__(screen, title)
        self.panel = None
        self.active_heater = None
        self.grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        self.labels["keypad"] = Keypad(
            self._screen, self.change_target_temp, self.pid_calibrate, self.hide_numpad
        )
        self.content.add(self.grid)

        number_pad = self.create_number_pad_panel(extra)

        if self._screen.vertical_mode:
            self.grid.attach(number_pad, 0, 0, 1, 1)
        else:
            self.grid.attach(number_pad, 0, 0, 1, 1)

    def create_number_pad_panel(self, extra):

        num_panel = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        if self._screen.vertical_mode:
            self.labels["keypad"].set_halign(Gtk.Align.CENTER)
            self.labels["keypad"].set_valign(Gtk.Align.CENTER)
            self.labels["keypad"].set_size_request(
                self._screen.width / 5 * 4, self._screen.height / 5 * 3
            )
            num_panel.attach(self.labels["keypad"], 0, 0, 1, 1)
        else:
            self.labels["keypad"].set_valign(Gtk.Align.CENTER)
            self.labels["keypad"].set_halign(Gtk.Align.CENTER)
            self.labels["keypad"].set_size_request(
                max(self._screen.width / 5 * 2, 400),
                max(self._screen.height / 5 * 4, 420),
            )
            num_panel.attach(self.labels["keypad"], 0, 0, 1, 1)

        return num_panel

    def active_refresh(self, extra):
        self.labels["keypad"].clear()
        self.active_heater = extra
        can_pid = (
            self._printer.state not in ("printing", "paused")
            and self._screen.printer.config[self.active_heater]["control"] == "pid"
        )
        self.labels["keypad"].show_pid(can_pid)
        self.numpad_visible = True
        self._screen.base_panel.set_control_sensitive(True, control="back")

    def change_target_temp(self, temp):
        name = (
            self.active_heater.split()[1]
            if len(self.active_heater.split()) > 1
            else self.active_heater
        )
        temp = self.verify_max_temp(temp)
        if temp is False:
            return

        if self.active_heater.startswith("extruder"):
            self._screen._ws.klippy.set_tool_temp(
                self._printer.get_tool_number(self.active_heater), temp
            )
        elif self.active_heater == "heater_bed":
            self._screen._ws.klippy.set_bed_temp(temp)
        elif self.active_heater == "heater_chamber" or self.active_heater == "heater_filament_chamber":
            self._screen._ws.klippy.set_heater_temp(name, temp)
        elif self.active_heater.startswith("heater_generic "):
            self._screen._ws.klippy.set_heater_temp(name, temp)
        elif self.active_heater.startswith("temperature_fan "):
            self._screen._ws.klippy.set_temp_fan_temp(name, temp)
        else:
            logging.info(f"Unknown heater: {self.active_heater}")
            self._screen.show_popup_message(
                _("Unknown Heater") + " " + self.active_heater
            )
        self.hide_numpad()

    def pid_calibrate(self, temp):
        heater = self.active_heater.split(' ', maxsplit=1)[-1]
        if self.verify_max_temp(temp):
            script = {
                "script": f"PID_CALIBRATE HEATER={heater} TARGET={temp}"
            }
            self._screen._confirm_send_action(
                None,
                _("Initiate a PID calibration for:")
                + f" {heater} @ {temp} ºC"
                + "\n\n"
                + _("It may take more than 5 minutes depending on the heater power."),
                "printer.gcode.script",
                script,
            )
        self.hide_numpad()

    def verify_max_temp(self, temp):
        temp = int(temp)
        max_temp = int(
            float(self._printer.get_config_section(self.active_heater)["max_temp"])
        )
        logging.debug(f"{temp}/{max_temp}")
        if temp > max_temp:
            self._screen.show_popup_message(
                _("Can't set above the maximum:") + f" {max_temp}"
            )
            return False
        return max(temp, 0)

    def hide_numpad(self, widget=None):
        self.numpad_visible = False
        self._screen._menu_go_back()

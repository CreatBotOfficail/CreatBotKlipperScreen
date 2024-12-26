import re
import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    distances = [".01", ".05", "0.1"]
    distance = distances[-2]

    def __init__(self, screen, title):
        title = title or _("offset fine tune")
        super().__init__(screen, title)

        self.state = "standby"

        if self.ks_printer_cfg is not None:
            dis = self.ks_printer_cfg.get("move_distances", "")
            if re.match(r"^[0-9,\.\s]+$", dis):
                dis = [str(i.strip()) for i in dis.split(",")]
                if 1 < len(dis) <= 7:
                    self.distances = dis
                    self.distance = self.distances[-2]

        self.labels["qr_code_box"] = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        qr_code = self._gtk.Image("wiki_qr_code", self._gtk.content_width * 0.46, self._gtk.content_height * 0.46)
        qr_code_url = Gtk.Label(label="https://www.creatbot.com/en/faqs.html")
        self.labels["qr_code_box"].attach(qr_code, 0, 0, 1, 3)
        self.labels["qr_code_box"].attach(qr_code_url, 0, 2, 1, 1)

        self.action_btn = {}
        self.action_btn["fine_tune"] = self._gtk.Button("fine-tune", scale=0.7)
        self.action_btn["pause"] = self._gtk.Button("pause", scale=0.8)
        self.action_btn["resume"] = self._gtk.Button("resume", scale=0.8)
        self.action_btn["stop"] = self._gtk.Button("stop", scale=0.8)

        self.action_btn["fine_tune"].connect("clicked", self.menu_item_clicked, {"panel": "fine_tune"})
        self.action_btn["pause"].connect("clicked", self.pause)
        self.action_btn["resume"].connect("clicked", self.resume)
        self.action_btn["stop"].connect("clicked", self.cancel)

        self.labels["action_menu"] = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        self.labels["action_menu"].attach(self.action_btn["pause"], 0, 0, 1, 1)
        self.labels["action_menu"].attach(self.action_btn["stop"], 1, 0, 1, 1)
        self.labels["action_menu"].attach(self.action_btn["fine_tune"], 2, 0, 1, 1)

        self.buttons = {
            "x+": self._gtk.Button("arrow-right", "X+", "color1"),
            "x-": self._gtk.Button("arrow-left", "X-", "color1"),
            "y+": self._gtk.Button("arrow-up", "Y+", "color2"),
            "y-": self._gtk.Button("arrow-down", "Y-", "color2"),
            "z+": self._gtk.Button("z-farther", "Z+", "color3"),
            "z-": self._gtk.Button("z-closer", "Z-", "color3"),
        }
        self.buttons["x+"].connect("clicked", self.move, "X", "+")
        self.buttons["x-"].connect("clicked", self.move, "X", "-")
        self.buttons["y+"].connect("clicked", self.move, "Y", "+")
        self.buttons["y-"].connect("clicked", self.move, "Y", "-")
        self.buttons["z+"].connect("clicked", self.move, "Z", "+")
        self.buttons["z-"].connect("clicked", self.move, "Z", "-")

        grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        if self._screen.vertical_mode:
            if self._screen.lang_ltr:
                grid.attach(self.buttons["x+"], 2, 1, 1, 1)
                grid.attach(self.buttons["x-"], 0, 1, 1, 1)
                grid.attach(self.buttons["z+"], 2, 2, 1, 1)
                grid.attach(self.buttons["z-"], 0, 2, 1, 1)
            else:
                grid.attach(self.buttons["x+"], 0, 1, 1, 1)
                grid.attach(self.buttons["x-"], 2, 1, 1, 1)
                grid.attach(self.buttons["z+"], 0, 2, 1, 1)
                grid.attach(self.buttons["z-"], 2, 2, 1, 1)

            grid.attach(self.buttons["y+"], 1, 0, 1, 1)
            grid.attach(self.buttons["y-"], 1, 2, 1, 1)

        else:
            if self._screen.lang_ltr:
                grid.attach(self.buttons["x+"], 2, 1, 1, 1)
                grid.attach(self.buttons["x-"], 0, 1, 1, 1)
            else:
                grid.attach(self.buttons["x+"], 0, 1, 1, 1)
                grid.attach(self.buttons["x-"], 2, 1, 1, 1)
            grid.attach(self.buttons["y+"], 1, 0, 1, 1)
            grid.attach(self.buttons["y-"], 1, 2, 1, 1)
            grid.attach(self.buttons["z-"], 3, 0, 1, 1)
            grid.attach(self.buttons["z+"], 3, 2, 1, 1)

        distgrid = Gtk.Grid()
        for j, i in enumerate(self.distances):
            self.labels[i] = self._gtk.Button(label=i)
            self.labels[i].set_direction(Gtk.TextDirection.LTR)
            self.labels[i].connect("clicked", self.change_distance, i)
            ctx = self.labels[i].get_style_context()
            ctx.add_class("horizontal_togglebuttons")
            if i == self.distance:
                ctx.add_class("horizontal_togglebuttons_active")
            distgrid.attach(self.labels[i], j, 0, 1, 1)

        for p in ("x_offset_val", "y_offset_val", "z_offset_val"):
            self.labels[p] = Gtk.Label(f"{p[0].upper()} " + _("Offset") + "\n" + "0")
            self.labels[p].set_justify(Gtk.Justification.CENTER)
            self.labels[p].set_line_wrap(True)
        self.labels["move_dist"] = Gtk.Label(label=_("Move Distance (mm)"))

        bottomgrid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        bottomgrid.set_direction(Gtk.TextDirection.LTR)
        bottomgrid.attach(self.labels["x_offset_val"], 0, 0, 1, 1)
        bottomgrid.attach(self.labels["y_offset_val"], 1, 0, 1, 1)
        bottomgrid.attach(self.labels["z_offset_val"], 2, 0, 1, 1)
        bottomgrid.attach(self.labels["move_dist"], 0, 1, 3, 1)

        self.labels["move_menu"] = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        self.labels["move_menu"].attach(self.labels["qr_code_box"], 0, 0, 2, 4)
        self.labels["move_menu"].attach(grid, 2, 0, 2, 3)
        self.labels["move_menu"].attach(bottomgrid, 2, 3, 2, 1)
        self.labels["move_menu"].attach(distgrid, 2, 4, 2, 1)
        self.labels["move_menu"].attach(self.labels["action_menu"], 0, 4, 2, 1)

        self.content.add(self.labels["move_menu"])

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        if "save_variables" in data and "variables" in data["save_variables"]:
            variables = data["save_variables"]["variables"]
            nozzle_offsets = ["nozzle_z_offset_val", "nozzle_x_offset_val", "nozzle_y_offset_val"]

            for offset in nozzle_offsets:
                if offset in variables:
                    axis = offset.split("_")[1]
                    self.labels[f"{axis}_offset_val"].set_text(
                        f"{axis.upper()} " + _("Offset") + "\n" + f"{variables[offset]}"
                    )
        if "print_stats" in data:
            if "state" in data["print_stats"]:
                self.state = data["print_stats"]["state"]
                self.show_buttons_for_state()

    def pause(self, widget):
        self.disable_button("pause")
        self._screen._ws.klippy.print_pause()
        self._screen.show_all()

    def resume(self, widget):
        self.disable_button("resume")
        self._screen._ws.klippy.print_resume()
        self._screen.show_all()

    def cancel(self, widget):
        buttons = [
            {"name": _("Cancel Print"), "response": Gtk.ResponseType.OK, "style": "dialog-error"},
            {"name": _("Go Back"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-info"},
        ]
        label = Gtk.Label(hexpand=True, vexpand=True, wrap=True)
        label.set_markup(_("Are you sure you wish to cancel this test?"))
        self._gtk.Dialog(_("Cancel"), buttons, label, self.cancel_confirm)

    def cancel_confirm(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            self.disable_button("pause", "resume", "stop", "fine_tune")
            self._screen._ws.klippy.print_cancel()
            logging.debug("Canceling print test")
            return
        if response_id == Gtk.ResponseType.CANCEL:
            self.enable_button("pause", "stop", "fine_tune")
            return

    def disable_button(self, *args):
        for arg in args:
            self.action_btn[arg].set_sensitive(False)

    def show_buttons_for_state(self):
        self.labels["action_menu"].remove_row(0)
        self.labels["action_menu"].insert_row(0)
        if self.state == "paused":
            self.labels["action_menu"].attach(self.action_btn["resume"], 0, 0, 1, 1)
            self.labels["action_menu"].attach(self.action_btn["stop"], 1, 0, 1, 1)
            self.labels["action_menu"].attach(self.action_btn["fine_tune"], 2, 0, 1, 1)
        else:
            self.labels["action_menu"].attach(self.action_btn["pause"], 0, 0, 1, 1)
            self.labels["action_menu"].attach(self.action_btn["stop"], 1, 0, 1, 1)
            self.labels["action_menu"].attach(self.action_btn["fine_tune"], 2, 0, 1, 1)
        self.content.show_all()

    def change_distance(self, widget, distance):
        logging.info(f"### Distance {distance}")
        self.labels[f"{self.distance}"].get_style_context().remove_class("horizontal_togglebuttons_active")
        self.labels[f"{distance}"].get_style_context().add_class("horizontal_togglebuttons_active")
        self.distance = distance

    def move(self, widget, axis, direction):
        axis = axis.lower()
        offset_name = f"nozzle_{axis}_offset_val"
        data = self._printer.data
        last_val = 0
        if "save_variables" in data and "variables" in data["save_variables"]:
            variables = data["save_variables"]["variables"]
            last_val = variables.get(offset_name, 0)
        try:
            expression = f"{last_val} {direction} {self.distance}"
            result = eval(expression)
            self.set_nozzle_offset(offset_name, round(float(result), 2))
        except Exception as e:
            logging.error(f"Error setting {offset_name}: eval failed with expression '{expression}'. Exception: {e}")

    def set_nozzle_offset(self, option, value):
        script = KlippyGcodes.set_save_variables(option, value)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set {option}:{value}")

import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    widgets = {}
    distances = [".01", ".05", ".1", ".5", "1", "5"]
    distance = distances[-2]

    def __init__(self, screen, title):
        title = title or _("Nozzle Offset")
        super().__init__(screen, title)

        self.start_z_calibrate = False
        self.z_hop_speed = 15.0
        self.z_hop = 5.0
        self.showing_input_box = False

        self.offset_data = [
            (_("Z Offset"), "z_offset_val", "0"),
            (_("X Offset"), "x_offset_val", "0"),
            (_("Y Offset"), "y_offset_val", "0"),
        ]

        for label_text, offset_key, value_text in self.offset_data:
            self.widgets[offset_key[:8]] = Gtk.Label(label=label_text)
            self.widgets[offset_key] = Gtk.Label(label=value_text)
            event_box = Gtk.EventBox()
            event_box.add(self.widgets[offset_key])
            event_box.connect("button-release-event", self.change_offset, label_text, self.widgets[offset_key])
            setattr(self, f"{offset_key[0]}_event_box", event_box)

        pos = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        pos.attach(self.widgets["z_offset"], 0, 1, 2, 1)
        pos.attach(self.z_event_box, 0, 2, 2, 1)
        pos.attach(self.widgets["x_offset"], 0, 3, 1, 1)
        pos.attach(self.x_event_box, 0, 4, 1, 1)
        pos.attach(self.widgets["y_offset"], 1, 3, 1, 1)
        pos.attach(self.y_event_box, 1, 4, 1, 1)
        for label in pos.get_children():
            if isinstance(label, Gtk.Label):
                label.set_ellipsize(Pango.EllipsizeMode.END)
        self.buttons = {
            "z+": self._gtk.Button("z-farther", _("Lower Bed"), "color4"),
            "z-": self._gtk.Button("z-closer", _("Raise Bed"), "color1"),
            "start_z_offset": self._gtk.Button("offset_z", _("Z offset Calibrate"), "color3"),
            "start_xy_offset": self._gtk.Button("resume", _("XY offset Calibrate"), "color3"),
            "complete": self._gtk.Button("complete", _("Save"), "color3"),
            "cancel": self._gtk.Button("cancel", _("Cancel"), "color2"),
        }
        self.buttons["z+"].connect("clicked", self.move, "z", "+")
        self.buttons["z-"].connect("clicked", self.move, "z", "-")
        self.buttons["complete"].connect("clicked", self.accept)
        script = {"script": "ABORT"}
        self.buttons["cancel"].connect("clicked", self.cancel)

        self.popover = Gtk.Popover(position=Gtk.PositionType.BOTTOM)
        script = {"script": "_NOZZLE_Z_OFFSET_CALIBRATE"}
        self.buttons["start_z_offset"].connect("clicked", self.nozzle_z_offset)
        script = {"script": "_NOZZLE_XY_OFFSET_CALIBRATE"}
        self.buttons["start_xy_offset"].connect("clicked", self.nozzle_xy_offset)

        distgrid = Gtk.Grid()
        for j, i in enumerate(self.distances):
            self.widgets[i] = self._gtk.Button(label=i)
            self.widgets[i].set_direction(Gtk.TextDirection.LTR)
            self.widgets[i].connect("clicked", self.change_distance, i)
            ctx = self.widgets[i].get_style_context()
            ctx.add_class("horizontal_togglebuttons")
            if i == self.distance:
                ctx.add_class("horizontal_togglebuttons_active")
            distgrid.attach(self.widgets[i], j, 0, 1, 1)

        self.widgets["move_dist"] = Gtk.Label(_("Move Distance (mm)"))
        distances = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        distances.pack_start(self.widgets["move_dist"], True, True, 0)
        distances.pack_start(distgrid, True, True, 0)

        self.grid = Gtk.Grid(column_homogeneous=True)
        if self._screen.vertical_mode:
            self.grid.attach(self.buttons["z+"], 0, 1, 1, 1)
            self.grid.attach(self.buttons["z-"], 0, 0, 1, 1)
            self.grid.attach(self.buttons["start_z_offset"], 1, 0, 1, 1)
            self.grid.attach(pos, 1, 1, 2, 1)
            self.grid.attach(self.buttons["start_xy_offset"], 2, 0, 1, 1)
            self.grid.attach(self.buttons["complete"], 3, 0, 1, 1)
            self.grid.attach(self.buttons["cancel"], 3, 1, 1, 1)
            self.grid.attach(distances, 0, 2, 4, 1)
        else:
            self.grid.attach(self.buttons["z+"], 0, 2, 1, 1)
            self.grid.attach(self.buttons["z-"], 0, 1, 1, 1)
            self.grid.attach(self.buttons["start_z_offset"], 0, 0, 2, 1)
            self.grid.attach(self.buttons["start_xy_offset"], 2, 0, 2, 1)
            self.grid.attach(pos, 1, 1, 2, 2)
            self.grid.attach(self.buttons["complete"], 3, 1, 1, 1)
            self.grid.attach(self.buttons["cancel"], 3, 2, 1, 1)
            self.grid.attach(distances, 0, 3, 4, 1)
        self.content.add(self.grid)

    def nozzle_z_offset(self, widget):
        text = (
            _("Start testing the Z offset value of the second nozzle?\n")
            + "\n\n"
            + _("Please ensure that the Z Calibrate has been performed")
        )
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(text)
        buttons = [
            {"name": _("Accept"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-error"},
        ]
        self._gtk.Dialog(_("Calibrate Nozzle Z Offset"), buttons, label, self.confirm_nozzle_z_offset)

    def confirm_nozzle_z_offset(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            self.start_z_calibrate = True
            self.buttons_calibration_start()
            self._screen._send_action(
                self.buttons["start_z_offset"], "printer.gcode.script", {"script": "_NOZZLE_Z_OFFSET_CALIBRATE"}
            )

    def nozzle_xy_offset(self, widget):
        text = (
            _("This operation is about to print the model")
            + "\n\n"
            + _("Please load two different colored PLA filaments!")
        )

        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(text)
        buttons = [
            {"name": _("Accept"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-error"},
        ]
        self._gtk.Dialog(_("Calibrate Nozzle XY Offset"), buttons, label, self.confirm_nozzle_xy_offset)

    def confirm_nozzle_xy_offset(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            self._screen.offset_fine_tune_mode = True
            self.buttons_calibration_start()
            self._screen._send_action(
                self.buttons["start_z_offset"], "printer.gcode.script", {"script": "_NOZZLE_XY_OFFSET_CALIBRATE"}
            )

    def change_offset(self, widget, event, title_label, offset_label):
        self._create_input_box(title_label, offset_label)

    def _create_input_box(self, title_label, offset_label):
        current_val = offset_label.get_text()
        title_label += "        " + _("Current value:") + f"{current_val}"
        for child in self.content.get_children():
            self.content.remove(child)
        lbl = Gtk.Label(label=title_label, halign=Gtk.Align.START, hexpand=False)
        self.labels["entry"] = Gtk.Entry(hexpand=True)
        self.labels["entry"].connect("focus-in-event", self._screen.show_keyboard)
        save = self._gtk.Button("complete", _("Save"), "color3")
        save.set_hexpand(False)
        save.connect("clicked", self.store_value, offset_label)
        box = Gtk.Box()
        box.pack_start(self.labels["entry"], True, True, 5)
        box.pack_start(save, False, False, 5)
        self.labels["input_box"] = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True, vexpand=True, valign=Gtk.Align.CENTER
        )
        self.labels["input_box"].pack_start(lbl, True, True, 5)
        self.labels["input_box"].pack_start(box, True, True, 5)
        self.content.add(self.labels["input_box"])
        self.labels["entry"].grab_focus_without_selecting()
        self.showing_input_box = True

    def hide_input_box(self):
        self._screen.remove_keyboard()
        for child in self.content.get_children():
            self.content.remove(child)
        self.content.add(self.grid)
        self.content.show()
        self.showing_input_box = False

    def store_value(self, widget, offset_label):
        val_text = self.labels["entry"].get_text()
        try:
            val = round(float(val_text), 3)
            name = None
            for label_text, offset_key, _ in self.offset_data:
                if offset_label == self.widgets[offset_key]:
                    name = offset_key
                    break
            if name is not None:
                name = "nozzle_" + name
                self.set_nozzle_offset(name, val)
            if self.showing_input_box:
                self.hide_input_box()
        except ValueError:
            self._screen.show_popup_message(_("Please enter a valid number"))

    def set_nozzle_offset(self, option, value):
        script = KlippyGcodes.set_save_variables(option, value)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set {option}:{value}")

    def back(self):
        if self.showing_input_box:
            self.hide_input_box()
            return True
        return False

    def _add_button(self, label, method, pobox):
        popover_button = self._gtk.Button(label=label)
        pobox.pack_start(popover_button, True, True, 5)

    def on_popover_clicked(self, widget):
        self.popover.set_relative_to(widget)
        self.popover.show_all()

    def activate(self):
        is_sensitive = self.buttons["start_z_offset"].get_sensitive()
        if is_sensitive:
            self.buttons_not_z_calibration()
        else:
            self.buttons_calibration_start()

    def deactivate(self):
        if self.start_z_calibrate:
            self.start_z_calibrate = False

    def process_update(self, action, data):

        if action == "notify_gcode_response":
            if self.start_z_calibrate and "extruder1" in data:
                self.buttons_z_calibration()
            elif "action:resumed" in data:
                return
        if action != "notify_status_update":
            return
        if "save_variables" in data and "variables" in data["save_variables"]:
            variables = data["save_variables"]["variables"]
            nozzle_offsets = ["nozzle_z_offset_val", "nozzle_x_offset_val", "nozzle_y_offset_val"]

            for offset in nozzle_offsets:
                if offset in variables:
                    self.widgets[f'{offset.split("_")[1]}_offset_val'].set_text(f"{variables[offset]}")

        if "gcode_move" in data or "toolhead" in data and "homed_axes" in data["toolhead"]:
            homed_axes = self._printer.get_stat("toolhead", "homed_axes")

            if "z" in homed_axes:
                self.pos_z = round(data["gcode_move"]["gcode_position"][2], 3)
                if self.start_z_calibrate:
                    self.widgets["z_offset_val"].set_text(f"{self.pos_z}")

    def change_distance(self, widget, distance):
        logging.info(f"### Distance {distance}")
        self.widgets[f"{self.distance}"].get_style_context().remove_class("horizontal_togglebuttons_active")
        self.widgets[f"{distance}"].get_style_context().add_class("horizontal_togglebuttons_active")
        self.distance = distance

    def move(self, widget, axis, direction):
        dist = f"{direction}{self.distance}"
        script = f"{KlippyGcodes.MOVE_RELATIVE}\nG0 {axis}{dist} F300"
        self._screen._send_action(widget, "printer.gcode.script", {"script": script})
        if self._printer.get_stat("gcode_move", "absolute_coordinates"):
            self._screen._ws.klippy.gcode_script("G90")

    def accept(self, widget):
        logging.info("Accepting nozzle Z offset")
        script = f"SET_GCODE_OFFSET Z={self.pos_z}"
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        script = f"G91\n G0 Z5 F6000"
        self._screen._send_action(None, "printer.gcode.script", {"script": script})

        self.set_nozzle_offset("nozzle_z_offset_val", self.pos_z)
        self.buttons_not_z_calibration()
        self.start_z_calibrate = False

    def cancel(self, widget):
        self.start_z_calibrate = False
        self.buttons_not_z_calibration()
        variables = self._printer.get_stat("save_variables", "variables")
        if "nozzle_z_offset_val" in variables:
            self.widgets["z_offset_val"].set_text(f"{variables['nozzle_z_offset_val']}")

    def buttons_calibration_start(self):
        self.buttons["start_z_offset"].set_sensitive(False)
        self.buttons["start_xy_offset"].set_sensitive(False)

        self.buttons["z+"].set_sensitive(False)
        self.buttons["z-"].set_sensitive(False)
        self.buttons["complete"].set_sensitive(False)
        self.buttons["cancel"].set_sensitive(False)

    def buttons_z_calibration(self):
        self.buttons["start_z_offset"].set_sensitive(False)
        self.buttons["start_xy_offset"].set_sensitive(False)
        self.buttons["z+"].set_sensitive(True)
        self.buttons["z-"].set_sensitive(True)
        self.buttons["complete"].set_sensitive(True)
        self.buttons["cancel"].set_sensitive(True)

    def buttons_not_z_calibration(self):
        self.buttons["start_z_offset"].set_sensitive(True)
        self.buttons["start_xy_offset"].set_sensitive(True)
        self.buttons["z+"].set_sensitive(False)
        self.buttons["z-"].set_sensitive(False)
        self.buttons["complete"].set_sensitive(False)
        self.buttons["cancel"].set_sensitive(False)

import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib
from contextlib import suppress
from ks_includes.screen_panel import ScreenPanel
from ks_includes.KlippyGtk import find_widget
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.align_camera import CameraController

class CalibrationPanel(ScreenPanel):
    def __init__(self, screen, title, **kwargs):
        super().__init__(screen, title, **kwargs)
        self.calibrating = False
        self.is_turning = False

    def _update_calibration_state(self, state):
        if self.calibrating == state:
            return
        self.calibrating = state
        if hasattr(self._screen, '_cur_panels'):
            current_panel = self._screen._cur_panels[-1]
            if current_panel in ('xy_calibrate', 'dual_zcalibrate', 'offset_manage'):
                self._screen.show_panel(current_panel, remove_current=True)

    def start_calibration(self):
        self._update_calibration_state(True)

    def finish_calibration(self):
        self._update_calibration_state(False)

    def _create_cleaning_stage(self, stack):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_margin_top(30)
        vbox.pack_start(self._create_icon_title_box("run-waiting", _("Heating and cleaning nozzles before calibration")), False, False, 0)

        cleaning_step_label = Gtk.Label(_("Preparing to clean nozzles"))
        cleaning_step_label.set_name("cleaning_step_label")
        cleaning_step_label.set_halign(Gtk.Align.CENTER)
        cleaning_step_label.set_line_wrap(True)
        cleaning_step_label.set_max_width_chars(35)
        cleaning_step_label.set_margin_top(10)
        self.widgets["cleaning_step_label"] = cleaning_step_label
        vbox.pack_start(cleaning_step_label, False, False, 0)

        temp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=30)
        temp_box.set_halign(Gtk.Align.CENTER)
        self.widgets["cleaning_temp_box"] = temp_box
        vbox.pack_start(temp_box, False, False, 20)

        stack.add_named(vbox, "cleaning")
        return vbox

    def _update_cleaning_display(self):
        if "cleaning_temp_box" not in self.widgets:
            return
        temp_box = self.widgets["cleaning_temp_box"]
        for child in temp_box.get_children():
            temp_box.remove(child)
        for i, extruder in enumerate(self._printer.get_tools()):
            temp = round(self._printer.get_stat(extruder, "temperature"))
            target = self._printer.get_stat(extruder, "target")
            temp_target = round(target) if target else 0
            extruder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            image = self._gtk.Image(f"extruder-{i}", *self._scaled(0.1, 0.1))
            extruder_box.pack_start(image, False, False, 10)
            temp_label = Gtk.Label(label=f"{temp}°/{temp_target}°")
            temp_label.set_halign(Gtk.Align.CENTER)
            extruder_box.pack_start(temp_label, False, False, 10)
            temp_box.pack_start(extruder_box, False, False, 0)
        temp_box.show_all()

        if "cleaning_step_label" in self.widgets:
            all_extruders_have_target = True
            extruders = self._printer.get_tools()
            for extruder in extruders:
                target = self._printer.get_stat(extruder, "target")
                if not target or target == 0:
                    all_extruders_have_target = False
                    break

            current_extruder = self._printer.get_stat("toolhead", "extruder")
            if all_extruders_have_target and len(extruders) >= 2:
                display_text = _("Waiting for nozzle clean temperature")
            else:
                if current_extruder == "extruder":
                    if self._printer.get_stat("extruder1", "target") == 0:
                        display_text = _("Waiting for homing complete")
                    else:
                        display_text = _("Cleaning left nozzle")
                elif current_extruder == "extruder1":
                    display_text = _("Cleaning right nozzle")
                else:
                    display_text = _("Cleaning nozzles")
            self.widgets["cleaning_step_label"].set_text(display_text)

    def _handle_cleaning_completion(self, stack_name="left_probe"):
        if "progress_stack" in self.widgets:
            self.widgets["progress_stack"].set_visible_child_name(stack_name)
            self.current_extruder = "extruder0"
            if "left_image" in self.widgets:
                self.widgets["left_image"].set_visible_child_name("left_nozzle")

    def _create_icon_title_box(self, icon_name, title_text):
        title = Gtk.Label()
        title.set_markup(title_text)
        title.set_line_wrap(True)
        title.set_max_width_chars(28)
        title.set_margin_bottom(20)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        icon = self._gtk.Image(icon_name, *self._scaled(0.1, 0.1))
        hbox.pack_start(icon, False, False, 0)
        hbox.pack_start(title, False, False, 0)
        return hbox

    def _scaled(self, w_rate: float, h_rate=None):
        h_rate = h_rate or w_rate
        try:
            return (int(self._gtk.content_width * w_rate),
                    int(self._gtk.content_height * h_rate))
        except Exception:
            return (int(400 * w_rate), int(300 * h_rate))

    def _create_stack(self, panels_config):
        stack = Gtk.Stack()
        for name, create_func in panels_config:
            stack.add_named(create_func(), name)
        stack.set_visible_child_name(panels_config[0][0])
        return stack

    def _create_label(self, text, markup=False, **kwargs):
        label = Gtk.Label()
        if markup:
            label.set_markup(text)
        else:
            label.set_text(text)
        for key, val in kwargs.items():
            if hasattr(label, f"set_{key}"):
                getattr(label, f"set_{key}")(val)
        return label

    def _create_button(self, label, callback=None, icon=None, color=None, **kwargs):
        btn = self._gtk.Button(icon, label, color)
        btn.set_size_request(*self._scaled(0.16, 0.1))
        if callback:
            btn.connect("clicked", callback)
        for key, val in kwargs.items():
            if hasattr(btn, f"set_{key}"):
                getattr(btn, f"set_{key}")(val)
        return btn

class Panel(CalibrationPanel):
    """Dual color calibration panel."""
    def __init__(self, screen, title, **kwargs):
        title = title or _("Dual Color Calibration")
        super().__init__(screen, title)
        self.widgets = {}
        self.start_btn_active = False
        self.xy_offset_calibration = True
        self.z_offset_calibration = True

        self.x_offset = self.last_x_offset = 0.0
        self.y_offset = self.last_y_offset = 0.0
        self.z_offset = self.last_z_offset = 0.0
        self.offset_label = None
        self.print_test = kwargs.get("print_test", False)
        self.cam_controller = CameraController(self)

        self._init_containers()
        self._build_layout()

        self.cam_controller.init_cam_tip()
        GLib.timeout_add_seconds(1, self.cam_controller.load_camera)

    def _create_toggle_switch(self, label, active=False, callback=None):
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, margin=0)
        content_box.set_hexpand(True)

        switch_label = self._create_label(
            _(f"<span font-size='small'>{label}</span>"),
            markup=True,
            halign=Gtk.Align.START
        )
        content_box.pack_start(switch_label, False, False, 20)

        toggle_switch = Gtk.Switch()
        toggle_switch.set_active(active)
        if callback:
            toggle_switch.connect("notify::active", callback)
        content_box.pack_end(toggle_switch, False, False, 20)

        return content_box

    def _init_containers(self):
        self.title_label = self._create_label(
            _("Dual Color Calibration"),
            markup=True,
            halign=Gtk.Align.CENTER,
            margin_top=10,
            margin_bottom=10,
        )

        left_panels = [
            ("camera", self._left_cam_panel),
            ("image", self._left_image_panel)
        ]
        self.left_container = self._create_stack(left_panels)

        right_panels = [
            ("default", self._right_default_panel),
            ("print", self._right_print_panel)
        ]
        self.right_container = self._create_stack(right_panels)

    def _left_cam_panel(self):
        left_vbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER
        )
        self.cam_box = self.cam_controller.create_camera_display_area()
        left_vbox.pack_start(self.cam_box, False, False, 20)
        return left_vbox

    def _add_instruction_item(self, instructions_box, text):
        label = self._create_label(
            text,
            halign=Gtk.Align.START,
            xalign=0.0,
            line_wrap=True,
            max_width_chars=45,
            line_wrap_mode=Pango.WrapMode.WORD
        )
        instructions_box.pack_start(label, False, False, 2)

    def _left_image_panel(self):
        left_vbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5,
            valign=Gtk.Align.START,
            halign=Gtk.Align.CENTER
        )

        instructions_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5,
            halign=Gtk.Align.START
        )

        self._add_instruction_item(instructions_box, _("1. Set nozzle and bed temperature before printing validation."))
        self._add_instruction_item(instructions_box, _("2. Load filament in the Filament Settings if needed."))
        self._add_instruction_item(instructions_box, _("3. Tap Start Print to run the validation model."))
        self._add_instruction_item(instructions_box, _("4. Tap Save to skip printing validation."))
        self._add_instruction_item(instructions_box, _("5. Tap Discard to discard right nozzle offsets."))

        image = self._gtk.Image("nozzle-aglin", *self._scaled(0.25, 0.25))
        left_vbox.pack_start(image, False, False, 5)
        left_vbox.pack_start(instructions_box, False, False, 0)
        return left_vbox

    def _right_default_panel(self):
        right_vbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            valign=Gtk.Align.START,
            halign=Gtk.Align.FILL,
            hexpand=True
        )

        switches_card_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin=30
        )
        switches_card_box.get_style_context().add_class("toggle-switch-card")

        self.xy_offset_toggle = self._create_toggle_switch(
            _("Right Nozzle XY Offset Calibration"),
            active=True,
            callback=self.on_toggle_xy_offset
        )

        self.z_offset_toggle = self._create_toggle_switch(
            _("Right Nozzle Z Offset Calibration"),
            active=True,
            callback=self.on_toggle_z_offset
        )

        switches_card_box.pack_start(self.xy_offset_toggle, False, False, 0)
        switches_card_box.pack_start(self.z_offset_toggle, False, False, 0)

        self.default_offset_label = self._create_label(
            self._get_offset_text(),
            line_wrap=True,
            max_width_chars=40,
            halign=Gtk.Align.CENTER,
            margin_top=5,
            margin_bottom=5,
        )

        self.instructions_label = self._create_label(
            _("Calibration is only required if dual-color printing malfunctions.\n"
              "Common scenarios: nozzle replacement, hotend replacement, "
              "printer collision, or mechanical zero adjustment."),
            line_wrap=True,
            max_width_chars=40,
            halign=Gtk.Align.START,
            margin_left=20,
            margin_right=20,
            margin_top=20,
            margin_bottom=5,
        )
        self.instructions_label.override_font(Pango.FontDescription("small"))

        right_default_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15, margin=30)
        cancel_btn = self._create_button(_("Cancel"), self.on_cancel, None, "color2")
        start_calib_btn = self._create_button(_("Start"), self.on_start_calibration, None, "color4")
        right_default_btns.pack_start(cancel_btn, False, False, 0)
        right_default_btns.pack_start(start_calib_btn, False, False, 0)

        right_vbox.pack_start(switches_card_box, False, False, 0)
        right_vbox.pack_start(self.default_offset_label, False, False, 0)
        right_vbox.pack_start(self.instructions_label, False, False, 0)
        right_vbox.pack_start(right_default_btns, False, False, 0)

        return right_vbox

    def _right_print_panel(self):
        right_vbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=15,
            valign=Gtk.Align.START,
            halign=Gtk.Align.FILL
        )

        temp_icons_box = Gtk.Grid(vexpand=False, halign=Gtk.Align.FILL, margin_top=10)
        temp_icons_box.set_column_homogeneous(True)
        temp_icons_box.set_row_homogeneous(False)
        temp_icons_box.set_column_spacing(0)

        self.temp_devices = {}
        def create_temp_device_button(icon_name, device_type):
            device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            device_box.set_halign(Gtk.Align.FILL)
            device_box.set_hexpand=True

            button = Gtk.Button(can_focus=False)
            button.set_halign(Gtk.Align.FILL)
            button.set_valign(Gtk.Align.CENTER)
            button.set_hexpand=True
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            vbox.set_halign(Gtk.Align.FILL)
            vbox.set_hexpand=True
            vbox.set_vexpand=True

            target = Gtk.Label()
            target.set_halign(Gtk.Align.CENTER)
            target.set_valign(Gtk.Align.CENTER)

            icon = self._gtk.Image(icon_name, *self._scaled(0.08, 0.1))
            icon.set_halign(Gtk.Align.FILL)
            icon.set_hexpand=True

            temp = Gtk.Label()
            temp.set_halign(Gtk.Align.CENTER)
            temp.set_valign(Gtk.Align.CENTER)

            vbox.pack_start(target, True, True, 5)
            vbox.pack_start(icon, True, True, 0)
            vbox.pack_start(temp, True, True, 0)
            button.add(vbox)
            button.connect("clicked", self.menu_item_clicked, {"panel": "numpad", "extra": device_type})
            device_box.pack_start(button, True, True, 0)

            self.temp_devices[device_type] = {
                "target": target,
                "temp": temp
            }

            return device_box

        temp_icons_box.attach(create_temp_device_button("extruder-0", "extruder"), 0, 0, 1, 1)
        temp_icons_box.attach(create_temp_device_button("extruder-1", "extruder1"), 1, 0, 1, 1)
        temp_icons_box.attach(create_temp_device_button("bed", "heater_bed"), 2, 0, 1, 1)
        right_vbox.pack_start(temp_icons_box, True, True, 5)

        filament_btn = self._create_button(_("Filament Settings"), self.on_jump_to_filament_settings, "filament", "color1")
        right_vbox.pack_start(filament_btn, True, True, 10)
        self.offset_label = self._create_label(
            self._get_offset_text(),
            halign=Gtk.Align.CENTER,
            line_wrap=True,
            max_width_chars=40,
            margin_bottom=10
        )
        right_vbox.pack_start(self.offset_label, False, False, 0)

        right_print_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        discard_btn = self._create_button(_("Discard"), self.on_discard, None, "color2")
        save_btn = self._create_button(_("Save"), self.on_save, None, "color3")
        self.start_calib_btn = self._create_button(_("Start Printing"), self.on_start_print, None, "color4")
        self.start_calib_btn.set_sensitive(False)
        right_print_btns.pack_start(discard_btn, False, False, 0)
        right_print_btns.pack_start(save_btn, False, False, 0)
        right_print_btns.pack_start(self.start_calib_btn, False, False, 0)
        right_vbox.pack_start(right_print_btns, False, False, 0)

        return right_vbox

    def _build_layout(self):
        self.top_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=5
        )
        self.top_container.pack_start(self.left_container, False, False, 0)
        self.top_container.pack_start(self.right_container, False, False, 0)

        main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            margin_left=10,
            margin_right=10
        )
        main_box.pack_start(self.title_label, False, False, 0)
        main_box.pack_start(self.top_container, True, True, 0)

        self.content.add(main_box)

    def on_cancel(self, widget):
        self.print_test = False
        self._screen._menu_go_back()

    def on_start_calibration(self, widget):
        self.last_x_offset = self.x_offset
        self.last_y_offset = self.y_offset
        self.last_z_offset = self.z_offset
        self.calibrating = True
        if self.xy_offset_calibration:
            self._screen._ws.klippy.gcode_script("G28")
            self._screen._ws.klippy.gcode_script("KTAMV_MOVE_DATUM_CENTER")
            if self.z_offset_calibration:
                self._screen.show_panel("align_datum", finish_action="continue_z", remove_current=True)
            else:
                self._screen.show_panel("align_datum", finish_action="print_test", remove_current=True)
        elif self.z_offset_calibration:
            self._screen.show_panel("dual_zcalibrate", auto_action="print_test", remove_current=True)
        else:
            self._switch_to_print_test()

    def _switch_to_print_test(self):
        self.print_test = False
        self.finish_calibration()
        self.title_label.set_text(_("Print verification"))
        self.right_container.set_visible_child_name("print")
        self.left_container.set_visible_child_name("image")
        logging.info("Switched to print verification interface")

    def _switch_to_default(self):
        self.title_label.set_text(_("Dual Color Calibration"))
        self.right_container.set_visible_child_name("default")
        self.left_container.set_visible_child_name("camera")
        if self.cam_box.get_window():
            self.cam_controller.load_camera(self.cam_box)
    def on_jump_to_filament_settings(self, widget):
        self._screen.show_panel("extrude", remove_all=False, keep_stack=True)

    def on_discard(self, widget):
        for axis in ['x', 'y', 'z']:
            setattr(self, f"{axis}_offset", getattr(self, f"last_{axis}_offset"))
            script = KlippyGcodes.set_save_variables(f"nozzle_{axis}_offset_val", getattr(self, f"last_{axis}_offset"))
            self._screen._send_action(None, "printer.gcode.script", {"script": script})
        self._switch_to_default()

    def on_save(self, widget):
        self.print_test = False
        self._switch_to_default()

    def on_start_print(self, widget):
        self._screen._ws.klippy.gcode_script("_NOZZLE_XY_OFFSET_CALIBRATE")

    def on_toggle_xy_offset(self, widget, param):
        active = widget.get_active()
        self.xy_offset_calibration = active

    def on_toggle_z_offset(self, widget, param):
        active = widget.get_active()
        self.z_offset_calibration = active

    def _get_offset_text(self):
        return _("Current right nozzle offsets:\n\n X:{}  Y:{}  Z:{}").format(
            self.x_offset, self.y_offset, self.z_offset
        )

    def process_update(self, action, data):
        if action == "notify_status_update":
            if "save_variables" in data:
                variables = data["save_variables"].get("variables", {})
                offset_updated = False
                for axis in ['x', 'y', 'z']:
                    var_name = f"nozzle_{axis}_offset_val"
                    attr_name = f"{axis}_offset"
                    if var_name in variables:
                        setattr(self, attr_name, variables[var_name])
                        offset_updated = True

                if offset_updated:
                    if hasattr(self, 'offset_label') and self.offset_label:
                        self.offset_label.set_text(self._get_offset_text())
                    if hasattr(self, 'default_offset_label') and self.default_offset_label:
                        self.default_offset_label.set_text(self._get_offset_text())

            if hasattr(self, 'temp_devices'):
                for device in self.temp_devices:
                    if device in data:
                        self.update_temp(
                            device,
                            self._printer.get_stat(device, "temperature"),
                            self._printer.get_stat(device, "target"),
                            self._printer.get_stat(device, "power"),
                        )

    def update_temp(self, dev, temp, target, power, lines=1, digits=1):
        temp_label_text = f"{temp or 0:.{digits}f}℃"
        target_label_text = "0℃"

        if self._printer.device_has_target(dev) and target:
             target_label_text = f"{target:.0f}℃"

        if dev in self.temp_devices:
            self.temp_devices[dev]["target"].set_text(target_label_text)
            self.temp_devices[dev]["temp"].set_text(temp_label_text)

        self._check_extruder_temperatures()

    def _check_extruder_temperatures(self):
        if not hasattr(self, 'start_calib_btn'):
            return
        all_extruders_have_target = True
        extruder_devices = ["extruder", "extruder1"]

        for device in extruder_devices:
            if device in self.temp_devices:
                target = self._printer.get_stat(device, "target")
                if not target or target <= 120:
                    all_extruders_have_target = False
                    break
        self.start_calib_btn.set_sensitive(all_extruders_have_target)

    def activate(self):
        self.cam_controller.init_cam_tip()
        if self.cam_box.get_window():
            self.cam_controller.load_camera(self.cam_box)
        if self.print_test:
            self._switch_to_print_test()

    def deactivate(self):
        self.print_test = False
        self.cam_controller.deactivate()

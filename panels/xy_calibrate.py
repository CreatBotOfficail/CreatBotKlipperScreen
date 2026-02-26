import logging
import gi
import re
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from ks_includes.align_camera import CameraController

class Panel(ScreenPanel):
    """Camera XY offset calibration panel."""
    def __init__(self, screen, title, **kwargs):
        title = title or _("XY Calibrate")
        super().__init__(screen, title)
        self.widgets = {}
        self.x_offset = self.y_offset = 0.0
        self.finish_action = kwargs.get("finish_action", None)
        self.cam_controller = CameraController(self)

        self.countdown_running = False
        self.countdown_timer_id = None

        self._init_widgets()
        self._init_containers()
        self._build_layout()

        self.cam_controller.init_cam_tip()
        GLib.timeout_add_seconds(1, self.cam_controller.delayed_load_camera)

    def _scaled(self, w_rate: float, h_rate=None):
        h_rate = h_rate or w_rate
        try:
            return (int(self._gtk.content_width * w_rate),
                    int(self._gtk.content_height * h_rate))
        except Exception:
            return (100, 100)

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

    def _create_button(self, label, callback,** kwargs):
        btn = self._gtk.Button(label=label)
        btn.set_size_request(*self._scaled(0.2, 0.1))
        btn.connect("clicked", callback)
        for key, val in kwargs.items():
            if hasattr(btn, f"set_{key}"):
                getattr(btn, f"set_{key}")(val)
        return btn

    def _create_stack(self, panels_config):
        stack = Gtk.Stack()
        for name, create_func in panels_config:
            stack.add_named(create_func(), name)
        stack.set_visible_child_name(panels_config[0][0])
        return stack

    def _init_containers(self):
        left_panels = [
            ("default", self._left_default_panel),
            ("tip", self._left_tip_panel)
        ]
        self.left_container = self._create_stack(left_panels)

        right_panels = [
            ("default", self._right_default_panel),
            ("tip", self._right_tip_panel),
            ("progress", self._right_progress_panel)
        ]
        self.right_container = self._create_stack(right_panels)

        bottom_panels = [
            ("start", self._bottom_start_panel),
            ("next", self._bottom_next_panel),
            ("finish", self._bottom_save_panel),
            ("empty", self._bottom_empty_panel),
            ("fail", self._bottom_fail_panel)
        ]
        self.bottom_container = self._create_stack(bottom_panels)

    def _init_widgets(self):
        self.title_label = self._create_label(
            _("XY Offset Calibration"),
            markup=True,
            halign=Gtk.Align.CENTER,
            margin_top=10
        )
        self.cam_box = self._create_cam_display_area()

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
        main_box.pack_start(self.bottom_container, False, False, 0)

        self.content.add(main_box)

    def _left_default_panel(self):
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        container.set_valign(Gtk.Align.CENTER)
        container.set_halign(Gtk.Align.CENTER)
        container.pack_start(self.cam_box, False, False, 0)
        return container

    def _create_cam_display_area(self):
        return self.cam_controller.create_camera_display_area()

    def _left_tip_panel(self):
        img = self._gtk.Image("camera-calibrate", *self._scaled(0.4, 0.5))
        img.set_valign(Gtk.Align.CENTER)
        img.set_halign(Gtk.Align.END)
        return img

    def _right_default_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, valign=Gtk.Align.CENTER, halign=Gtk.Align.END)
        box.pack_start(self._create_tip_title(), False, False, 0)
        box.pack_start(self._create_tip_text1(), False, False, 5)
        box.pack_start(self._create_offset_box("current"), False, False, 5)
        box.pack_start(self._create_tip_text2(), False, False, 5)
        return box

    def _right_tip_panel(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            valign=Gtk.Align.CENTER
        )
        box.pack_start(self._create_label(
            _("Place the camera in the indicated position"),
            markup=True,
            max_width_chars=20,
            halign=Gtk.Align.CENTER
        ), False, False, 0)
        return box

    def _right_progress_panel(self):
        self.widgets["progress_stack"] = Gtk.Stack()
        self.widgets["progress_stack"].set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        def _create_state_panel(icon_name, title_text, stack_name):
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            vbox.set_halign(Gtk.Align.CENTER)
            vbox.set_margin_start(20)

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon = self._gtk.Image(icon_name, *self._scaled(0.06, 0.06))
            title = self._create_label(title_text, markup=True, halign=Gtk.Align.START)
            hbox.pack_start(icon, False, False, 5)
            hbox.pack_start(title, False, False, 0)
            vbox.pack_start(hbox, False, False, 0)

            data_label = self._create_label(
                "", halign=Gtk.Align.START, line_wrap=True, max_width_chars=40
            )
            self.widgets[f"progress_data_{stack_name}"] = data_label
            self.widgets[f"progress_data_{stack_name}"].set_margin_top(20)
            vbox.pack_start(data_label, False, False, 0)

            self.widgets["progress_stack"].add_named(vbox, stack_name)
            return vbox

        in_progress_stack = Gtk.Stack()
        in_progress_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        def _create_calibration_header(vbox):
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon = self._gtk.Image("run-waiting", *self._scaled(0.03, 0.04))
            title = self._create_label(
                _("<span font-size='large'>Calibration in progress...</span>"), 
                markup=True, 
                halign=Gtk.Align.START
            )
            hbox.pack_start(icon, False, False, 0)
            hbox.pack_start(title, False, False, 0)
            vbox.pack_start(hbox, False, False, 0)
        
        default_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        default_vbox.set_halign(Gtk.Align.START)
        _create_calibration_header(default_vbox)
        
        data_label = self._create_label(
            "", halign=Gtk.Align.START, line_wrap=True, max_width_chars=40
        )
        self.widgets["progress_data_in_progress"] = data_label
        self.widgets["progress_data_in_progress"].set_margin_top(20)
        default_vbox.pack_start(data_label, False, False, 0)

        cleaning_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        cleaning_vbox.set_halign(Gtk.Align.START)
        _create_calibration_header(cleaning_vbox)

        temp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        cleaning_vbox.pack_start(temp_box, False, False, 0)

        step_label = self._create_label("", halign=Gtk.Align.START)
        cleaning_vbox.pack_start(step_label, False, False, 10)

        self.widgets["cleaning_temp_box"] = temp_box
        self.widgets["cleaning_step_label"] = step_label

        in_progress_stack.add_named(default_vbox, "default")
        in_progress_stack.add_named(cleaning_vbox, "cleaning")
        in_progress_stack.set_visible_child_name("default")
        self.widgets["progress_stack"].add_named(in_progress_stack, "in_progress")
        self.widgets["in_progress_stack"] = in_progress_stack

        _create_state_panel(
            "result-good",
            _("<span color='green' font-size='x-large'>Calibration Succeeded!</span>"),
            "success"
        )
        _create_state_panel(
            "result-bed",
            _("<span color='red' font-size='x-large'>Calibration Failed!</span>"),
            "fail"
        )

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.pack_start(Gtk.Box(vexpand=True), True, True, 0)
        panel.pack_start(self.widgets["progress_stack"], False, False, 0)
        panel.set_halign(Gtk.Align.CENTER)
        panel.set_valign(Gtk.Align.CENTER)
        panel.set_margin_left(10)

        self.widgets["progress_stack"].set_visible_child_name("in_progress")
        return panel

    def _get_offset_text(self):
        return _("right nozzle offsets: X:{}  Y:{}").format(self.x_offset, self.y_offset)

    def _create_offset_box(self, prefix):
        offset_label = self._create_label(
            self._get_offset_text(),
            markup=True,
            halign=Gtk.Align.START,
            line_wrap=True
        )
        setattr(self, f"{prefix}_offset_label", offset_label)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5,
            halign=Gtk.Align.CENTER,
            margin=20
        )
        box.get_style_context().add_class("toggle-switch-card")
        box.pack_start(offset_label, False, False, 15)
        return box

    def _create_tip_title(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.START
        )
        icon = self._gtk.Image("light_hint", *self._scaled(0.03, 0.04))
        icon.set_valign(Gtk.Align.START)
        box.pack_start(icon, False, False, 0)
        box.pack_start(self._create_label(
            _("<span>Calibration Tips</span>"),
            markup=True,
            halign=Gtk.Align.START
        ), False, False, 0)
        return box

    def _create_tip_text1(self):
        label = self._create_label(
            _("It is recommended to perform calibration of the dual nozzle offset after replacing "
              "or adjusting the nozzle to ensure printing accuracy and reliability."),
            halign=Gtk.Align.START,
            line_wrap=True,
            max_width_chars=35,
            line_wrap_mode=Pango.WrapMode.WORD
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.pack_start(label, False, False, 10)
        return box

    def _create_tip_text2(self):
        label = self._create_label(
            _("To ensure calibration accuracy, please perform the following steps first:\n\n"
              "1. Unload the filament out of the nozzles\n"
              "2. Thoroughly clean the nozzles"),
            halign=Gtk.Align.START,
            line_wrap=True,
            max_width_chars=35,
            line_wrap_mode=Pango.WrapMode.WORD
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_margin_top(15)
        box.pack_start(label, False, False, 0)
        return box

    def _bottom_start_panel(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=0,
            halign=Gtk.Align.END,
            margin_right=30,
        )
        self.widgets["btn_start_single"] = self._create_button(
            _("Start"), self.on_start_calibrate
        )
        box.pack_start(self.widgets["btn_start_single"], False, False, 0)
        return box

    def _bottom_next_panel(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=15,
            halign=Gtk.Align.END,
            margin_top=10,
        )
        self.widgets["btn_return"] = self._create_button(
            _("Return"), self.on_return_start
        )
        self.widgets["btn_next"] = self._create_button(
            _("Next"), self.on_next_calibrate
        )
        box.pack_start(self.widgets["btn_return"], False, False, 0)
        box.pack_start(self.widgets["btn_next"], False, False, 0)
        return box

    def _bottom_save_panel(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=15,
            halign=Gtk.Align.END,
            margin_top=10,
            margin_right=20
        )
        self.widgets["btn_return"] = self._create_button(
            _("Return"), self.on_return_start
        )
        self.widgets["btn_print"] = self._create_button(
            _("Save"), self.on_save_calibrate
        )
        box.pack_start(self.widgets["btn_return"], False, False, 0)
        box.pack_start(self.widgets["btn_print"], False, False, 0)
        return box

    def _bottom_empty_panel(self):
        return Gtk.Box(height_request=20)

    def _bottom_fail_panel(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=15,
            halign=Gtk.Align.END,
            margin_top=10,
        )
        self.widgets["btn_fail_return"] = self._create_button(
            _("Return"), self.on_return_start
        )
        self.widgets["btn_fail"] = self._create_button(
            _("Recalibrate"), self.on_next_calibrate
        )
        box.pack_start(self.widgets["btn_fail_return"], False, False, 0)
        box.pack_start(self.widgets["btn_fail"], False, False, 0)
        return box

    def on_start_calibrate(self, widget):
        mode = self._screen.connecting_to_printer.split("-")[0]
        if mode == "F430NX":
            self.left_container.set_visible_child_name("tip")
            self.right_container.set_visible_child_name("tip")
            self.bottom_container.set_visible_child_name("next")
        else:
            self.right_container.set_visible_child_name("progress")
            self.widgets["progress_data_in_progress"].set_text("")
            self.widgets["progress_stack"].set_visible_child_name("in_progress")
            self.current_progress = 0.0
            self.progress_update_count = 0
            self.bottom_container.set_visible_child_name("empty")
            self._screen._ws.klippy.gcode_script("KTAMV_CALIB_NOZZLE")

    def on_next_calibrate(self, widget):
        self.left_container.set_visible_child_name("default")
        self.widgets["progress_data_in_progress"].set_text("")
        self.widgets["progress_stack"].set_visible_child_name("in_progress")
        self.right_container.set_visible_child_name("progress")
        self.bottom_container.set_visible_child_name("empty")
        self._screen._ws.klippy.gcode_script("KTAMV_CALIB_NOZZLE")

    def on_save_calibrate(self, widget):
        self._screen._ws.klippy.gcode_script("KTAMV_SAVE_OFFSET")
        self.left_container.set_visible_child_name("default")
        self.right_container.set_visible_child_name("default")
        self.bottom_container.set_visible_child_name("start")
    
    def _countdown_timer(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.widgets["btn_print"].set_label(_("Next ({})").format(self.countdown))
            return True
        else:
            self._countdown_finish()
            return False
    
    def _countdown_finish(self):
        self.countdown_running = False
        if hasattr(self, 'countdown_timer_id') and self.countdown_timer_id:
            GLib.source_remove(self.countdown_timer_id)
            self.countdown_timer_id = None

        self._return_default()
        if self.finish_action == "continue_z":
            self._screen.show_panel("dual_zcalibrate", auto_action="auto_start", remove_current=True)
        else:
            self._screen.show_panel("offset_manage", print_test=True, remove_current=True)

    def on_return_start(self, widget):
        self._return_default()
    
    def _return_default(self):
        self.left_container.set_visible_child_name("default")
        self.right_container.set_visible_child_name("default")
        self.bottom_container.set_visible_child_name("start")
        self._screen._ws.klippy.gcode_script("KTAMV_CLEAR_STATUS")

    def init_cam_tip(self):
        self.cam_controller.init_cam_tip()

    def load_calibrate_camera(self, widget):
        self.cam_controller.load_camera(widget)

    def mpv_log(self, loglevel, component, message):
        self.cam_controller.mpv_log(loglevel, component, message)

    def check_load_timeout(self):
        return self.cam_controller.check_load_timeout()

    def process_update(self, action, data):
        if action == "notify_status_update":
            if "save_variables" in data:
                variables = data["save_variables"].get("variables", {})
                offset_updated = False
                if "nozzle_x_offset_val" in variables:
                    self.x_offset = variables["nozzle_x_offset_val"]
                    offset_updated = True
                if "nozzle_y_offset_val" in variables:
                    self.y_offset = variables["nozzle_y_offset_val"]
                    offset_updated = True

                if offset_updated and hasattr(self, "current_offset_label"):
                    self.current_offset_label.set_markup(self._get_offset_text())
            if "ktamv" in data:
                self._update_calibration_status(data["ktamv"].get("calibration_status", {}))

            for extruder in self._printer.get_tools():
                if f"temp_label_{extruder}" in self.widgets:
                    temp = round(self._printer.get_stat(extruder, "temperature"))
                    target = self._printer.get_stat(extruder, "target")
                    temp_target = round(target) if target else 0
                    temp_state = f"{temp}°/{temp_target}°"
                    self.widgets[f"temp_label_{extruder}"].set_text(temp_state)
            
            if "in_progress_stack" in self.widgets and self.widgets["in_progress_stack"].get_visible_child_name() == "cleaning":
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
                        display_text = _("Cleaning left nozzle")
                    elif current_extruder == "extruder1":
                        display_text = _("Cleaning right nozzle")
                    else:
                        display_text = _("Cleaning nozzles")
                
                if "cleaning_step_label" in self.widgets:
                    self.widgets["cleaning_step_label"].set_text(display_text)

        elif action == "notify_gcode_response":
            cleaned_data = "\n".join([
                line.strip()[2:].strip() if line.strip().startswith(("//", "!!")) else line.strip()
                for line in data.splitlines()
                if line.strip()
            ])
            if "offset from center" in data.lower():
                self.widgets["progress_stack"].set_visible_child_name("success")
                pattern = r"X:([\d.+-]+)\s+Y:([\d.+-]+)"
                match = re.search(pattern, data)
                if match:
                    x_offset = match.group(1)
                    y_offset = match.group(2)
                    self.widgets["progress_data_success"].set_text(
                        f"X: {x_offset}  Y: {y_offset}\n\n{cleaned_data}"
                    )
                    self.bottom_container.set_visible_child_name("finish")
                    if self.finish_action:
                        self._screen._ws.klippy.gcode_script("KTAMV_SAVE_OFFSET")
                        self.countdown = 3
                        self.countdown_running = True
                        self.widgets["btn_print"].set_label(_("Next ({})").format(self.countdown))
                        self.widgets["btn_return"].set_sensitive(False)
                        self.widgets["btn_print"].set_sensitive(True)
                        self.countdown_timer_id = GLib.timeout_add_seconds(1, self._countdown_timer)
            elif any(keyword in data.lower() for keyword in ["pixel", "uv:"]):
                if "in_progress_stack" in self.widgets:
                    self.widgets["in_progress_stack"].set_visible_child_name("default")
                progress_data = self.widgets["progress_data_in_progress"]
                progress_data.set_text(cleaned_data)
                if "progress_stack" in self.widgets:
                    self.widgets["progress_stack"].set_visible_child_name("in_progress")
                    self.widgets["progress_stack"].show_all()

    def activate(self):
        self.init_cam_tip()
        if self.cam_box.get_window():
            self.load_calibrate_camera(self.cam_box)
        res = self._screen.apiclient.send_request("printer/objects/query?ktamv")
        data = res.get('status', {})

        if "ktamv" in data:
            ktamv_status = data["ktamv"]
            calibration_status = ktamv_status.get("calibration_status", {})
            current_state = ktamv_status.get("current_state", "idle")
            if current_state != "idle" or calibration_status.get("status") == "running":
                self.right_container.set_visible_child_name("progress")
            self._update_calibration_status(calibration_status)

    def _update_calibration_status(self, calibration_status):
        if self.right_container.get_visible_child_name() == "progress":
            if calibration_status.get("status") == "error":
                self.finish_action = None
                self.widgets["progress_stack"].set_visible_child_name("fail")
                self.widgets["progress_data_fail"].set_text(calibration_status.get("step_description", "Calibration error"))
                self.bottom_container.set_visible_child_name("fail")
            elif calibration_status.get("current_step") == "COMPLETE":
                self.widgets["progress_stack"].set_visible_child_name("success")
                self.bottom_container.set_visible_child_name("finish")
            else:
                step_description = calibration_status.get("step_description", "Calibration in progress...")
                if "cleaning the nozzle" in step_description.lower():
                    self.widgets["in_progress_stack"].set_visible_child_name("cleaning")
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
                        temp_label = self._create_label(
                            f"{temp}°/{temp_target}°", 
                            halign=Gtk.Align.CENTER
                        )
                        extruder_box.pack_start(temp_label, False, False, 10)
                        self.widgets[f"temp_label_{extruder}"] = temp_label

                        temp_box.pack_start(extruder_box, False, False, 10)
                    
                    temp_box.show_all()
                else:
                    self.widgets["in_progress_stack"].set_visible_child_name("default")
                    
                    if step_description:
                        self.widgets["progress_data_in_progress"].set_text(step_description)
                    
                    if "progress_stack" in self.widgets:
                        self.widgets["progress_stack"].set_visible_child_name("in_progress")
                        self.widgets["progress_stack"].show_all()
    def deactivate(self):
        self.cam_controller.deactivate()

from ks_includes.screen_panel import ScreenPanel
from gi.repository import Gtk, GLib, Pango, Gdk
import logging
import gi
class Panel(ScreenPanel):
    """Eddy sensor calibration panel."""

    def __init__(self, screen, title):
        title = title or _("Eddy calibration")
        super().__init__(screen, title)
        self.widgets = {}
        self.current_temp = 0.0
        self.target_temp = 0.0
        self.accuracy_stddev = 0.0
        self.is_calibrating = self.verifying = False

        title_label = Gtk.Label()
        title_label.set_markup(f"<big>{_('Eddy calibration')}</big>")
        title_label.set_halign(Gtk.Align.CENTER)
        title_label.set_margin_top(10)

        self.right_panel = self.create_right_panel()
        self.right_progress_panel = self.create_right_progress_panel()

        self.right_container = Gtk.Stack()
        self.right_container.add_named(self.right_panel, "default")
        self.right_container.add_named(self.right_progress_panel, "right_progress")
        self.right_container.set_visible_child_name("default")

        self.bottom_container = Gtk.Stack()
        self.bottom_container.add_named(self.bottom_empty_panel(), "empty")
        self.bottom_container.add_named(self.bottom_full_panel(), "full")
        self.bottom_container.add_named(self.bottom_save_panel(), "save")
        self.bottom_container.set_visible_child_name("empty")

        self.top_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.top_hbox.set_halign(Gtk.Align.CENTER)
        self.top_hbox.set_valign(Gtk.Align.CENTER)
        self.top_hbox.set_margin_top(50)
        self.top_hbox.pack_start(self.create_lift_progress_panel(), False, False, 5)
        self.top_hbox.pack_start(self.right_container, False, False, 5)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_left(10)
        main_box.set_margin_right(10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)

        main_box.pack_start(title_label, False, False, 0)
        main_box.pack_start(self.top_hbox, False, False, 0)
        main_box.pack_start(self.bottom_container, False, False, 0)

        self.content.add(main_box)

    def _scaled(self, w_rate: float, h_rate=None):
        if h_rate is None:
            h_rate = w_rate
        try:
            w = int(self._gtk.content_width * w_rate)
            h = int(self._gtk.content_height * h_rate)
        except Exception:
            w, h = 100, 100
        return w, h

    def create_right_panel(self):
        right_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        right_vbox.set_halign(Gtk.Align.CENTER)
        right_vbox.set_valign(Gtk.Align.CENTER)
        right_vbox.set_margin_top(10)
        right_vbox.set_margin_bottom(10)

        top_frame = Gtk.Frame()
        top_frame.set_margin_left(5)

        self.hint_stack = self.create_hint_panel()
        bottom_hbox = self.create_bottom_buttons()
        bottom_hbox.set_margin_top(30)

        right_vbox.pack_start(top_frame, False, False, 0)
        right_vbox.pack_start(self.hint_stack, False, False, 0)
        right_vbox.pack_start(bottom_hbox, False, False, 0)
        return right_vbox

    def create_hint_panel(self):
        hint_stack = Gtk.Stack()

        self.widgets["right_hint"] = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hint_icon = self._gtk.Image(
            "light_hint", *self._scaled(0.04, 0.05))
        hint_icon.set_valign(Gtk.Align.START)

        text = (
            _("Please ensure that the <b>Probe Calibrate</b> has been performed!")
            + "\n\n"
            + _("Click Start to begin the calibration process!")
        )
        self.calibration_hint_ready = Gtk.Label(wrap=True, vexpand=True)
        self.calibration_hint_ready.set_markup(text)
        self.calibration_hint_ready.set_halign(Gtk.Align.CENTER)
        self.calibration_hint_ready.set_name("hint-text")
        self.widgets["right_hint"].pack_start(hint_icon, False, False, 0)
        self.widgets["right_hint"].pack_start(self.calibration_hint_ready, False, False, 0)

        hint_stack.add_named(self.widgets["right_hint"], "ready")

        self.current_temp_label_start = Gtk.Label()
        self.current_temp_label_start.set_markup(f"<span color='#E6BB69'>{self.current_temp}°C</span>")

        self.hint_text1 = Gtk.Label(label=_("bed is warming up..."))
        self.hint_text2 = Gtk.Label(label=_("Ensure your eddy sensor maintains measurement accuracy at any printing temperature."))
        self.hint_text2.set_line_wrap(True)

        self.hint_start_line1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.hint_start_line1.pack_start(self.current_temp_label_start, False, False, 0)
        self.hint_start_line1.pack_start(self.hint_text1, False, False, 0)

        self.calibration_hint_start = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.calibration_hint_start.set_halign(Gtk.Align.CENTER)
        self.calibration_hint_start.pack_start(self.hint_start_line1, False, False, 0)
        self.calibration_hint_start.pack_start(self.hint_text2, False, False, 0)
        hint_stack.add_named(self.calibration_hint_start, "start")
        return hint_stack

    def create_bottom_buttons(self):
        bottom_frame = Gtk.Frame()
        bottom_frame.set_margin_left(5)
        bottom_frame.set_margin_right(5)
        self.widgets["bottom_frame"] = bottom_frame

        bottom_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_hbox.set_halign(Gtk.Align.CENTER)
        self.widgets["bottom_hbox"] = bottom_hbox
        self.widgets["bottom_frame"].add(self.widgets["bottom_hbox"])

        exit_btn = Gtk.Button(label=_("Exit"))
        exit_btn.set_size_request(
            int(self._gtk.content_width * 0.18),
            int(self._gtk.content_height * 0.1)
        )
        self.widgets["bottom_exit_btn"] = exit_btn
        self.widgets["bottom_exit_btn"].get_style_context().add_class("horizontal_togglebuttons_active")
        self.widgets["bottom_exit_btn"].connect("clicked", self.exit_calibration)

        start_btn = Gtk.Button(label=_("Start"))
        start_btn.set_size_request(
            int(self._gtk.content_width * 0.18),
            int(self._gtk.content_height * 0.1)
        )
        self.widgets["bottom_start_btn"] = start_btn
        self.widgets["bottom_start_btn"].get_style_context().add_class("horizontal_togglebuttons_active")
        self.widgets["bottom_start_btn"].connect("clicked", self.start_calibration)

        self.widgets["bottom_hbox"].pack_start(self.widgets["bottom_exit_btn"], False, False, 0)
        self.widgets["bottom_hbox"].pack_start(self.widgets["bottom_start_btn"], False, False, 0)

        return self.widgets["bottom_frame"]

    def _create_btn(self, label, callback):
        btn = self._gtk.Button(label=label)
        btn.set_size_request(int(self._gtk.content_width * 0.18), int(self._gtk.content_height * 0.12))
        btn.connect("clicked", callback)
        return btn

    def bottom_save_panel(self):
        save_single_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        save_single_box.set_halign(Gtk.Align.END)
        save_single_box.set_margin_right(20)
        self.widgets["btn_save_single"] = self._create_btn(_("Save and Reboot"), self.on_save_config)
        save_single_box.pack_start(self.widgets["btn_save_single"], False, False, 0)
        return save_single_box

    def bottom_empty_panel(self):
        empty_box = Gtk.Box()
        return empty_box

    def bottom_full_panel(self):
        full_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        full_box.set_halign(Gtk.Align.END)
        full_box.set_margin_right(20)

        self.widgets["btn_save_full"] = self._create_btn(_("Save and Reboot"), self.on_save_config)
        self.widgets["btn_cancel_full"] = self._create_btn(_("Discard results"), self.on_cancel_config)
        self.widgets["btn_recalibrate"] = self._create_btn(_("Recalibrate"), self.on_recalibrate)

        full_box.pack_start(self.widgets["btn_save_full"], False, False, 0)
        full_box.pack_start(self.widgets["btn_cancel_full"], False, False, 0)
        full_box.pack_start(self.widgets["btn_recalibrate"], False, False, 0)
        return full_box

    def on_save_config(self, widget):
        self._screen._ws.klippy.gcode_script("SAVE_CONFIG")

    def _reset_calibration_state(self):
        self.current_temp = 0.0
        self.accuracy_stddev = 0.0
        self.is_calibrating = False
        self.widgets["bottom_start_btn"].set_sensitive(True)
        self.right_container.set_visible_child_name("default")
        self.hint_stack.set_visible_child_name("ready")
        self.bottom_container.set_visible_child_name("empty")
        self.widgets["progress_stack"].set_visible_child_name("tuning")

    def _start_calibration_state(self):
        self.is_calibrating = True
        self.widgets["bottom_exit_btn"].set_sensitive(False)
        self.widgets["bottom_start_btn"].set_sensitive(False)
        self.hint_stack.set_visible_child_name("start")
        self._screen._ws.klippy.gcode_script("PROBE_EDDY_NG_SETUP")

    def on_cancel_config(self, widget):
        self._reset_calibration_state()

    def on_recalibrate(self, widget):
        self._reset_calibration_state()
        self._start_calibration_state()

    def create_lift_progress_panel(self):
        self.widgets["sensor_image2"] = self._gtk.Image(
            "eddy-2", *self._scaled(0.4, 0.4))
        self.widgets["sensor_image2"].set_valign(Gtk.Align.CENTER)
        self.widgets["sensor_image2"].set_halign(Gtk.Align.CENTER)
        return self.widgets["sensor_image2"]

    def create_right_progress_panel(self):
        self.widgets["progress_stack"] = Gtk.Stack()
        self.widgets["progress_stack"].set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        def _create_icon_title_box(icon_name, title_text):
            width_rate = 0.04
            height_rate = 0.05
            if icon_name ==  "result-good" or icon_name ==  "result-bed":
                width_rate = width_rate * 1.5
                height_rate = height_rate * 1.5
            icon = self._gtk.Image(
                icon_name, *self._scaled(width_rate, height_rate)
            )
            icon.set_valign(Gtk.Align.START)

            title = Gtk.Label()
            title.set_markup(title_text)
            title.set_halign(Gtk.Align.START)
            title.set_line_wrap(True)
            title.set_max_width_chars(28)
            title.set_margin_bottom(20)

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
            hbox.pack_start(icon, False, False, 0)
            hbox.pack_start(title, False, False, 0)
            return hbox

        def _create_basic_stage(icon_name, title_text, desc_text, stack_name):
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            vbox.set_halign(Gtk.Align.CENTER)

            title_box = _create_icon_title_box(icon_name, title_text)
            vbox.pack_start(title_box, False, False, 0)

            desc_label = Gtk.Label(desc_text)
            desc_label.set_halign(Gtk.Align.START)
            desc_label.set_line_wrap(True)
            desc_label.set_max_width_chars(28)
            desc_label.set_margin_top(20)
            vbox.pack_start(desc_label, False, False, 0)

            self.widgets["progress_stack"].add_named(vbox, stack_name)
            return vbox

        _create_basic_stage(
            icon_name="run-waiting",
            title_text=_("Auto-tuning in progress ..."),
            desc_text=_("Sensor is calibrating to collect data and ensure accurate and reliable sensor readings."),
            stack_name="tuning"
        )

        testing_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        testing_vbox.set_halign(Gtk.Align.CENTER)

        testing_title_box1 = _create_icon_title_box(
            "run-finished", _("Auto-tuning completed")
        )
        testing_vbox.pack_start(testing_title_box1, False, False, 0)
        testing_title_box2 = _create_icon_title_box(
            "run-waiting", _("Calibration test in progress ...")
        )
        testing_vbox.pack_start(testing_title_box2, False, False, 0)

        testing_desc = Gtk.Label(_("Verifying sensor accuracy, testing will be automatically completed."))
        testing_desc.set_halign(Gtk.Align.START)
        testing_desc.set_line_wrap(True)
        testing_desc.set_max_width_chars(28)
        testing_desc.set_margin_top(20)
        testing_vbox.pack_start(testing_desc, False, False, 0)

        self.widgets["progress_stack"].add_named(testing_vbox, "testing")
        _create_basic_stage(
            icon_name="result-good",
            title_text=_("<span color='#0066CC' font-size='x-large'>Calibration result: Excellent</span>"),
            desc_text=_("Everything is ready! Click 'Save and Restart' to start your printing."),
            stack_name="report_good"
        )
        _create_basic_stage(
            icon_name="result-bed",
            title_text=_("<span color='#FF0000' font-size='x-large'>Calibration result: Poor</span>"),
            desc_text=_("It is recommended to check if the sensor is securely installed and recalibrate."),
            stack_name="report_bed"
        )
        top_spacer = Gtk.Box()
        top_spacer.set_vexpand(True)

        right_progress_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right_progress_panel.pack_start(top_spacer, True, True, 0)
        right_progress_panel.pack_start(self.widgets["progress_stack"], False, False, 0)
        right_progress_panel.set_halign(Gtk.Align.CENTER)
        right_progress_panel.set_valign(Gtk.Align.CENTER)
        right_progress_panel.set_margin_left(10)

        self.widgets["progress_stack"].set_visible_child_name("tuning")
        return right_progress_panel

    def start_calibration(self, widget):
        text = (
            _("<b>Start the eddy sensor calibrate?</b>\n")
            + "\n\n"
            + _("Please ensure that the <b>Probe Calibrate</b> has been performed!")
        )
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(text)
        buttons = [
            {"name": _("Accept"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-error"},
        ]
        self._gtk.Dialog(_("Calibrate Eddy"), buttons, label, self.confirm_calibration)

    def start_calibration(self, widget):
        logging.info("eddy calibration started")
        self._start_calibration_state()

    def exit_calibration(self, widget=None):
        logging.info("Exit the calibration process of eddy current sensors")
        def confirm_eddy_exit(dialog, response_id):
            self._gtk.remove_dialog(dialog)
            if response_id == Gtk.ResponseType.OK:
                if self._printer.get_stat("manual_probe", "is_active"):
                    self._screen._ws.klippy.gcode_script("ABORT")
                self.is_calibrating = False
                self.exit_calibration()
        if self.is_calibrating:
                title = _("<b>The calibration process is in progress. Are you sure you want to exit?</b>\n")
                label = Gtk.Label(wrap=True, vexpand=True)
                label.set_markup(title)
                buttons = [
                    {"name": _("Accept"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
                    {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-error"},
                ]
                self._gtk.Dialog(_("Eddy calibration"), buttons, label, confirm_eddy_exit)
        else:
            self._screen._menu_go_back()
            self.hint_stack.set_visible_child_name("ready")
            self.bottom_container.set_visible_child_name("empty")

    def verify_calibration(self):
        logging.info("Verifying eddy calibration")
        self.verifying = True
        self.widgets["progress_stack"].set_visible_child_name("testing")
        script = f"G28 Z \nPROBE_EDDY_NG_PROBE_ACCURACY"
        self._screen._ws.klippy.gcode_script(script)

    def process_update(self, action, data):
        if action == "notify_status_update":
            if "heater_bed" in data:
                temp_data = data["heater_bed"]
                if "temperature" in temp_data:
                    self.current_temp = int(temp_data["temperature"])
                    self.update_hint_temp_labels()
                if "target" in temp_data:
                    self.target_temp = int(temp_data["target"])
            for x in self._printer.get_eddy_sensors():
                if x in data:
                    accuracy_stddev = self._printer.get_stat(x, "accuracy_stddev")
                    self.update_calibrate_result(accuracy_stddev)

    def update_calibrate_result(self, stddev):
        if not self.verifying:
            return
        if stddev > 0.0 and stddev != self.accuracy_stddev:
            if stddev < 0.15:
                self.widgets["progress_stack"].set_visible_child_name("report_good")
                self.bottom_container.set_visible_child_name("save")
            else:
                self.widgets["progress_stack"].set_visible_child_name("report_bed")
                self.bottom_container.set_visible_child_name("full")
            self.accuracy_stddev = stddev
            self.verifying = False

    def update_hint_temp_labels(self):
        if not self.is_calibrating:
            return
        if self.current_temp >= self.target_temp or self.target_temp == 0:
            self.widgets["bottom_exit_btn"].set_sensitive(True)
            self.right_container.set_visible_child_name("right_progress")
        if self.hint_stack.get_visible_child_name() == "start" and hasattr(self, "current_temp_label_start"):
            self.current_temp_label_start.set_markup(f"<span color='#E6BB69'>{self.current_temp}°C</span>")

from ks_includes.screen_panel import ScreenPanel
from ks_includes.KlippyGcodes import KlippyGcodes
from gi.repository import Gtk, GLib
import logging

class Panel(ScreenPanel):
    """Dual z calibration panel."""

    def __init__(self, screen, title, **kwargs):
        title = title or _("Z calibration")
        super().__init__(screen, title)
        self.widgets = {}
        self.finish_offset = 0.0
        self.current_extruder = None
        self.is_turning = False
        self.offset_data = [
            (_("Offset Compensation"), "offset_compensation", "0"),
            (_("Current Z Offset"), "offset_val", "0"),
        ]
        self.showing_input_box = False
        self.auto_action = kwargs.get("auto_action", "sample")

        self.countdown_running = False
        self.countdown_timer_id = None
        self.countdown = 0

        self._initialize_ui()

    def _scaled(self, w_rate: float, h_rate=None):
        if h_rate is None:
            h_rate = w_rate
        try:
            return int(self._gtk.content_width * w_rate), int(self._gtk.content_height * h_rate)
        except Exception:
            return 100, 100

    def _initialize_ui(self):
        title_label = Gtk.Label()
        title_label.set_markup(f"<big>{_('Z calibration')}</big>")
        title_label.set_halign(Gtk.Align.CENTER)
        title_label.set_margin_top(10)
        title_label.set_margin_bottom(20)

        self.right_container = Gtk.Stack()
        self.right_container.set_hexpand(True)
        self.right_container.set_halign(Gtk.Align.FILL)
        self.right_container.add_named(self._create_right_default_panel(), "right_default")
        self.right_container.add_named(self._create_right_progress_panel(), "right_progress")
        self.right_container.set_visible_child_name("right_default")
        self.right_container.show_all()

        self.bottom_container = Gtk.Stack()
        self.bottom_container.add_named(Gtk.Box(), "empty")
        self.bottom_container.add_named(self._create_bottom_save_panel(), "save")
        self.bottom_container.set_visible_child_name("empty")

        self.top_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.top_hbox.set_halign(Gtk.Align.CENTER)
        self.top_hbox.set_vexpand(True)

        left_vertical_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        left_vertical_box.set_vexpand(True)
        left_vertical_box.set_valign(Gtk.Align.CENTER)

        left_panel = self._create_left_panel()
        left_vertical_box.pack_start(left_panel, False, False, 0)
        self.top_hbox.pack_start(left_vertical_box, True, True, 0)

        self.right_container.set_valign(Gtk.Align.CENTER)
        self.top_hbox.pack_start(self.right_container, False, False, 20)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_box.set_margin_left(10)
        self.main_box.set_margin_right(10)
        self.main_box.set_margin_bottom(10)
        self.main_box.pack_start(title_label, False, False, 0)
        
        self.top_hbox.set_vexpand(True)
        self.main_box.pack_start(self.top_hbox, True, True, 0)
        
        self.bottom_container.set_vexpand(False)
        self.main_box.pack_start(self.bottom_container, False, False, 0)

        self.content.add(self.main_box)
        
        if self.auto_action == "auto_start":
            self.right_container.set_visible_child_name("right_progress")
            self._start_calibration_state()

    def _create_icon_title_box(self, icon_name, title_text):
        icon = self._gtk.Image(icon_name, *self._scaled(0.05, 0.06))
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

    def _create_button(self, label, style_class=None, callback=None):
        btn = Gtk.Button(label=label)
        btn.set_size_request(int(self._gtk.content_width * 0.18), int(self._gtk.content_height * 0.1))
        if style_class:
            btn.get_style_context().add_class(style_class)
        if callback:
            btn.connect("clicked", callback)
        return btn

    def _create_right_default_panel(self):
        right_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        right_vbox.set_halign(Gtk.Align.CENTER)
        right_vbox.set_valign(Gtk.Align.CENTER)
        right_vbox.set_margin_top(20)
        right_vbox.set_margin_bottom(10)

        hint_text = (
            _("<b>Start the Dual Z offset calibrate?</b>\n\n")
            + _("1.Please ensure that the <b>Probe Calibrate</b> has been performed!\n\n")
            + _("2.Please ensure that the <b>XY Calibrate</b> has been performed!")
        )
        hint_box = self._create_icon_title_box("light_hint", hint_text)

        bottom_buttons_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_buttons_hbox.set_halign(Gtk.Align.CENTER)
        bottom_buttons_hbox.pack_start(self._create_button(_("Exit"), "horizontal_togglebuttons_active", self.exit_calibration), False, False, 0)
        bottom_buttons_hbox.pack_start(self._create_button(_("Start"), "horizontal_togglebuttons_active", self.start_calibration), False, False, 0)

        right_vbox.pack_start(Gtk.Frame(), False, False, 0)
        right_vbox.pack_start(hint_box, False, False, 0)
        right_vbox.pack_start(bottom_buttons_hbox, False, False, 0)
        return right_vbox

    def _create_bottom_save_panel(self):
        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        save_box.set_halign(Gtk.Align.END)
        save_box.set_margin_right(30)
        save_box.set_margin_bottom(30)
        self.widgets["btn_recalibrate"] = self._create_button(_("Recalibrate"), callback=self.on_recalibrate)
        save_box.pack_start(self.widgets["btn_recalibrate"], False, False, 0)
        return save_box

    def _create_left_panel(self):
        left_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        left_vbox.set_halign(Gtk.Align.CENTER)
        left_vbox.set_valign(Gtk.Align.CENTER)

        self.widgets["left_image"] = Gtk.Stack()
        self.widgets["left_image"].add_named(self._create_nozzle_image("dual_z_calibrate-1"), "left_nozzle")
        self.widgets["left_image"].add_named(self._create_nozzle_image("dual_z_calibrate-2"), "right_nozzle")
        self.widgets["left_image"].set_visible_child_name("left_nozzle")

        left_vbox.pack_start(self.widgets["left_image"], False, False, 0)
        left_vbox.pack_start(self._create_data_box(), False, False, 30)
        return left_vbox

    def _create_nozzle_image(self, image_name):
        img = self._gtk.Image(image_name, *self._scaled(0.4, 0.5))
        img.set_valign(Gtk.Align.CENTER)
        img.set_halign(Gtk.Align.CENTER)
        img.set_margin_bottom(20)
        return img

    def _create_data_box(self):
        data_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for label_text, offset_key, value_text in self.offset_data:
            base_key = offset_key.split('_')[1]
            self.widgets[f"{base_key}_label"] = Gtk.Label(label=f"{label_text}:")
            self.widgets[offset_key] = Gtk.Label(label=value_text)
            
            event_box = Gtk.EventBox()
            event_box.add(self.widgets[offset_key])
            event_box.connect("button-release-event", self.change_offset, label_text, self.widgets[offset_key])
            
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
            hbox.set_halign(Gtk.Align.CENTER)
            hbox.set_margin_top(15)
            hbox.pack_start(self.widgets[f"{base_key}_label"], False, False, 0)
            hbox.pack_start(event_box, False, False, 0)
            
            data_box.pack_start(hbox, False, False, 0)
        return data_box

    def _create_right_progress_panel(self):
        self.widgets["progress_stack"] = Gtk.Stack()
        self.widgets["progress_stack"].set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        def _create_basic_stage(icon_name, title_text, desc_text, stack_name):
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            vbox.set_halign(Gtk.Align.CENTER)
            vbox.set_margin_top(30)
            vbox.pack_start(self._create_icon_title_box(icon_name, title_text), False, False, 0)
            
            desc_label = Gtk.Label(desc_text)
            desc_label.set_name(f"desc_label_{stack_name}")
            desc_label.set_halign(Gtk.Align.START)
            desc_label.set_line_wrap(True)
            desc_label.set_max_width_chars(35)
            desc_label.set_margin_top(20)
            self.widgets[f"desc_label_{stack_name}"] = desc_label
            vbox.pack_start(desc_label, False, False, 0)
            
            self.widgets["progress_stack"].add_named(vbox, stack_name)
            return vbox

        def _create_progress_stage(title_data_list, stack_name):
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            vbox.set_halign(Gtk.Align.CENTER)
            for icon_name, title_text in title_data_list:
                vbox.pack_start(self._create_icon_title_box(icon_name, title_text), False, False, 20)
            self.widgets["progress_stack"].add_named(vbox, stack_name)
            return vbox

        common_hint = _("Obtain the nozzle accurate height through multiple precision detections.")
        
        _create_progress_stage([("light_hint", common_hint), ("run-waiting", _("left nozzle probing ..."))], "left_probe")
        _create_progress_stage([("light_hint", common_hint), ("run-finished", _("left nozzle probe completed")), ("run-waiting", _("right nozzle probing ..."))], "right_probe")
        _create_basic_stage("result-good", _("<span color='#0066CC' font-size='x-large'>Probe result: Excellent</span>"), _("Everything is ready! Click [Save] to apply nozzle offset.\n\n"), "report_good")
        _create_basic_stage("result-bed", _("<span color='#FF0000' font-size='x-large'>Probe result: Poor</span>"), "", "report_bed")

        right_progress_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right_progress_panel.pack_start(self.widgets["progress_stack"], False, False, 0)
        right_progress_panel.set_halign(Gtk.Align.CENTER)
        right_progress_panel.set_valign(Gtk.Align.START)
        right_progress_panel.set_margin_left(10)
        right_progress_panel.set_margin_top(10)
        self.widgets["progress_stack"].set_visible_child_name("left_probe")
        
        return right_progress_panel

    def _start_calibration_state(self):
        if self.is_turning:
            return
        self.is_turning = True
        if "progress_stack" in self.widgets:
            self.widgets["progress_stack"].set_visible_child_name("left_probe")
        self.right_container.set_visible_child_name("right_progress")
        self.right_container.queue_draw()
        self.content.queue_draw()
        self._screen._ws.klippy.gcode_script("DUAL_Z_PROBE_CALIBRATE")

    def start_calibration(self, widget):
        logging.info("dual Z offset calibration started")
        self._screen._ws.klippy.gcode_script("CLEAN_NOZZLE")
        self._start_calibration_state()

    def exit_calibration(self, widget=None):
        logging.info("Exit the calibration process of dual Z offset")
        self._screen._menu_go_back()
        self.right_container.set_visible_child_name("right_default")
        self.bottom_container.set_visible_child_name("empty")

    def _countdown_timer(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.widgets["btn_recalibrate"].set_label(_("Next ({})").format(self.countdown))
            return True
        else:
            self._countdown_finish()
            return False
    
    def _countdown_finish(self):
        self.countdown_running = False
        if self.countdown_timer_id:
            GLib.source_remove(self.countdown_timer_id)
            self.countdown_timer_id = None

        self.auto_action = "sample"
        self.right_container.set_visible_child_name("right_default")
        self.bottom_container.set_visible_child_name("empty")
        self.right_container.show_all()
        self._screen.show_panel("offset_manage", print_test=True, remove_current=True)

    def on_recalibrate(self, widget):
        if self.countdown_running:
           self._countdown_finish()
        else:
            self.bottom_container.set_visible_child_name("empty")
            self._start_calibration_state()

    def process_update(self, action, data):
        if action == "notify_status_update":
            if ("toolhead" in data and "extruder" in data["toolhead"] and data["toolhead"]["extruder"] != self.current_extruder):
                self.current_extruder = data["toolhead"]["extruder"]
                if self.is_turning and "progress_stack" in self.widgets:
                    if self.current_extruder == "extruder1":
                        self.widgets["left_image"].set_visible_child_name("right_nozzle")
                        self.widgets["progress_stack"].set_visible_child_name("right_probe")
                    else:
                        self.widgets["left_image"].set_visible_child_name("left_nozzle")
                        self.widgets["progress_stack"].set_visible_child_name("left_probe")

            if "save_variables" in data and "variables" in data["save_variables"]:
                variables = data["save_variables"]["variables"]
                for var in ["nozzle_z_offset_val", "nozzle_z_offset_compensation"]:
                    if var in variables:
                        key = var.split('_z_')[1]
                        logging.info(f"{key} update {var} to {variables[var]}")
                        if key in self.widgets:
                            self.widgets[key].set_text(f"{variables[var]}")

        elif action == "notify_gcode_response" and "final dual-nozzle offset" in data.lower():
            self.is_turning = False
            lines = []
            for line in data.splitlines():
                stripped_line = line.strip()
                if stripped_line.startswith("//"):
                    stripped_line = stripped_line[2:].strip()
                if stripped_line:
                    lines.append(stripped_line)
            
            if len(lines) >= 4:
                lines.insert(3, "")
            display_text = "\n\n".join(lines)

            if "out of range" in data.lower():
                if "desc_label_report_bed" in self.widgets:
                    self.widgets["desc_label_report_bed"].set_text(display_text)
                self.bottom_container.set_visible_child_name("save")
                self.widgets["progress_stack"].set_visible_child_name("report_bed")
            else:
                if "desc_label_report_good" in self.widgets:
                    self.widgets["desc_label_report_good"].set_text(display_text)
                
                final_offset_line = next((line for line in lines if "final dual-nozzle offset" in line.lower()), None)
                if final_offset_line and ": " in final_offset_line:
                    try:
                        self.finish_offset = round(float(final_offset_line.split(": ")[1].strip()), 3)
                    except (IndexError, ValueError):
                        logging.error(f"Failed to parse final offset from line: {final_offset_line}")
                
                self.widgets["progress_stack"].set_visible_child_name("report_good")
                self.bottom_container.set_visible_child_name("save")
                
                if self.auto_action != "sample":
                    self.countdown = 3
                    self.countdown_running = True
                    self.widgets["btn_recalibrate"].set_label(_("Next ({})").format(self.countdown))
                    self.widgets["btn_recalibrate"].set_sensitive(True)

                    self.set_nozzle_offset("nozzle_z_offset_val", self.finish_offset)
                    self.countdown_timer_id = GLib.timeout_add_seconds(1, self._countdown_timer)

    def change_offset(self, widget, event, title_label, offset_label):
        if self.is_turning:
            return
        self._create_input_box(title_label, offset_label)

    def _create_input_box(self, title_label, offset_label):
        current_val = offset_label.get_text()
        title_markup = f"{title_label}<b>{_('Current value:')}</b>{current_val}"
        
        for child in self.content.get_children():
            self.content.remove(child)
            
        lbl = Gtk.Label(label=title_markup, halign=Gtk.Align.START, hexpand=False, use_markup=True)
        
        self.labels["entry"] = Gtk.Entry(hexpand=True)
        self.labels["entry"].connect("focus-in-event", self._screen.show_keyboard)
        
        save_btn = self._gtk.Button("complete", _("Save"), "color3")
        save_btn.set_hexpand(False)
        save_btn.connect("clicked", self.store_value, offset_label)
        
        entry_box = Gtk.Box(spacing=5)
        entry_box.pack_start(self.labels["entry"], True, True, 0)
        entry_box.pack_start(save_btn, False, False, 0)
        
        input_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True, vexpand=True, valign=Gtk.Align.CENTER)
        input_box.pack_start(lbl, True, True, 5)
        input_box.pack_start(entry_box, True, True, 5)
        
        self.content.add(input_box)
        self.labels["entry"].grab_focus_without_selecting()
        self.showing_input_box = True
                   
    def store_value(self, widget, offset_label):
        val_text = self.labels["entry"].get_text()
        try:
            val = round(float(val_text), 3)
            for _, offset_key, _ in self.offset_data:
                if offset_label == self.widgets[offset_key]:
                    self.set_nozzle_offset(f"nozzle_z_{offset_key}", val)
                    break
            if self.showing_input_box:
                self.hide_input_box()
        except ValueError:
            self._screen.show_popup_message(_("Please enter a valid number"))

    def set_nozzle_offset(self, option, value):
        script = KlippyGcodes.set_save_variables(option, value)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set {option}:{value}")

    def hide_input_box(self):
        self._screen.remove_keyboard()
        for child in self.content.get_children():
            self.content.remove(child)
        self.content.add(self.main_box)
        self.content.show_all()
        self.showing_input_box = False

    def activate(self):
        if self.auto_action == "auto_start":
            self._start_calibration_state()

    def back(self):
        if self.showing_input_box:
            self.hide_input_box()
            return True
        else:
            if not self.is_turning:
                if "left_image" in self.widgets:
                    self.widgets["left_image"].set_visible_child_name("left_nozzle")
                self.right_container.set_visible_child_name("right_default")
                self.bottom_container.set_visible_child_name("empty")
            self.auto_action = "sample"
            self._screen._menu_go_back()
            return True

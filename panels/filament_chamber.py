from ks_includes.widgets.keypad import Keypad
from ks_includes.widgets.timerkeypad import TimerKeypad
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from gi.repository import Gtk, GLib, Pango, Gdk
import logging
import gi

gi.require_version("Gtk", "3.0")


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Filament Chamber Settings")
        super().__init__(screen, title)
        self.current_temp = 0
        self.target_temp = 0
        self.remaining_time_seconds = 0
        self.set_duration_seconds = 0

        self.vertical_mode = self._screen.vertical_mode
        self.is_small_screen = self._gtk.content_height < 700

        if self.vertical_mode:
            self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5 if self.is_small_screen else 10)
        else:
            self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0, homogeneous=True)

        margin = 5 if self.is_small_screen else 10
        self.main_box.set_margin_left(margin)
        self.main_box.set_margin_right(margin)
        self.main_box.set_margin_top(margin)
        self.main_box.set_margin_bottom(margin)

        self.control_panel = self.create_control_panel()
        self.display_panel = self.create_display_panel()
        self.keypad_panel = self.create_keypad_panel()

        self.display_container = Gtk.Stack()
        self.display_container.add_named(self.display_panel, "default")
        self.display_container.add_named(self.keypad_panel, "keypad")
        self.display_container.set_visible_child_name("default")

        if self.vertical_mode:
            self.main_box.pack_start(self.control_panel, False, False, 3 if self.is_small_screen else 5)
            self.main_box.pack_start(self.display_container, True, True, 3 if self.is_small_screen else 5)
        else:
            self.main_box.pack_start(self.control_panel, True, True, 5)
            self.main_box.pack_start(self.display_container, True, True, 5)

        self.content.add(self.main_box)

    def get_button_size(self):
        if self.vertical_mode:
            if self.is_small_screen:
                return int(self._gtk.content_width * 0.42), int(self._gtk.content_height * 0.09)
            return int(self._gtk.content_width * 0.42), int(self._gtk.content_height * 0.12)
        else:
            return int(self._gtk.content_width * 0.22), int(self._gtk.content_height * 0.22)

    def get_image_size(self):
        if self.vertical_mode:
            # Small screen uses smaller image
            if self.is_small_screen:
                return int(self._gtk.content_width * 0.55), int(self._gtk.content_height * 0.18)
            return int(self._gtk.content_width * 0.9), int(self._gtk.content_height * 0.35)
        else:
            return int(self._gtk.content_width * 0.45), int(self._gtk.content_height * 0.5)

    def get_indicator_size(self):
        if self.vertical_mode:
            if self.is_small_screen:
                return (90, 90)
            return (120, 120)
        else:
            return (180, 180)

    def get_icon_size(self):
        if self.vertical_mode:
            if self.is_small_screen:
                return (40, 40)
            return (50, 50)
        else:
            return (70, 70)

    def create_control_panel(self):
        if self.is_small_screen:
            spacing = 3
            margin = 3
            inner_margin = 5
        else:
            spacing = 10
            margin = 10
            inner_margin = 15

        control_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        control_box.set_hexpand(True)
        control_box.set_vexpand(not self.vertical_mode)
        control_box.set_margin_left(margin)
        control_box.set_margin_right(margin)
        control_box.set_margin_top(margin)
        control_box.set_margin_bottom(margin)

        temp_timer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing, homogeneous=False)

        btn_width, btn_height = self.get_button_size()

        temp_btn = self._gtk.Button()
        temp_btn.connect("clicked", self.on_temp_clicked)
        temp_btn.get_style_context().add_class("color1")
        temp_btn.set_property("width-request", btn_width)
        temp_btn.set_property("height-request", btn_height)

        temp_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        temp_vbox.set_homogeneous(True)
        temp_btn.add(temp_vbox)

        self.target_temp_label = Gtk.Label(f"{self.target_temp}°C")
        self.target_temp_label.set_halign(Gtk.Align.CENTER)
        self.target_temp_label.set_valign(Gtk.Align.CENTER)
        temp_vbox.pack_start(self.target_temp_label, True, True, 0)

        temp_icon = self._gtk.Image("thermometer")
        temp_icon.set_halign(Gtk.Align.CENTER)
        temp_icon.set_valign(Gtk.Align.CENTER)
        temp_vbox.pack_start(temp_icon, True, True, 0)

        self.current_temp_label = Gtk.Label(f"{self.current_temp}°C")
        self.current_temp_label.set_halign(Gtk.Align.CENTER)
        self.current_temp_label.set_valign(Gtk.Align.CENTER)
        temp_vbox.pack_start(self.current_temp_label, True, True, 0)

        timer_btn = self._gtk.Button()
        timer_btn.connect("clicked", self.on_timer_clicked)
        timer_btn.get_style_context().add_class("color2")
        timer_btn.set_property("width-request", btn_width)
        timer_btn.set_property("height-request", btn_height)

        timer_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        timer_vbox.set_homogeneous(True)
        timer_btn.add(timer_vbox)

        self.set_timer_label = Gtk.Label("--:--:--")
        self.set_timer_label.set_halign(Gtk.Align.CENTER)
        self.set_timer_label.set_valign(Gtk.Align.CENTER)
        timer_vbox.pack_start(self.set_timer_label, True, True, 0)

        timer_icon = self._gtk.Image("countdown")
        timer_icon.set_halign(Gtk.Align.CENTER)
        timer_icon.set_valign(Gtk.Align.CENTER)
        timer_vbox.pack_start(timer_icon, True, True, 0)

        self.remaining_timer_label = Gtk.Label("--:--:--")
        self.remaining_timer_label.set_halign(Gtk.Align.CENTER)
        self.remaining_timer_label.set_valign(Gtk.Align.CENTER)
        timer_vbox.pack_start(self.remaining_timer_label, True, True, 0)

        temp_timer_box.pack_start(temp_btn, False, False, 0)
        temp_timer_box.pack_start(timer_btn, False, False, 0)
        temp_timer_box.set_halign(Gtk.Align.CENTER)

        auto_close_frame = Gtk.Frame()
        auto_close_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
        auto_close_box.set_margin_left(inner_margin)
        auto_close_box.set_margin_right(inner_margin)
        auto_close_box.set_margin_top(inner_margin)
        auto_close_box.set_margin_bottom(inner_margin)

        switch_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5 if self.is_small_screen else 10)

        auto_close_title = Gtk.Label()
        auto_close_title.set_name("title-bold")
        text = _("Auto-Off After Print")
        auto_close_title.set_markup(f'<span weight="bold" size="small">{text}</span>')
        auto_close_title.set_halign(Gtk.Align.START)
        switch_hbox.pack_start(auto_close_title, False, False, 0)

        self.auto_close_switch = Gtk.Switch()
        self.auto_close_switch.set_active(False)
        self.auto_close_switch.connect("notify::active", self.on_auto_close_toggled)
        self.auto_close_switch.set_halign(Gtk.Align.END)
        switch_hbox.pack_end(self.auto_close_switch, False, False, 0)

        auto_close_box.pack_start(switch_hbox, True, True, 0)
        auto_close_frame.add(auto_close_box)

        control_box.pack_start(temp_timer_box, False, False, 0)
        control_box.pack_start(auto_close_frame, False, False, 0)

        if not self.vertical_mode:
            spacer = Gtk.Box()
            spacer.set_vexpand(True)
            control_box.pack_start(spacer, True, True, 0)

        return control_box

    def format_time_display(self, seconds):
        if seconds <= 0:
            return "--:--:--"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining_seconds = seconds % 60

        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"

    def create_display_panel(self):
        if self.is_small_screen:
            spacing = 3
            margin = 3
            inner_margin = 5
        else:
            spacing = 10
            margin = 10
            inner_margin = 15

        display_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        display_box.set_hexpand(True)
        display_box.set_vexpand(True)
        display_box.set_margin_left(margin)
        display_box.set_margin_right(margin)
        display_box.set_margin_top(margin)
        display_box.set_margin_bottom(margin)

        info_frame = Gtk.Frame()
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1 if self.is_small_screen else 2)
        info_box.set_margin_left(inner_margin)
        info_box.set_margin_right(inner_margin)
        info_box.set_margin_top(inner_margin)
        info_box.set_margin_bottom(inner_margin)

        info_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1 if self.is_small_screen else 2)
        info_title_box.set_halign(Gtk.Align.START)

        hint_icon_size = min(self._gtk.content_width, self._gtk.content_height) * (0.015 if self.is_small_screen else 0.025)
        hint_icon = self._gtk.Image("light_hint", hint_icon_size, hint_icon_size)
        hint_icon.set_valign(Gtk.Align.START)
        info_title_box.pack_start(hint_icon, False, False, 0)

        info_title = Gtk.Label()
        text = _("Usage Tips")
        info_title.set_markup(f"<b>{text}</b>")
        info_title.set_halign(Gtk.Align.START)
        info_title_box.pack_start(info_title, False, False, 0)

        info_text1 = Gtk.Label(_("1. Keep filament dry to prevent print failures and nozzle clogs."))
        info_text1.set_halign(Gtk.Align.START)
        info_text1.set_line_wrap(True)

        info_text2 = Gtk.Label(_("2. Dry filament periodically when humidity exceeds 50%."))
        info_text2.set_halign(Gtk.Align.START)
        info_text2.set_line_wrap(True)

        info_text3 = Gtk.Label(_("3. Always set the proper temperature for your filament!"))
        info_text3.set_halign(Gtk.Align.START)
        info_text3.set_line_wrap(True)

        info_box.pack_start(info_title_box, False, False, 0)
        info_box.pack_start(info_text1, False, False, 0)
        info_box.pack_start(info_text2, False, False, 0)
        info_box.pack_start(info_text3, False, False, 0)
        info_frame.add(info_box)

        img_width, img_height = self.get_image_size()
        indicator_width, indicator_height = self.get_indicator_size()
        icon_width, icon_height = self.get_icon_size()

        overlay_frame = Gtk.Frame()
        overlay_frame.set_vexpand(True)

        overlay = Gtk.Overlay()

        self.background_image = self._gtk.Image("filament_chamber", img_width, img_height)
        self.background_image.set_halign(Gtk.Align.CENTER)
        self.background_image.set_valign(Gtk.Align.CENTER)
        self.background_image.set_hexpand(False)
        self.background_image.set_vexpand(False)

        self.temp_indicator = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.temp_indicator.set_size_request(indicator_width, indicator_height)
        self.temp_indicator.set_halign(Gtk.Align.START)
        self.temp_indicator.set_valign(Gtk.Align.START)
        self.temp_indicator.set_margin_top(5)
        self.temp_indicator.set_margin_left(5)

        indicator_overlay = Gtk.Overlay()

        circle_bg = Gtk.DrawingArea()
        circle_bg.set_size_request(indicator_width, indicator_height)
        circle_bg.connect("draw", self.on_draw_circle_background)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        content_box.set_halign(Gtk.Align.CENTER)
        content_box.set_valign(Gtk.Align.CENTER)

        self.thermometer_icon = self._gtk.Image("thermometer_cool", icon_width, icon_height)

        self.temp_display_label = Gtk.Label(f"{self.current_temp}°C")
        self.temp_display_label.set_markup(f"<span weight='bold' size='medium'>{self.current_temp}°C</span>")

        content_box.pack_start(self.thermometer_icon, False, False, 0)
        content_box.pack_start(self.temp_display_label, False, False, 0)

        indicator_overlay.add(circle_bg)
        indicator_overlay.add_overlay(content_box)

        self.temp_indicator.pack_start(indicator_overlay, True, True, 0)

        overlay.add(self.background_image)
        overlay.add_overlay(self.temp_indicator)

        overlay_frame.add(overlay)

        display_box.pack_start(info_frame, False, False, 0)
        display_box.pack_start(overlay_frame, True, True, 0)

        return display_box

    def on_draw_circle_background(self, widget, cr):
        allocation = widget.get_allocation()
        width = allocation.width
        height = allocation.height

        circle_x = width / 2
        circle_y = height / 2
        circle_radius = min(width, height) * 0.4

        line_width = 3

        cr.set_source_rgba(0.5, 0.5, 0.5, 0.2)
        cr.arc(circle_x, circle_y, circle_radius + line_width, 0, 2 * 3.14159)
        cr.fill()

        if self.target_temp == 0:
            cr.set_source_rgb(0.2, 0.592, 0.8)
        else:
            cr.set_source_rgb(0.902, 0.733, 0.412)

        cr.set_line_width(line_width)
        cr.arc(circle_x, circle_y, circle_radius, 0, 2 * 3.14159)
        cr.stroke()
        self.update_indicator_content_colors()

        return True

    def update_indicator_content_colors(self):
        if self.target_temp == 0:
            color_hex = "#3397CC"
        else:
            color_hex = "#E6BB69"
        if hasattr(self, 'temp_display_label'):
            self.temp_display_label.set_markup(
                f"<span weight='bold' size='medium' color='{color_hex}'>{self.current_temp}°C</span>"
            )

    def update_background_and_indicator(self):
        if hasattr(self, 'background_image') and hasattr(self, 'thermometer_icon'):
            img_width, img_height = self.get_image_size()
            icon_width, icon_height = self.get_icon_size()

            if self.target_temp == 0:
                new_pixbuf = self._gtk.Image("filament_chamber", img_width, img_height).get_pixbuf()
                self.background_image.set_from_pixbuf(new_pixbuf)
                new_pixbuf = self._gtk.Image("thermometer_cool", icon_width, icon_height).get_pixbuf()
                self.thermometer_icon.set_from_pixbuf(new_pixbuf)
            else:
                new_pixbuf = self._gtk.Image("filament_chamber_heat", img_width, img_height).get_pixbuf()
                self.background_image.set_from_pixbuf(new_pixbuf)
                new_pixbuf = self._gtk.Image("thermometer_heat", icon_width, icon_height).get_pixbuf()
                self.thermometer_icon.set_from_pixbuf(new_pixbuf)

            self.temp_indicator.queue_draw()
            self.update_indicator_content_colors()

    def create_keypad_panel(self):
        keypad_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        keypad_box.set_hexpand(True)
        keypad_box.set_vexpand(True)
        keypad_box.set_margin_left(15)
        keypad_box.set_margin_right(15)
        keypad_box.set_margin_top(20)
        keypad_box.set_margin_bottom(20)

        self.keypad_title = Gtk.Label("")
        self.keypad_title.get_style_context().add_class("section-title")
        self.keypad_title.set_halign(Gtk.Align.CENTER)

        self.temp_keypad = Keypad(self._screen, self.on_temp_set, None, self.hide_keypad)
        self.timer_keypad = TimerKeypad(self._screen, self.on_timer_set, self.hide_keypad)

        self.keypad_stack = Gtk.Stack()
        self.keypad_stack.add_named(self.temp_keypad, "temp")
        self.keypad_stack.add_named(self.timer_keypad, "timer")

        keypad_box.pack_start(self.keypad_title, False, False, 0)
        keypad_box.pack_start(self.keypad_stack, True, True, 0)

        return keypad_box

    def on_temp_clicked(self, button):
        logging.info(f"Temperature button clicked, current: {self.current_temp}°C")
        self.keypad_title.set_text(_("Set Target Temp(°C)"))
        self.keypad_stack.set_visible_child_name("temp")
        self.temp_keypad.clear()
        self.display_container.set_visible_child_name("keypad")

    def on_timer_clicked(self, button):
        self.keypad_title.set_text(_("Set Countdown (Hours)"))
        self.keypad_stack.set_visible_child_name("timer")
        self.timer_keypad.clear()
        self.display_container.set_visible_child_name("keypad")

    def on_temp_set(self, temp):
        try:
            if "heater_filament_chamber" in self._printer.get_temp_devices():
                max_temp = int(
                    float(self._printer.get_config_section("heater_filament_chamber")["max_temp"])
                )
                if temp > max_temp:
                    temp = max_temp
                    self._screen.show_popup_message(
                        _("Can't set above the maximum:") + f" {temp}"
                    )
                    return
                self._screen._ws.klippy.set_heater_temp_time(
                    "heater_filament_chamber", temp, self.set_duration_seconds)
                self.target_temp = temp

                if hasattr(self, 'target_temp_label'):
                    self.target_temp_label.set_text(f"{temp}°C")

                self.update_background_and_indicator()

                logging.info(f"Set filament chamber temperature to {temp}°C")

        except (ValueError, TypeError):
            logging.error(f"Invalid temperature value: {temp}")

        self.hide_keypad()

    def on_timer_set(self, hours):
        try:
            hours = float(hours)
            if hours < 0:
                hours = 0
            elif hours > 999:
                hours = 999

            seconds = int(hours * 3600)
            if "heater_filament_chamber" in self._printer.get_temp_devices():
                if self.target_temp > 0:
                    temp = self.target_temp
                    self._screen._ws.klippy.set_heater_temp_time(
                        "heater_filament_chamber", temp, seconds)
                    self.set_duration_seconds = seconds
                    self.remaining_time_seconds = seconds
                else:
                    self.set_duration_seconds = seconds
                    self.remaining_time_seconds = seconds
                    if hasattr(self, 'set_timer_label'):
                        self.set_timer_label.set_text(
                            f"{self.format_time_display(self.set_duration_seconds)}")
        except (ValueError, TypeError):
            logging.error(f"Invalid timer value: {hours}")

        self.hide_keypad()

    def hide_keypad(self, widget=None):
        self.display_container.set_visible_child_name("default")

    def on_auto_close_toggled(self, switch, gparam):
        is_active = switch.get_active()
        script = KlippyGcodes.set_save_variables("filament_chamber_auto_cool", is_active)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set filament_chamber_auto_cool: {is_active}")

    def process_update(self, action, data):
        if action == "notify_status_update":
            if "heater_filament_chamber" in data:
                temp_data = data["heater_filament_chamber"]
                if "temperature" in temp_data:
                    self.current_temp = int(temp_data["temperature"])
                    if hasattr(self, 'current_temp_label'):
                        self.current_temp_label.set_text(f"{self.current_temp}°C")
                if "target" in temp_data:
                    self.target_temp = int(temp_data["target"])
                    if hasattr(self, 'target_temp_label'):
                        self.target_temp_label.set_text(f"{self.target_temp}°C")
                    self.update_background_and_indicator()

                if "auto_turnoff" in temp_data:
                    auto_turnoff = temp_data["auto_turnoff"]
                    if auto_turnoff is None:
                        self.set_duration_seconds = 0
                        self.remaining_time_seconds = 0
                    else:
                        self.set_duration_seconds = auto_turnoff.get("set_duration", 0)
                        self.remaining_time_seconds = auto_turnoff.get("remaining_time", 0)

                    if hasattr(self, 'set_timer_label'):
                        self.set_timer_label.set_text(
                            f"{self.format_time_display(self.set_duration_seconds)}")
                    if hasattr(self, 'remaining_timer_label'):
                        self.remaining_timer_label.set_text(
                            f"{self.format_time_display(self.remaining_time_seconds)}")
            if "save_variables" in data:
                if "variables" in data["save_variables"]:
                    variables = data["save_variables"]["variables"]
                    if "filament_chamber_auto_cool" in variables:
                        self.auto_close_switch.set_active(
                            variables["filament_chamber_auto_cool"])

import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib
from contextlib import suppress
from ks_includes.screen_panel import ScreenPanel
from ks_includes.KlippyGtk import find_widget
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.align_camera import CameraController

class Panel(ScreenPanel):
    """Alignment datum calibration panel."""
    def __init__(self, screen, title, **kwargs):
        title = title or _("Datum Align")
        super().__init__(screen, title)
        self.widgets = {}
        self.distance = "1"
        self.distances = ["0.1", "0.5", "1"]
        self.mode = "check"
        self.start_btn_active = kwargs.get("start_btn_active", False)
        
        # Initialize camera controller
        self.cam_controller = CameraController(self)
        
        self._init_widgets()
        self._init_containers()
        self._build_layout()
        logging.info(f"start_btn_active: {self.start_btn_active}")
        self.start_btn.set_sensitive(self.start_btn_active)

        self.cam_controller.init_cam_tip()
        GLib.timeout_add_seconds(1, self.cam_controller.load_camera)

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
    
    def _create_button(self, label, icon, color, callback, **kwargs):
        """Create a button with consistent size"""
        btn = self._gtk.Button(icon, label, color)
        btn.set_size_request(*self._scaled(0.2, 0.1))
        btn.connect("clicked", callback)
        for key, val in kwargs.items():
            if hasattr(btn, f"set_{key}"):
                getattr(btn, f"set_{key}")(val)
        return btn

    def _init_widgets(self):
        # Title label
        self.title_label = self._create_label(
            _("datum point alignment"),
            markup=True,
            halign=Gtk.Align.CENTER,
            margin_top=10
        )
        
        # Camera box
        self.cam_box = self._create_cam_display_area()
        
        # Distance buttons (分度值)
        # Create a vertical box to hold label and buttons
        self.distance_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.distance_box.set_no_show_all(True)  # Ensure it stays hidden until explicitly shown
        self.distance_box.hide()
        
        # Add label above distance buttons
        self.distance_label = self._create_label(_("Move Distance (mm)"), halign=Gtk.Align.CENTER)
        self.distance_box.pack_start(self.distance_label, False, False, 0)
        
        # Create grid for distance buttons with homogeneous sizing
        self.distance_grid = Gtk.Grid()
        self.distance_grid.set_hexpand(True)
        self.distance_grid.set_column_homogeneous(True)
        self.distance_grid.set_row_homogeneous(True)
        self.distance_grid.set_halign(Gtk.Align.CENTER)
        self.distance_grid.set_valign(Gtk.Align.CENTER)
        
        for i, distance in enumerate(self.distances):
            btn = self._gtk.Button(label=distance)
            btn.set_direction(Gtk.TextDirection.LTR)
            btn.connect("clicked", self.change_distance, distance)
            # Set minimum width to make buttons longer
            btn.set_size_request(150, -1)
            ctx = btn.get_style_context()
            ctx.add_class("horizontal_togglebuttons")
            if distance == self.distance:
                ctx.add_class("horizontal_togglebuttons_active")
            self.distance_grid.attach(btn, i, 0, 1, 1)
            # Use unique widget name for camera distance buttons
            self.widgets[f"cam_distance_{distance}"] = btn
        
        # Add grid to box
        self.distance_box.pack_start(self.distance_grid, True, True, 0)
        
        # Control buttons grid (上下左右 + z+ z-)
        self.control_grid = Gtk.Grid(
            column_homogeneous=True,
            row_homogeneous=True,
            column_spacing=5,
            row_spacing=5
        )
        
        # Create control buttons with proper formatting
        self.control_buttons = {
            "y+": self._gtk.Button("arrow-up", "Y+", "color3"),
            "y-": self._gtk.Button("arrow-down", "Y-", "color3"),
            "x-": self._gtk.Button("arrow-left", "X-", "color3"),
            "x+": self._gtk.Button("arrow-right", "X+", "color3"),
            "z+": self._gtk.Button("arrow-up", "Z+", "color2"),
            "z-": self._gtk.Button("arrow-down", "Z-", "color2"),
            "datum": self._gtk.Button("home", _("Datum"), "color1")
        }
        
        # Connect buttons to callbacks
        for name, btn in self.control_buttons.items():
            btn.connect("clicked", self.on_control_click, name)
            self.widgets[name] = btn
        
        # Layout control buttons in grid
        self.control_grid.attach(self.control_buttons["y+"], 1, 0, 1, 1)
        self.control_grid.attach(self.control_buttons["x-"], 0, 1, 1, 1)
        self.control_grid.attach(self.control_buttons["datum"], 1, 1, 1, 1)
        self.control_grid.attach(self.control_buttons["x+"], 2, 1, 1, 1)
        self.control_grid.attach(self.control_buttons["y-"], 1, 2, 1, 1)
        self.control_grid.attach(self.control_buttons["z+"], 3, 0, 1, 1)
        self.control_grid.attach(self.control_buttons["z-"], 3, 2, 1, 1)
        
        # Right side content for check mode
        self.check_right_content = self._create_check_right_content()
        
        # Right side content for calibrate mode
        self.calibrate_right_content = self.control_grid
        
        # Create stack for right side content
        self.right_stack = Gtk.Stack()
        self.right_stack.add_named(self.check_right_content, "check")
        self.right_stack.add_named(self.calibrate_right_content, "calibrate")
        self.right_stack.set_visible_child_name("check")
        
        # Create bottom stack to manage different mode footers
        self.bottom_stack = Gtk.Stack()
        
        # Bottom content for check mode - centered buttons
        self.check_bottom_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=15,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            margin_bottom=10
        )
        
        # Create check mode buttons
        self.check_btn = self._create_button(_("Position check"), None, f"color1", self.on_position_check)
        self.start_btn = self._create_button(_("Start calibration"), None, f"color3", self.on_start_calibrate)
        self.cancel_btn = self._create_button(_("Cancel"), None, f"color2", self.on_cancel)
        
        # Add buttons to check bottom box
        self.check_bottom_box.pack_start(self.check_btn, False, False, 0)
        self.check_bottom_box.pack_start(self.start_btn, False, False, 0)
        self.check_bottom_box.pack_start(self.cancel_btn, False, False, 0)
        
        # Bottom content for calibrate mode - split into left and right
        self.calibrate_bottom_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            margin_bottom=10
        )
        
        # Left section - distance buttons (aligned to bottom)
        calibrate_left_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.END
        )
        # Add label above distance buttons
        calibrate_left_box.pack_start(self._create_label(_("Move Distance (mm)"), halign=Gtk.Align.CENTER), False, False, 0)
        
        # Distance buttons (分度值) - use grid for better homogeneous sizing
        self.distance_buttons = Gtk.Grid()
        self.distance_buttons.set_hexpand(True)
        self.distance_buttons.set_column_homogeneous(True)
        self.distance_buttons.set_row_homogeneous(True)
        self.distance_buttons.set_halign(Gtk.Align.CENTER)
        self.distance_buttons.set_valign(Gtk.Align.CENTER)
        
        for i, distance in enumerate(self.distances):
            btn = self._gtk.Button(label=distance)
            btn.set_direction(Gtk.TextDirection.LTR)
            btn.connect("clicked", self.change_distance, distance)
            # Set minimum width to make buttons longer
            btn.set_size_request(150, -1)
            ctx = btn.get_style_context()
            ctx.add_class("horizontal_togglebuttons")
            if distance == self.distance:
                ctx.add_class("horizontal_togglebuttons_active")
            self.distance_buttons.attach(btn, i, 0, 1, 1)
            # Use unique widget name for bottom distance buttons
            self.widgets[f"bottom_distance_{distance}"] = btn
        
        calibrate_left_box.pack_start(self.distance_buttons, True, True, 0)
        
        # Right section - function buttons (aligned to bottom)
        calibrate_right_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=15,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.END
        )
        # Create calibrate mode buttons
        self.save_btn = self._create_button(_("Save settings"), None, f"color3", self.on_save_settings)
        self.cancel_cal_btn = self._create_button(_("Cancel"), None, f"color2", self.on_cancel_calibrate)
        # Add buttons to right box
        calibrate_right_box.pack_start(self.save_btn, False, False, 0)
        calibrate_right_box.pack_start(self.cancel_cal_btn, False, False, 0)
        
        # Add left and right sections to calibrate bottom box
        self.calibrate_bottom_box.pack_start(calibrate_left_box, True, True, 0)
        self.calibrate_bottom_box.pack_start(calibrate_right_box, True, True, 0)
        
        # Add both bottom layouts to stack
        self.bottom_stack.add_named(self.check_bottom_box, "check")
        self.bottom_stack.add_named(self.calibrate_bottom_box, "calibrate")
        self.bottom_stack.set_visible_child_name("check")

    def _create_cam_display_area(self):
        return self.cam_controller.create_camera_display_area()

    def _create_check_right_content(self):
        # Create right side content for check mode
        right_vbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=20,
            valign=Gtk.Align.CENTER
        )
        
        # Example images grid
        example_grid = Gtk.Grid(
            column_homogeneous=True,
            row_homogeneous=True,
            column_spacing=5
        )
        
        def _create_image_box(icon_name, label_text, status_text):
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            
            # Create EventBox for click-to-zoom functionality
            event_box = Gtk.EventBox()
            event_box.set_halign(Gtk.Align.CENTER)
            event_box.set_valign(Gtk.Align.CENTER)
            event_box.set_size_request(*self._scaled(0.15, 0.15))
            
            # Create image
            image = self._gtk.Image(icon_name, *self._scaled(0.12, 0.12))
            event_box.add(image)
            
            # Connect click event
            event_box.connect("button-press-event", self.on_example_image_click, icon_name)
            
            # Add to vbox
            vbox.pack_start(event_box, False, False, 0)
            vbox.pack_start(self._create_label(label_text, markup=True, halign=Gtk.Align.CENTER), False, False, 0)
            vbox.pack_start(self._create_label(status_text, markup=True, halign=Gtk.Align.CENTER), False, False, 0)
            
            return vbox
        
        # Correct example
        correct_box = _create_image_box("nozzle-photo1", _("<span color='green' font-size='small'>Correct</span>"), "✓")
        example_grid.attach(correct_box, 0, 0, 1, 1)
        
        # Wrong example 1 
        wrong1_box = _create_image_box("nozzle-photo2", _("<span color='red' font-size='small'>Nozzle not clean</span>"), "✗")
        example_grid.attach(wrong1_box, 1, 0, 1, 1)
        
        # Wrong example 2
        wrong2_box = _create_image_box("nozzle-photo3", _("<span color='red' font-size='small'>Position offset</span>"), "✗")
        example_grid.attach(wrong2_box, 2, 0, 1, 1)
        
        # Instructions text in multiple labels
        instructions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        instructions_box.set_halign(Gtk.Align.START)
        
        # Header label
        header_label = self._create_label(
            _("Notes:"),
            markup=True,
            halign=Gtk.Align.START
        )
        instructions_box.pack_start(header_label, False, False, 0)
        
        # Item 1
        item1_label = self._create_label(
            _("1. Advanced setting: Use only when necessary " \
              "(e.g., nozzle/hotend replacement, post-collision, " \
              "or mechanical zero adjustment)."),
            halign=Gtk.Align.START,
            xalign=0.0,
            line_wrap=True,
            max_width_chars=40,
            line_wrap_mode=Pango.WrapMode.WORD
        )
        item1_label.override_font(Pango.FontDescription("small"))
        item1_label.set_margin_start(0)
        instructions_box.pack_start(item1_label, False, False, 0)
        
        # Item 2
        item2_label = self._create_label(
            _("2. Follow the image guide strictly during calibration " \
              "to avoid damaging the vision module or " \
              "causing print errors."),
            halign=Gtk.Align.START,
            xalign=0.0,
            line_wrap=True,
            max_width_chars=40,
            line_wrap_mode=Pango.WrapMode.WORD
        )
        item2_label.override_font(Pango.FontDescription("small"))
        item2_label.set_margin_start(0)
        instructions_box.pack_start(item2_label, False, False, 0)
        
        # Item 3
        item3_label = self._create_label(
            _("3. If you have any questions, please contact customer service."),
            halign=Gtk.Align.START,
            xalign=0.0,
            line_wrap=True,
            max_width_chars=40,
            line_wrap_mode=Pango.WrapMode.WORD
        )
        item3_label.override_font(Pango.FontDescription("small"))
        item3_label.set_margin_start(0)
        instructions_box.pack_start(item3_label, False, False, 0)
        
        # Add all to right vbox
        right_vbox.pack_start(example_grid, False, False, 0)
        right_vbox.pack_start(instructions_box, False, False, 0)
        
        return right_vbox

    def _init_containers(self):
        # Main vertical box for entire panel
        self.main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
            margin_left=10,
            margin_right=10
        )
        
        # Top section: Title
        top_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top_section.pack_start(self.title_label, False, False, 0)
        
        # Middle section: Camera and content
        middle_section = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            margin_top=20
        )
        
        # Left side: Create a container for camera (with optional distance buttons)
        self.left_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER
        )
        self.left_container.pack_start(self.cam_box, False, False, 0)
        self.left_container.pack_start(self.distance_box, False, False, 10)
        
        # Right side: Content stack
        right_section = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            valign=Gtk.Align.CENTER
        )
        right_section.pack_start(self.right_stack, True, True, 0)
        
        # Add left and right sections to middle section
        middle_section.pack_start(self.left_container, False, False, 10)
        middle_section.pack_start(right_section, True, True, 10)
        
        # Bottom section: Button stack
        self.bottom_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.bottom_section.pack_start(self.bottom_stack, True, True, 0)
        
        # Add all sections to main box
        self.main_box.pack_start(top_section, False, False, 0)
        self.main_box.pack_start(middle_section, True, True, 0)
        self.main_box.pack_start(self.bottom_section, False, False, 0)

    def _build_layout(self):
        self.content.add(self.main_box)

    def _create_cam_display_area(self):
        return self.cam_controller.create_camera_display_area()

    def init_cam_tip(self):
        self.cam_controller.init_cam_tip()

    # Button callbacks
    def on_position_check(self, widget):
        self.start_btn.set_sensitive(True)
        self._screen._ws.klippy.gcode_script("KTAMV_MOVE_DATUM_CENTER")
        logging.info("Position check clicked")

    def on_start_calibrate(self, widget):
        # Switch to calibration mode
        self.mode = "calibrate"
        self.title_label.set_markup(_("Datum Calibration"))
        
        # Switch right content to control grid
        self.right_stack.set_visible_child_name("calibrate")
        
        # Switch bottom buttons using stack
        self.bottom_stack.set_visible_child_name("calibrate")

    def on_cancel(self, widget):
        # Handle cancel button click
        self._screen._menu_go_back()

    def on_cancel_calibrate(self, widget):
        # Switch back to check mode
        self.mode = "check"
        self.title_label.set_markup(_("Datum Align"))
        
        # Switch right content back to check content
        self.right_stack.set_visible_child_name("check")
        
        # Switch bottom buttons using stack
        self.bottom_stack.set_visible_child_name("check")

    def on_save_settings(self, widget):
        self._screen._ws.klippy.gcode_script("KTAMV_SET_CENTER_OFFSET")
        self.on_cancel_calibrate(widget)

    def on_control_click(self, widget, button_name):
        logging.info(f"Control button clicked: {button_name}") 
        # Special handling for home/Datum button
        if button_name == "datum":
            self._screen._ws.klippy.gcode_script("KTAMV_MOVE_DATUM_CENTER USE_OFFSET=0")
            return

        axis = button_name[0]
        direction = button_name[1]
        
        axis = axis.lower()
        if (
            self._config.get_config()["main"].getboolean(f"invert_{axis}", False)
            and axis != "z"
        ):
            direction = "-" if direction == "+" else "+"
        
        dist = f"{direction}{self.distance}"
        config_key = "move_speed_z" if axis == "z" else "move_speed_xy"
        if axis == "z":
            # Simple z safety check (can be enhanced if needed)
            speed = (
                None
                if self.ks_printer_cfg is None
                else self.ks_printer_cfg.getint(config_key, None)
            )
        else:
            speed = (
                None
                if self.ks_printer_cfg is None
                else self.ks_printer_cfg.getint(config_key, None)
            )
        
        if speed is None:
            # Get max velocity from printer config if available
            try:
                printer_cfg = self._printer.get_config_section("printer")
                if printer_cfg:
                    max_velocity = max(int(float(printer_cfg["max_velocity"])), 2)
                    max_z_velocity = max_velocity
                    if "max_z_velocity" in printer_cfg:
                        max_z_velocity = max(int(float(printer_cfg["max_z_velocity"])), 2)
                    speed = max_z_velocity if axis == "z" else max_velocity
                else:
                    speed = 10
            except Exception:
                speed = 10
        
        speed = 60 * max(1, speed)
        script = f"{KlippyGcodes.MOVE_RELATIVE}\nG0 {axis}{dist} F{speed}"
        self._screen._send_action(widget, "printer.gcode.script", {"script": script})
        if self._printer.get_stat("gcode_move", "absolute_coordinates"):
            self._screen._ws.klippy.gcode_script("G90")

    def change_distance(self, widget, distance):
        # Update active distance button for both camera and bottom buttons
        for dist in self.distances:
            # Update camera distance buttons
            if f"cam_distance_{dist}" in self.widgets:
                ctx = self.widgets[f"cam_distance_{dist}"].get_style_context()
                ctx.remove_class("horizontal_togglebuttons_active")
            # Update bottom distance buttons
            if f"bottom_distance_{dist}" in self.widgets:
                ctx = self.widgets[f"bottom_distance_{dist}"].get_style_context()
                ctx.remove_class("horizontal_togglebuttons_active")
        
        # Set active state for clicked button
        ctx = widget.get_style_context()
        ctx.add_class("horizontal_togglebuttons_active")
        self.distance = distance
        logging.info(f"Move distance changed to: {distance}")

    def activate(self):
        # Re-initialize camera when panel is activated
        self.start_btn.set_sensitive(self.start_btn_active)
        self.cam_controller.init_cam_tip()
        if self.cam_box.get_window():
            self.cam_controller.load_camera(self.cam_box)
    
    def deactivate(self):
        self.cam_controller.deactivate()
        # Close any open image dialogs
        if hasattr(self, 'image_dialog') and self.image_dialog is not None:
            self.image_dialog.destroy()
            self.image_dialog = None
    
    def on_example_image_click(self, widget, event, icon_name):
        # Create a fullscreen image dialog
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.set_halign(Gtk.Align.FILL)
        vbox.set_valign(Gtk.Align.FILL)
        
        # Create event box to capture clicks for closing
        event_box = Gtk.EventBox()
        event_box.set_halign(Gtk.Align.FILL)
        event_box.set_valign(Gtk.Align.FILL)
        event_box.set_hexpand(True)
        event_box.set_vexpand(True)
        
        # Create fullscreen image
        large_image = self._gtk.Image(icon_name, *self._scaled(1.0, 1.0))
        event_box.add(large_image)
        
        # Connect click event to close dialog
        event_box.connect("button-press-event", self.close_image_dialog)
        
        vbox.pack_start(event_box, True, True, 0)
        
        # Create dialog and show fullscreen
        self.image_dialog = self._gtk.Dialog(_("Example Image"), None, vbox, self.close_image_dialog)
        self.image_dialog.fullscreen()
        
    def close_image_dialog(self, dialog, response_id=None):
        # Close the fullscreen image dialog
        if hasattr(self, 'image_dialog') and self.image_dialog is not None:
            self.image_dialog.destroy()
            self.image_dialog = None

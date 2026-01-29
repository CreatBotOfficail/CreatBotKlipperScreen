import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from ks_includes.KlippyFactory import KlippyFactory
from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from datetime import datetime

update_engine_available = False
try:
    from update_engine import UpdateEngine
    update_engine_available = True
    logging.info("UpdateEngine imported successfully")
except ImportError:
    logging.info("UpdateEngine not available")

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Advanced")
        super().__init__(screen, title)
        self.last_drop_time = datetime.now()
        self.advanced = {}
        self.menu_list = {}
        self.is_initialized = False
        self.advanced_options = [
            {
                "adaptive_leveling": {
                    "section": "main",
                    "name": _("Auto Bed Leveling"),
                    "type": "binary",
                    "tooltip": _("Automatic compensation based on the data of the bed mesh"),
                    "value": "False",
                    "callback": self.set_adaptive_leveling,
                }
            },
            {
                "power_loss_recovery": {
                    "section": "main",
                    "name": _("Power Loss Recovery"),
                    "type": "binary",
                    "tooltip": _("Restores your print job after a power outage"),
                    "value": "True",
                    "callback": self.set_power_loss_recovery,
                }
            },
            {
                "auto_change_nozzle": {
                    "section": "main",
                    "name": _("Auto Change Nozzle"),
                    "type": "binary",
                    "tooltip": _("Auto change nozzle when filament runout")
                    + _("(Disable during dual extrusion printing)"),
                    "value": "False",
                    "callback": self.set_auto_change_nozzle,
                }
            },
	]
        if not update_engine_available:
            self.advanced_options.append(
            {
                "factory_settings": {
                    "section": "main",
                    "name": _("Restore Factory Settings"),
                    "type": "button",
                    "tooltip": _("This operation will clear the user data"),
                    "value": "True",
                    "callback": self.reset_factory_settings,
                }
            })

        if self._printer.get_macro("_door_detection") or self._printer.get_config_section_list("door"):
            self.advanced_options.append(
                {
                    "door_open_detection": {
                        "section": "main",
                        "name": _("Door Open Protection Mode"),
                        "type": "dropdown",
                        "tooltip": _(
                            "This feature allows you to customize the printer's response when door opening is detected"
                        ),
                        "value": "Disabled",
                        "callback": self.door_open_detection,
                        "options": [
                            {"name": _("Disabled") + " " + _("(default)"), "value": "Disabled"},
                            {"name": _("Pause Print"), "value": "Pause Print"},
                        ],
                    }
                }
            )

            leds = self._printer.get_leds()
            if leds and len(leds) > 0:
                self.advanced_options.append(
                    {
                        "led_control": {
                            "section": "main",
                            "name": _("Lighting Control"),
                            "type": "binary",
                            "tooltip": _(
                                "Toggle chamber lighting on or off"
                            ),
                            "value": False,
                            "callback": self.set_led_control,
                        }
                    }
                )

        try:
            if hasattr(self._printer, 'get_locks'):
                locks = self._printer.get_locks()
                if locks and len(locks) > 0:
                    self.advanced_options.append(
                        {
                            "auto_door_lock": {
                                "section": "main",
                                "name": _("Auto Door Lock"),
                                "type": "binary",
                                "tooltip": _(
                                    "Automatically lock the door when printing starts"
                                ),
                                "value": True,
                                "callback": self.set_auto_door_lock,
                            }
                        }
                    )
        except Exception:
            pass

        options = self.advanced_options
        self.labels["advanced_menu"] = self._gtk.ScrolledWindow()
        self.labels["advanced"] = Gtk.Grid()
        self.labels["advanced_menu"].add(self.labels["advanced"])
        for option in options:
            name = list(option)[0]
            res = self.add_option("advanced", self.advanced, name, option[name])
            self.menu_list.update(res)
        self.content.add(self.labels["advanced_menu"])

        if "door_open_detection" in self.menu_list:
            self.menu_list["door_open_detection"].connect("notify::popup-shown", self.on_popup_shown)

    def reset_factory_settings(self, *args):
        text = _("Confirm factory reset?\n") + "\n\n" + _("The system will reboot!")
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(text)
        label.set_margin_top(100)

        clear_files_checkbox = Gtk.CheckButton(label=" " + _("Clear Internal G-code Files"))
        clear_files_checkbox.set_halign(Gtk.Align.CENTER)
        clear_files_checkbox.set_valign(Gtk.Align.CENTER)

        buttons = [
            {
                "name": _("Accept"),
                "response": Gtk.ResponseType.OK,
                "style": "dialog-error",
            },
            {
                "name": _("Cancel"),
                "response": Gtk.ResponseType.CANCEL,
                "style": "dialog-info",
            },
        ]

        grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        grid.set_row_spacing(20)
        grid.set_column_spacing(0)
        grid.attach(label, 0, 0, 1, 1)
        grid.attach(clear_files_checkbox, 0, 1, 1, 1)

        self._gtk.Dialog(
            _("factory settings"),
            buttons,
            grid,
            self.confirm_reset_factory_settings,
            clear_files_checkbox,
        )

    def confirm_reset_factory_settings(self, dialog, response_id, clear_files_checkbox):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            KlippyFactory.user_factory_reset(self._screen._ws.klippy, self._config, clear_files_checkbox.get_active())

    def on_popup_shown(self, combo_box, param):
        if combo_box.get_property("popup-shown"):
            logging.debug("Dropdown popup show")
            self.last_drop_time = datetime.now()
        else:
            elapsed = (datetime.now() - self.last_drop_time).total_seconds()
            if elapsed < 0.1:
                logging.debug(f"Dropdown closed too fast ({elapsed}s)")
                GLib.timeout_add(50, lambda: self.dropdown_keep_open(combo_box))
                return
            logging.debug("Dropdown popup close")

    def dropdown_keep_open(self, combo_box):
        if isinstance(combo_box, Gtk.ComboBox):
            combo_box.popup()
        return False

    def door_open_detection(self, str):
        self.set_configuration_string("door_detect", str)

    def set_auto_door_lock(self, *args):
        if not self.is_initialized:
            enable_feature = any(args)
            self.set_configuration_feature("auto_door_lock", enable_feature)
            return
        if len(args) == 1 and isinstance(args[0], bool):
            enable_feature = args[0]
            if not enable_feature:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                box.set_halign(Gtk.Align.CENTER)
                box.set_valign(Gtk.Align.CENTER)
                box.set_hexpand(True)
                box.set_vexpand(True)
                
                label = Gtk.Label()
                label.set_markup(_("<span font-size='x-large'><b>Warning:</b></span>"))
                label.set_halign(Gtk.Align.START)
                label.set_valign(Gtk.Align.CENTER)
                label.set_margin_bottom(10)
                box.add(label)
                
                label2 = Gtk.Label()
                label2.set_text(_("If this option is disabled and the door action is set to Pause,"
                                "changes in door status may cause the print job to pause. "
                                "Please check the relevant settings to ensure smooth printing."))
                label2.set_halign(Gtk.Align.START)
                label2.set_valign(Gtk.Align.CENTER)
                label2.set_line_wrap(True)
                label2.set_max_width_chars(50)
                box.add(label2)

                buttons = [
                    {"name": _("Confirm Disable"), "response": Gtk.ResponseType.YES, "style": "dialog-error"},
                    {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-default"}
                ]
                self._gtk.Dialog(_("Confirm Disable Auto Door Lock"), buttons, box, self._confirm_disable_auto_door_lock)
            else:
                self.set_configuration_feature("auto_door_lock", *args)
        elif len(args) > 0:
            enable_feature = any(args)
            self.set_configuration_feature("auto_door_lock", enable_feature)
    
    def _confirm_disable_auto_door_lock(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        auto_door_lock_switch = self.menu_list.get("auto_door_lock")
        if response_id == Gtk.ResponseType.YES:
            self.set_configuration_feature("auto_door_lock", False)
            self._screen._ws.klippy.set_door_lock("all", "unlock")
            if auto_door_lock_switch:
                auto_door_lock_switch.set_active(False)
        else:
            auto_door_lock_switch.set_active(True)

    def set_adaptive_leveling(self, *args):
        self.set_configuration_feature("adaptive_meshing", *args)

    def set_power_loss_recovery(self, *args):
        self.set_configuration_feature("power_loss_recovery", *args)

    def set_auto_change_nozzle(self, *args):
        self.set_configuration_feature("auto_change_nozzle", *args)

    def set_led_control(self, *args):
        enable_led = any(args)
        leds = self._printer.get_leds()
        if not leds:
            logging.info("No LEDs available for control")
            return
        script_parts = []
        for led_name in leds:
            clean_led_name = led_name.split()[1] if len(led_name.split()) > 1 else led_name
            
            if enable_led:
                script_parts.append(f"SET_LED LED={clean_led_name} RED=1 GREEN=1 BLUE=1 WHITE=1 TRANSMIT=1")
            else:
                script_parts.append(f"SET_LED LED={clean_led_name} RED=0 GREEN=0 BLUE=0 WHITE=0 TRANSMIT=1")
        script = "\n".join(script_parts)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set LED Control: {'On' if enable_led else 'Off'}")

    def set_configuration_string(self, feature_name, str):
        script = KlippyGcodes.set_save_variables(feature_name, str)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set {feature_name}: {str}")

    def set_configuration_feature(self, feature_name, *args):
        enable_feature = any(args)
        script_value = True if enable_feature else False
        script = KlippyGcodes.set_save_variables(feature_name, script_value)
        self._screen._send_action(None, "printer.gcode.script", {"script": script})
        logging.info(f"Set {feature_name}: {script_value}")

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        if "save_variables" in data and "variables" in data["save_variables"]:
            variables = data["save_variables"]["variables"]
            if "adaptive_meshing" in variables:
                self.menu_list["adaptive_leveling"].set_active(variables["adaptive_meshing"])
            else:
                self.menu_list["adaptive_leveling"].set_active(False)

            if "power_loss_recovery" in variables:
                self.menu_list["power_loss_recovery"].set_active(variables["power_loss_recovery"])

            if "auto_change_nozzle" in variables:
                self.menu_list["auto_change_nozzle"].set_active(variables["auto_change_nozzle"])
            else:
                self.menu_list["auto_change_nozzle"].set_active(False)

            if "auto_door_lock" in variables:
                if "auto_door_lock" in self.menu_list:
                    current_value = self.menu_list["auto_door_lock"].get_active()
                    if current_value != variables["auto_door_lock"]:
                        self.menu_list["auto_door_lock"].set_active(variables["auto_door_lock"])
            else:
                if "auto_door_lock" in self.menu_list:
                    current_value = self.menu_list["auto_door_lock"].get_active()
                    if current_value:
                        self.menu_list["auto_door_lock"].set_active(False)
                        self._config.set("main", "auto_door_lock", "False")
                        self._config.save_user_config_options()

            leds = self._printer.get_leds()
            if leds and len(leds) > 0:
                if "interior_lighting" in variables:
                    self.menu_list["led_control"].set_active(variables["interior_lighting"])
                else:
                    self.menu_list["led_control"].set_active(True)

            if self._printer.get_macro("_door_detection") or self._printer.get_config_section_list("door"):
                if "door_detect" in variables:
                    model = self.menu_list["door_open_detection"].get_model()
                    for i, row in enumerate(model):
                        if row[0] == _(variables["door_detect"]):
                            self.menu_list["door_open_detection"].set_active(i)
            self.is_initialized = True


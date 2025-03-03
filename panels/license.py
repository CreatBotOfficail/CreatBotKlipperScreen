import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):

    def __init__(self, screen, title, **kwargs):
        title = title or _("license")
        super().__init__(screen, title)
        self.title_text = (
            _("This device is not activated and is available for trial use only")
            + "\n"
            + _("Please enter a key to activate")
        )
        self.key_len = 15
        self.full = False
        self.interface = screen.license
        self.serial_num = self.interface.get_unique_id() or _("Unknown")
        self.is_active = self.interface.is_active()
        self.args = {}

    def update_time(self):
        total_printed_time = max(0, self.interface.get_total_printed_time())
        trial_time = max(0, self.interface.get_trial_time())
        remaining_time = max(0, trial_time - total_printed_time)

        self.license_box["elapsed_trial_time_value"].set_text(self.seconds_to_hms(total_printed_time))
        self.license_box["trial_time_value"].set_text(self.seconds_to_hms(trial_time))
        self.license_box["remain_time_value"].set_text(self.seconds_to_hms(remaining_time))

    def seconds_to_hms(self, seconds):

        if not isinstance(seconds, (int, float)) or seconds < 0:
            raise ValueError(f"seconds must be a non-negative number, got {seconds}")

        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)

        return f"{hours:03}:{minutes:02}:{secs:02}"

    def state_update(self, text):
        self.license_box["state_text_value"].set_text(text)

    def verify_key(self, key):
        try:
            res = self.interface.verify_activation_code(key)
            if res:
                if self.interface.is_active():
                    self.is_active = True
                    self.state_update(_("Permanent Activation"))
                else:
                    self.state_update(_("Key is valid"))
            else:
                self.state_update(_("Key is invalid"))
        except Exception as e:
            logging.exception(e)

    def active_refresh(self, **args):
        self.args["full"] = args.get("full")
        self.args["callback"] = args.get("func")
        self.args["file"] = args.get("file")
        self.args["onboarding"] = args.get("onboarding")
        self.display_dialog()

    def deactivate(self):
        self._screen.remove_keyboard()
        for child in self.content.get_children():
            self.content.remove(child)

    def display_dialog(self, full=False, key=""):
        BUTTON_CONFIGS = {
            "trial_with_callback": [
                {"name": _("Activate"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
                {"name": _("Skip"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-error"},
            ],
            "full_features": [
                {"name": _("Reset"), "response": Gtk.ResponseType.APPLY, "style": "dialog-secondary"},
                {"name": _("Activate"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
                {"name": _("Close"), "response": Gtk.ResponseType.CLOSE, "style": "dialog-error"},
            ],
            "Trial": [
                {"name": _("Activate"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
                {"name": _("Trial"), "response": Gtk.ResponseType.CLOSE, "style": "dialog-error"},
            ],
            "default": [
                {"name": _("Activate"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
                {"name": _("Close"), "response": Gtk.ResponseType.CLOSE, "style": "dialog-error"},
            ],
        }

        if self.args.get("callback") and self.interface.is_trial_active():
            buttons = BUTTON_CONFIGS["trial_with_callback"]
        elif self.args.get("full"):
            buttons = BUTTON_CONFIGS["full_features"]
        elif self.args.get("onboarding"):
            buttons = BUTTON_CONFIGS["Trial"]
        else:
            buttons = BUTTON_CONFIGS["default"]

        self.create_license_key_dialog(buttons=buttons, key=key)

    def create_license_key_dialog(self, buttons=None, key=""):

        if buttons is None:
            buttons = [
                {"name": _("Activate"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
                {"name": _("Close"), "response": Gtk.ResponseType.CLOSE, "style": "dialog-error"},
            ]

        self.title_label = Gtk.Label(hexpand=True, vexpand=False, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        self.title_label.set_markup(f"<big>{self.title_text}</big>\n")
        self.title_label.set_margin_top(50)
        self.title_label.set_margin_start(20)
        self.title_label.set_halign(Gtk.Align.START)

        self.license_box = {}

        self.grid = Gtk.Grid(column_spacing=20, row_spacing=20, hexpand=True, vexpand=True)

        def add_labeled_value(row, label_text, value_text):
            label = Gtk.Label(label=label_text, use_markup=True, xalign=0, wrap=True)
            value = Gtk.Label(label=value_text, use_markup=True, xalign=0, wrap=True)
            self.grid.attach(label, 0, row, 1, 1)
            self.grid.attach(value, 1, row, 1, 1)
            return label, value

        status_text = _("Not activated")
        if not self.interface.is_interface_valid():
            status_text = _("Unknown")
        elif self.is_active:
            status_text = _("Permanent Activation")
        self.license_box["state_text"], self.license_box["state_text_value"] = add_labeled_value(
            0, _("State:"), status_text
        )
        self.license_box["serial_num_text"], self.license_box["serial_num_value"] = add_labeled_value(
            1, _("Serial Number:"), self.serial_num
        )
        self.license_box["trial_time_text"], self.license_box["trial_time_value"] = add_labeled_value(
            2, _("Trial Time:"), "000:00:00"
        )
        self.license_box["elapsed_trial_time_text"], self.license_box["elapsed_trial_time_value"] = add_labeled_value(
            3, _("Elapsed trial time:"), "000:00:00"
        )
        self.license_box["remain_time_text"], self.license_box["remain_time_value"] = add_labeled_value(
            4, _("Remaining Time:"), "000:00:00"
        )

        self.license_box["key_text"] = Gtk.Label(label=_("Key:"), use_markup=True, xalign=0, wrap=True)
        self.grid.attach(self.license_box["key_text"], 0, 5, 1, 1)

        self.license_box["key_input"] = Gtk.Entry(hexpand=False, vexpand=False)
        self.license_box["key_input"].set_max_length(self.key_len)
        self.license_box["key_input"].set_text(key)
        self.license_box["key_input"].connect("button-press-event", self.on_show_keyboard)
        self.grid.attach(self.license_box["key_input"], 1, 5, 1, 1)

        image = self._gtk.Image("license", self._gtk.content_width * 0.4, self._gtk.content_height * 0.4)
        image.set_margin_start(60)
        image.set_margin_end(20)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        horizontal_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        horizontal_box.set_margin_top(20)

        self.grid.set_margin_start(60)
        horizontal_box.pack_start(image, False, True, 0)
        horizontal_box.pack_start(self.grid, True, True, 0)

        main_box.pack_start(self.title_label, False, True, 0)
        main_box.pack_start(horizontal_box, True, True, 0)

        self.dialog = self._gtk.Dialog("License", buttons, main_box, self.confirm_license_response)
        self.update_time()

    def confirm_license_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            if self.interface.enabled_registration():
                self.state_update(_("Enabled successfully"))
        elif response_id == Gtk.ResponseType.APPLY:
            if len(self.license_box["key_input"].get_text()) == 0:
                self.state_update(_("Key is empty"))
                return
            else:
                if self.interface.reset_registration(self.license_box["key_input"].get_text()):
                    self.update_time()
                    self.state_update(_("Reset successfully"))
                else:
                    self.state_update(_("Key is invalid"))
        elif response_id == Gtk.ResponseType.CLOSE:
            self._gtk.remove_dialog(dialog)
            self._screen._menu_go_back()
        elif response_id == Gtk.ResponseType.CANCEL:
            self._gtk.remove_dialog(dialog)
            self._screen._menu_go_back()
            if not self.interface.is_active() and self.interface.is_trial_active():
                if self.args.get("callback"):
                    self.args["callback"](self.args["file"])
        elif response_id == Gtk.ResponseType.OK:
            if len(self.license_box["key_input"].get_text()) == 0:
                self.state_update(_("Key is empty"))
                return
            self.verify_key(self.license_box["key_input"].get_text())
            self.update_time()

    def on_show_keyboard(self, entry=None, event=None):
        self._gtk.remove_dialog(self.dialog)
        lbl = Gtk.Label(_("Please enter a key to activate"), halign=Gtk.Align.START, hexpand=False)
        self.labels["entry"] = Gtk.Entry(hexpand=True)
        self.labels["entry"].set_max_length(self.key_len)
        self.labels["entry"].connect("focus-in-event", self._screen.show_keyboard)
        save = self._gtk.Button("complete", _("Save"), "color3")
        save.set_hexpand(False)
        save.connect("clicked", self.on_save_key)
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        input_box.pack_start(self.labels["entry"], True, True, 5)
        input_box.pack_start(save, False, False, 5)
        self.labels["input_box"] = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True, vexpand=True, valign=Gtk.Align.CENTER
        )
        self.labels["input_box"].pack_start(lbl, True, True, 5)
        self.labels["input_box"].pack_start(input_box, True, True, 5)
        self.content.add(self.labels["input_box"])
        self.labels["entry"].grab_focus_without_selecting()

    def on_save_key(self, dialog):
        key_text = self.labels["entry"].get_text()
        self._screen.remove_keyboard()
        for child in self.content.get_children():
            self.content.remove(child)
        self.display_dialog(self.full, key=key_text)

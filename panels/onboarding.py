import logging
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):

    def __init__(self, screen, title):
        title = title or _('Welcome')
        super().__init__(screen, title)

        buttons = [
            {"name": _("Next"), "response": Gtk.ResponseType.YES, "style": 'dialog-secondary'}
        ]

        image = self._gtk.Image(
            "retainer", self._gtk.content_width * 0.3, self._gtk.content_height * 0.5
        )
        start_text = _("1. For first use, refer to the accompanying diagram to disassemble the fixed components of the X, Y, and Z axes.")
        space = "\n\n"
        end_text = _("2. Once the disassembly is complete, click the 'Next' button to proceed.")
        label = Gtk.Label(hexpand=True, vexpand=True, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        label.set_markup(f"<big>{start_text + space + end_text}</big>\n")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        image.set_margin_start(60)
        image.set_margin_top(80)
        box.pack_start(image, False, True, 0)
        box.pack_start(label, False, False, 20)

        self._gtk.Dialog(f'Welcome', buttons, box, self.confirm_print_response)

    def create_raise_platform(self):
        buttons = [
            {"name": _("Raise Platform"), "response": Gtk.ResponseType.OK},
            {"name": _("Finish"), "response": Gtk.ResponseType.APPLY, "style": 'dialog-secondary'}
        ]

        image = self._gtk.Image(
            "take_out", self._gtk.content_width * 0.3, self._gtk.content_height * 0.5
        )

        start_text = _("1. Ensure that all fixed components have been properly removed before proceeding.")
        center_text = _("2. Press the 'Raise Platform' button to lift the platform and remove the items underneath.")
        end_text = _("3. Once the operation is complete, click the \'Finish\' button to conclude the process.")
        space = "\n\n"
        label = Gtk.Label(hexpand=True, vexpand=True, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        label.set_markup(f"<big>{start_text + space + center_text + space + end_text}</big>\n")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        image.set_margin_start(60)
        image.set_margin_top(80)
        box.pack_start(image, False, True, 0)
        box.pack_start(label, False, False, 20)

        self._gtk.Dialog(f'Test', buttons, box, self.confirm_print_response)

    def confirm_print_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            self._gtk.remove_dialog(dialog)
            self.create_raise_platform()
        elif response_id == Gtk.ResponseType.OK:
            self._screen._ws.klippy.gcode_script("SET_KINEMATIC_POSITION Z=5\nG28")
        elif response_id == Gtk.ResponseType.APPLY:
            self._screen.show_panel("main_menu", remove_all=True, items=self._config.get_menu_items("__main"))
            self._config.set("main", "onboarding", "False")
            self._config.save_user_config_options()
            if self._screen.license.is_interface_valid() and not self._screen.license.is_active():
                self._gtk.remove_dialog(dialog)
                self._screen.show_panel("license", remove_all=False, onboarding=True)

import logging
import os.path
import pathlib

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from ks_includes.ModelConfig import ModelConfig
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or "factory settings"
        super().__init__(screen, title)
        self.factory_settings_list = [
            {
                "Select Model": {
                    "section": "main",
                    "name": _("Select Model"),
                    "type": "button",
                    "callback": self.show_select_model,
                }
            }
        ]
        self.settings = {}
        self.select_model = False
        self.labels["setting_menu"] = self._gtk.ScrolledWindow()
        self.labels["settings"] = Gtk.Grid()
        self.labels["setting_menu"].add(self.labels["settings"])

        for option in self.factory_settings_list:
            name = list(option)[0]
            self.add_option("settings", self.settings, name, option[name])

        self.content.add(self.labels["setting_menu"])
        self.content.show_all()

    def back(self):
        if self.select_model:
            self.hide_select_model()
            return True
        return False

    def show_select_model(self, widget, option):
        self.create_select_model()
        for child in self.content.get_children():
            self.content.remove(child)
        self.content.add(self.labels["model_menu"])
        self.content.show_all()
        self.select_model = True

    def create_select_model(self):
        if "model_menu" in self.labels:
            return
        if not hasattr(self, "model_config") or self.model_config is None:
            self.model_config = ModelConfig()
        self.labels["model_menu"] = self._gtk.ScrolledWindow()
        self.labels["model"] = Gtk.Grid()
        self.labels["model_menu"].add(self.labels["model"])
        klipperscreendir = pathlib.Path(__file__).parent.resolve().parent
        self.model_list_path = os.path.join(klipperscreendir, "config", "model_menu.conf")
        self.model_list = pathlib.Path(self.model_list_path).read_text()
        with open(self.model_list_path) as file:
            self.models = {}
            for line in file:
                model_name = line.strip()
                self.models[model_name] = {
                    "name": model_name,
                    "type": "button",
                    "callback": self.change_model,
                }
                self.add_option("model", self.models, model_name, self.models[model_name])

    def change_model(self, widget, event):
        self.model_config.generate_config(event)

    def hide_select_model(self):
        for child in self.content.get_children():
            self.content.remove(child)
        if "setting_menu" in self.labels:
            self.content.add(self.labels["setting_menu"])
            self.content.show_all()
        self.select_model = False

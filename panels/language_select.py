import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or "Select Language"
        super().__init__(screen, title)
        self.language_map = {
            'cs': 'Čeština',
            'da': 'Dansk',
            'de': 'Deutsch',
            'de_formal': 'Höfliches Deutsch',
            'en': 'English',
            'es': 'Español',
            'et': 'Eesti',
            'fr': 'Français',
            'he': 'עברית',
            'hu': 'Magyar',
            'it': 'Italiano',
            'jp': '日本語',
            'ko': '한국어',
            'lt': 'Lietuvių',
            'nl': 'Nederlands',
            'pl': 'Polski',
            'pt': 'Português',
            'pt_BR': 'Português (Brasil)',
            'ru': 'Русский',
            'sl': 'Slovenščina',
            'sv': 'Svenska',
            'tr': 'Türkçe',
            'uk': 'Українська',
            'vi': 'Tiếng Việt',
            'zh_CN': '简体中文',
            'zh_TW': '繁體中文',
        }
        self.langs = {}
        self.labels['lang_menu'] = self._gtk.ScrolledWindow()
        self.labels['lang'] = Gtk.Grid()
        self.labels['lang_menu'].add(self.labels['lang'])
        self.labels['lang'].set_margin_start(50)
        for lang in self._config.lang_list:
            name = self.language_map.get(lang)
            if name:
                self.langs[lang] = {
                    "name": name,
                    "type": "button",
                    "callback": self.change_language,
                }
                self.add_option("lang", self.langs, lang, self.langs[lang])
        self.content.add(self.labels["lang_menu"])
        self.content.show_all()

    def change_language(self, widget, lang):
        reverse_language_map = {v: k for k, v in self.language_map.items()}
        language_code = reverse_language_map.get(lang, 'en')
        self._screen.change_language(widget, language_code)
        self._screen.initial_connection()

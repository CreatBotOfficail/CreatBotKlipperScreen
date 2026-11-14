import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel
from panels import date_time


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Settings")
        super().__init__(screen, title)
        if getattr(self, "datetime_page", None) is not None:
            self.datetime_page.stop()
        self.printers = self.settings = self.langs = {}
        self.menu = ['settings_menu']
        options = [
            option for option in self._config.get_configurable_options() if "24htime" not in option
        ]
        options.append({"lang": {
            "name": _("Language"),
            "type": "menu",
            "menu": "lang"
        }})
        options.append({"datetime": {
            "name": _("Date & Time"),
            "type": "menu",
            "menu": "datetime"
        }})
        self.labels['settings_menu'] = self._gtk.ScrolledWindow()
        self.labels['settings'] = Gtk.Grid()
        self.labels['settings_menu'].add(self.labels['settings'])
        for option in options:
            name = list(option)[0]
            self.add_option('settings', self.settings, name, option[name])

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

        self.labels['lang_menu'] = self._gtk.ScrolledWindow()
        self.labels['lang'] = Gtk.Grid()
        self.labels['lang_menu'].add(self.labels['lang'])
        for lang in self._config.lang_list:
            name = self.language_map.get(lang)
            self.langs[lang] = {
                "name": name,
                "type": "button",
                "callback": self.change_language,
            }
            self.add_option("lang", self.langs, lang, self.langs[lang])

        self.labels['datetime_menu'] = self.datetime_page = date_time.DateTimePage(self)

        self.content.add(self.labels['settings_menu'])

    def load_menu(self, widget, name, title=None):
        if name == "datetime":
            self.labels['datetime_menu'].refresh()
        super().load_menu(widget, name, title)

    def change_language(self, widget, lang):
        reverse_language_map = {v: k for k, v in self.language_map.items()}
        language_code = reverse_language_map.get(lang, 'en')
        self._screen.change_language(widget, language_code)

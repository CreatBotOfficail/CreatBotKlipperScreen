import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Network")
        super().__init__(screen, title)

    def activate(self):
        self.create_network_menu()

    def create_network_menu(self):
        for child in self.content.get_children():
            self.content.remove(child)

        menu_items = self._screen._config.get_menu_items("__main", "more network")

        if menu_items:
            from panels.menu import Panel as MenuPanel

            menu_panel = MenuPanel(self._screen, _("Network"), items=menu_items)

            scroll = self._gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

            scroll.add(menu_panel.arrangeMenuItems(menu_items))

            self.content.add(scroll)
        else:
            label = Gtk.Label(_("No network options available"))
            label.set_halign(Gtk.Align.CENTER)
            label.set_valign(Gtk.Align.CENTER)
            self.content.add(label)

        self.content.show_all()

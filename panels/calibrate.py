import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Calibrate")
        super().__init__(screen, title)
        
    def activate(self):
        self.create_calibrate_menu()
    
    def create_calibrate_menu(self):
        for child in self.content.get_children():
            self.content.remove(child)
        
        calibration_items = self._screen._config.get_menu_items("__calibrate")
        
        if calibration_items:
            from panels.menu import Panel as MenuPanel
            
            menu_panel = MenuPanel(self._screen, _("Calibrate"), items=calibration_items)
            
            scroll = self._gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            
            scroll.add(menu_panel.arrangeMenuItems(calibration_items))
            
            self.content.add(scroll)
        else:
            label = Gtk.Label(_("No calibration options available"))
            label.set_halign(Gtk.Align.CENTER)
            label.set_valign(Gtk.Align.CENTER)
            self.content.add(label)
        
        self.content.show_all()

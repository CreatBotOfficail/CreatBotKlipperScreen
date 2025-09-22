import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from panels.menu import Panel as MenuPanel
from ks_includes.widgets.heatergraph import HeaterGraph
from ks_includes.widgets.keypad import Keypad
from ks_includes.KlippyGtk import find_widget


class Panel(MenuPanel):
    def __init__(self, screen, title, items=None):
        super().__init__(screen, title, items)
        self.left_panel = None
        self.devices = {}
        self.graph_update = None
        self.active_heater = None
        self.h = self.f = 0
        self.main_menu = Gtk.Grid(row_homogeneous=True, column_homogeneous=True, hexpand=True, vexpand=True)

        if self._screen.vertical_mode:
            self.labels['menu'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0, homogeneous=False)
        else:
            self.labels['menu'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, homogeneous=False)
        logo_image = self._gtk.Image("klipper", self._gtk.content_width * 0.2, self._gtk.content_height * 0.5)
        self.labels['menu'].pack_start(logo_image, False, False, 80)
        # temp_Button = self.arrangeMenuItems(items, 1, True)
        temp_Button = self._gtk.Button("heat-up", _("Temperature"))
        temp_Button.set_valign(Gtk.Align.CENTER)
        temp_Button.set_halign(Gtk.Align.CENTER)
        temp_Button.set_size_request(200, 100)
        temp_Button.get_style_context().add_class('custom-icon-button')
        temp_Button.connect('clicked', self.menu_item_clicked, {"panel": "temperature"})
        self.labels['menu'].pack_start(temp_Button, True, True, 0)
        self.labels['da'] = HeaterGraph(self._screen, self._printer, self._gtk.font_size)
        self.labels['devices'] = self.create_top_panel(self.labels['da'])

        logging.info("### Making MainMenu")

        stats = self._printer.get_printer_status_data()["printer"]
        if stats["temperature_devices"]["count"] > 0 or stats["extruders"]["count"] > 0:
            self._gtk.reset_temp_color()
        if self._screen.vertical_mode:
            self.main_menu.attach(self.labels['devices'], 0, 0, 2, 1)
            self.main_menu.attach(self.labels['da'], 0, 1, 2, 1)
            self.main_menu.attach(self.labels['menu'], 0, 2, 2, 1)
        else:
            self.main_menu.attach(self.labels['devices'], 0, 0, 2, 1)
            self.main_menu.attach(self.labels['menu'], 0, 1, 1, 2)
            self.main_menu.attach(self.labels['da'], 1, 1, 1, 2)
        self.content.add(self.main_menu)

    def update_graph_visibility(self, force_hide=False):
        if self.left_panel is None:
            logging.info("No left panel")
            return
        count = 0
        for device in self.devices:
            visible = self._config.get_config().getboolean(f"graph {self._screen.connected_printer}",
                                                           device, fallback=True)
            self.devices[device]['visible'] = visible
            self.labels['da'].set_showing(device, visible)
            if visible:
                count += 1
                self.devices[device]['name'].get_style_context().add_class("graph_label")
            else:
                self.devices[device]['name'].get_style_context().remove_class("graph_label")
        if count > 0 and not force_hide:
            self.labels['da'].queue_draw()
            self.labels['da'].show()
            if self.graph_update is None:
                # This has a high impact on load
                self.graph_update = GLib.timeout_add_seconds(5, self.update_graph)
        elif self.labels['da'] in self.left_panel:
            self.left_panel.remove(self.labels['da'])
            if self.graph_update is not None:
                GLib.source_remove(self.graph_update)
                self.graph_update = None
        return False

    def activate(self):
        if not self._printer.tempstore:
            self._screen.init_tempstore()
        self.update_graph_visibility()

    def deactivate(self):
        if self.graph_update is not None:
            GLib.source_remove(self.graph_update)
            self.graph_update = None

    def add_device(self, device, graph):

        logging.info(f"Adding device: {device}")

        temperature = self._printer.get_stat(device, "temperature")
        if temperature is None:
            return False

        devname = device.split()[1] if len(device.split()) > 1 else device
        # Support for hiding devices by name
        if devname.startswith("_"):
            return False

        if device.startswith("extruder"):
            if self._printer.extrudercount > 1:
                image = f"extruder-{device[8:]}" if device[8:] else "extruder-0"
            else:
                image = "extruder"
            class_name = f"graph_label_{device}"
            dev_type = "extruder"
        elif device == "heater_bed":
            image = "bed"
            devname = "Heater Bed"
            class_name = "graph_label_heater_bed"
            dev_type = "bed"
        elif device == "heater_generic chamber" or device == "heater_chamber":
            self.h += 1
            image = "chamber"
            devname = "Heater Chamber"
            class_name = f"graph_label_sensor_{self.h}"
            dev_type = "sensor"
        elif device.startswith("heater_generic"):
            self.h += 1
            image = "heater"
            class_name = f"graph_label_sensor_{self.h}"
            dev_type = "sensor"
        elif device.startswith("temperature_fan"):
            self.f += 1
            image = "fan"
            class_name = f"graph_label_fan_{self.f}"
            dev_type = "fan"
        elif self._config.get_main_config().getboolean("only_heaters", False):
            return False
        else:
            self.h += 1
            image = "heat-up"
            class_name = f"graph_label_sensor_{self.h}"
            dev_type = "sensor"

        rgb = self._gtk.get_temp_color(dev_type)

        can_target = self._printer.device_has_target(device)
        graph.add_object(device, "temperatures", rgb, False, False)
        if can_target:
            graph.add_object(device, "targets", rgb, False, True)
        if self._show_heater_power and self._printer.device_has_power(device):
            graph.add_object(device, "powers", rgb, True, False)

        # name = self._gtk.Button(image, self.prettify(devname), None, self.bts, Gtk.PositionType.TOP, 1)
        name = self._gtk.Button()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        name.add(vbox)
        target = Gtk.Label()
        icon = self._gtk.Image(image)
        temp = Gtk.Label()
        power = Gtk.Label()
        vbox.pack_start(target, True, False, 5)
        vbox.pack_start(icon, True, False, 0)
        vbox.pack_start(temp, True, False, 0)
        vbox.pack_start(power, True, False, 0)
        # name.connect("clicked", self.toggle_visibility, device)
        # name.set_alignment(0, .5)
        name.get_style_context().add_class(class_name)
        visible = self._config.get_config().getboolean(f"graph {self._screen.connected_printer}", device, fallback=True)
        if visible:
            name.get_style_context().add_class("graph_label")
        self.labels['da'].set_showing(device, visible)

        find_widget(temp, Gtk.Label).set_ellipsize(False)
        if can_target:
            name.connect("clicked", self.menu_item_clicked, {"panel": "numpad", 'extra': device})

        self.devices[device] = {
            "class": class_name,
            "name": name,
            "temp": temp,
            "target": target,
            "power": power,
            "can_target": can_target,
            "visible": visible
        }

        devices = sorted(self.devices)
        pos = devices.index(device) + 1

        self.labels['devices'].insert_row(pos)
        self.labels['devices'].attach(name, pos, 0, 1, 1)
        self.labels['devices'].show_all()
        return True

    def toggle_visibility(self, widget, device):
        self.devices[device]['visible'] ^= True
        logging.info(f"Graph show {self.devices[device]['visible']}: {device}")

        section = f"graph {self._screen.connected_printer}"
        if section not in self._config.get_config().sections():
            self._config.get_config().add_section(section)
        self._config.set(section, f"{device}", f"{self.devices[device]['visible']}")
        self._config.save_user_config_options()

        self.update_graph_visibility()




    def create_top_panel(self, graph):

        self.labels['devices'] = Gtk.Grid(vexpand=False)
        self.labels['devices'].get_style_context().add_class('heater-grid')

        # name = Gtk.Label()
        # temp = Gtk.Label(label=_("Temp (°C)"))
        # if self._show_heater_power:
        #     temp.get_style_context().add_class("heater-grid-temp-power")
        # else:
        #     temp.get_style_context().add_class("heater-grid-temp")

        # self.labels['devices'].attach(name, 0, 0, 1, 1)
        # self.labels['devices'].attach(temp, 1, 0, 1, 1)

        # self.labels['da'] = HeaterGraph(self._screen, self._printer, self._gtk.font_size)

        scroll = self._gtk.ScrolledWindow(steppers=False)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.get_style_context().add_class('heater-list')
        scroll.add(self.labels['devices'])

        self.left_panel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.left_panel.add(scroll)

        for d in self._printer.get_temp_devices():
            self.add_device(d, graph)

        return self.left_panel



    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        for x in self._printer.get_temp_devices():
            if x in data:
                self.update_temp(
                    x,
                    self._printer.get_stat(x, "temperature"),
                    self._printer.get_stat(x, "target"),
                    self._printer.get_stat(x, "power"),
                )





    def update_graph(self):
        self.labels['da'].queue_draw()
        return True


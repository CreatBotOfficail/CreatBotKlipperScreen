import logging
import gi
import time

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from ks_includes.screen_panel import ScreenPanel

class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("System")
        super().__init__(screen, title)
        self.current_row = 0
        self.mem_multiplier = None
        self.model_config = None
        self.info_panel = None
        self.scales = {}
        self.labels = {}
        self.click_count = 0
        self.last_click_time = 0
        self.click_threshold = 2.0
        self.target_clicks = 5
        self.grid = Gtk.Grid(column_spacing=10, row_spacing=5)

        self.sysinfo = screen.printer.system_info
        if not self.sysinfo:
            logging.debug("Asking for info")
            self.sysinfo = screen.apiclient.send_request("machine/system_info")
            if 'system_info' in self.sysinfo:
                screen.printer.system_info = self.sysinfo['system_info']
                self.sysinfo = self.sysinfo['system_info']
        logging.debug(self.sysinfo)

        if self.sysinfo:
            self.info_panel = self.create_layout()
        else:
            self.content.add(Gtk.Label(label=_("No info available"), vexpand=True))

    def create_layout(self):
        self.labels["cpu_usage"] = Gtk.Label(label="", xalign=0)
        self.grid.attach(self.labels["cpu_usage"], 0, self.current_row, 1, 1)
        self.scales["cpu_usage"] = Gtk.ProgressBar(
            hexpand=True, show_text=False, fraction=0
        )
        self.grid.attach(self.scales["cpu_usage"], 1, self.current_row, 1, 1)
        self.current_row += 1

        self.labels["memory_usage"] = Gtk.Label(label="", xalign=0)
        self.grid.attach(self.labels["memory_usage"], 0, self.current_row, 1, 1)
        self.scales["memory_usage"] = Gtk.ProgressBar(
            hexpand=True, show_text=False, fraction=0
        )
        self.grid.attach(self.scales["memory_usage"], 1, self.current_row, 1, 1)
        self.current_row += 1

        self.grid.attach(Gtk.Separator(), 0, self.current_row, 2, 1)
        self.current_row += 1
        self.machine_info()
        self.current_row += 1
        self.populate_info()

        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.grid)
        self.content.add(scroll)
        return scroll

    def on_model_click(self, widget, event):
        current_time = time.time()
        if (current_time - self.last_click_time) <= self.click_threshold:
            self.click_count += 1
        else:
            self.click_count = 0
        self.last_click_time = current_time
        if self.click_count >= self.target_clicks:
            self.click_count = 0
            self._screen.show_panel("factory_settings", remove_all=False)

    def set_mem_multiplier(self, data):
        memory_units = data.get("memory_units", "kB").lower()
        units_mapping = {
            "kb": 1024,
            "mb": 1024**2,
            "gb": 1024**3,
            "tb": 1024**4,
            "pb": 1024**5,
        }
        self.mem_multiplier = units_mapping.get(memory_units, 1)

    def add_label_to_grid(self, text, column, bold=False):
        if bold:
            text = f"<b>{text}</b>"
        label = Gtk.Label(label=text, use_markup=True, xalign=0, wrap=True)
        self.grid.attach(label, column, self.current_row, 1, 1)
        self.current_row += 1

    def machine_info(self):
        self.add_label_to_grid(self.prettify("device"), 0, bold=True)
        self.current_row -= 1
        self.add_label_to_grid("Manufacturer: CreatBot", 1)
        event_box = Gtk.EventBox()
        event_box.connect("button-release-event", self.on_model_click)
        mode = self._screen.connecting_to_printer.split("-")[0]
        label = Gtk.Label(label=f"Model: {mode}", use_markup=True, xalign=0, wrap=True)
        self.grid.attach(event_box, 1, self.current_row, 1, 1)
        self.current_row += 1
        event_box.add(label)
        self.add_label_to_grid(f"Name: {self._screen.connecting_to_printer}", 1)

    def populate_info(self):
        for category, data in self.sysinfo.items():
            if category == "python":
                self.add_label_to_grid(self.prettify(category), 0, bold=True)
                self.current_row -= 1
                self.add_label_to_grid(
                    f'Version: {data["version_string"].split(" ")[0]}', 1
                )
                continue

            if (
                category
                in (
                    "virtualization",
                    "provider",
                    "available_services",
                    "service_state",
                    "instance_ids",
                )
                or not self.sysinfo[category]
            ):
                continue

            self.add_label_to_grid(self.prettify(category), 0, bold=True)

            if isinstance(data, dict):
                for key, value in data.items():
                    if key in ("version_parts", "memory_units") or not value:
                        continue
                    if key == "total_memory":
                        if not self.mem_multiplier:
                            self.set_mem_multiplier(data)
                        value = self.format_size(int(value) * self.mem_multiplier)
                    if isinstance(value, dict):
                        self.add_label_to_grid(self.prettify(key), 0)
                        self.current_row -= 1
                        for sub_key, sub_value in value.items():
                            if not sub_value:
                                continue
                            elif (
                                isinstance(sub_value, list)
                                and sub_key == "ip_addresses"
                            ):
                                for _ip in sub_value:
                                    self.add_label_to_grid(
                                        f"{self.prettify(sub_key)}: {_ip['address']}", 1
                                    )
                                continue
                            self.add_label_to_grid(
                                f"{self.prettify(sub_key)}: {sub_value}", 1
                            )
                    else:
                        self.add_label_to_grid(f"{self.prettify(key)}: {value}", 1)

    def process_update(self, action, data):
        if not self.sysinfo:
            return
        if action == "notify_proc_stat_update":
            self.labels["cpu_usage"].set_label(
                f'CPU: {data["system_cpu_usage"]["cpu"]:.0f}%'
            )
            self.scales["cpu_usage"].set_fraction(
                float(data["system_cpu_usage"]["cpu"]) / 100
            )

            self.labels["memory_usage"].set_label(
                _("Memory")
                + f': {(data["system_memory"]["used"] / data["system_memory"]["total"]) * 100:.0f}%'
            )
            self.scales["memory_usage"].set_fraction(
                float(data["system_memory"]["used"])
                / float(data["system_memory"]["total"])
            )

from update_engine import UpdateEngine, UpdateEngineError
from ks_includes.KlippyFactory import KlippyFactory
from ks_includes.screen_panel import ScreenPanel
from gi.repository import Gtk, Pango, GLib
import logging
import os
import tarfile
import datetime
from gettext import ngettext

import gi

gi.require_version("Gtk", "3.0")


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Maintenance")
        super().__init__(screen, title)
        self.labels = {}
        self.update_status = None
        self.upload_file = None
        self.firmware_version = None
        self.is_beta = False
        self.update_engine = UpdateEngine()

        self.buttons = {
            "online_update": self._gtk.Button(
                image_name="arrow-up",
                label=_("Online Update"),
                style="color1",
                scale=self.bts,
                position=Gtk.PositionType.LEFT,
                lines=1,
            ),
            "local_update": self._gtk.Button(
                image_name="sd",
                label=_("USB Update"),
                style="color2",
                scale=self.bts,
                position=Gtk.PositionType.LEFT,
                lines=1,
            ),
            "factory_reset": self._gtk.Button(
                image_name="settings",
                label=_("Factory Reset"),
                style="color3",
                scale=self.bts,
                position=Gtk.PositionType.LEFT,
                lines=1,
            ),
            "export_logs": self._gtk.Button(
                image_name="file",
                label=_("Export Logs"),
                style="color4",
                scale=self.bts,
                position=Gtk.PositionType.LEFT,
                lines=1,
            ),
        }

        self.service_buttons = {}
        self.services = []

        self.buttons["online_update"].connect(
            "clicked", self.online_update_clicked)
        self.buttons["local_update"].connect(
            "clicked", self.local_update_clicked)
        self.buttons["factory_reset"].connect(
            "clicked", self.factory_reset_clicked)
        self.buttons["export_logs"].connect(
            "clicked", self.export_logs_clicked)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)

        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        left_box.set_hexpand(True)

        function_grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        function_grid.set_row_spacing(10)
        function_grid.set_column_spacing(10)
        # function_grid.attach(self.buttons["online_update"], 0, 0, 1, 1) #todo
        function_grid.attach(self.buttons["local_update"], 0, 1, 1, 1)
        function_grid.attach(self.buttons["factory_reset"], 0, 2, 1, 1)
        function_grid.attach(self.buttons["export_logs"], 0, 3, 1, 1)

        left_box.pack_start(function_grid, True, True, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        separator.set_margin_top(0)
        separator.set_margin_bottom(0)

        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right_box.set_hexpand(True)

        self.service_grid = Gtk.Grid()
        self.service_grid.set_row_spacing(10)
        self.service_grid.set_column_spacing(15)
        self.service_grid.set_valign(Gtk.Align.CENTER)

        right_box.pack_start(self.service_grid, True, False, 0)

        main_box.pack_start(left_box, True, True, 0)
        main_box.pack_start(separator, False, False, 0)
        main_box.pack_start(right_box, True, True, 0)

        self.content.add(main_box)

    def activate(self):
        self.load_services()

    def load_services(self):
        for child in self.service_grid.get_children():
            self.service_grid.remove(child)

        self.services.clear()
        self.service_buttons.clear()

        service_config = {
            "klipper": "Klipper",
            "moonraker": "Moonraker",
            "KlipperScreen": "KlipperScreen",
            "go2rtc": "Go2RTC",
            "crowsnest": "Crowsnest",
            "sonar": "Sonar",
            "nginx": "Nginx",
        }

        available_services = []
        try:
            if hasattr(self._printer, 'system_info') and self._printer.system_info:
                if "available_services" in self._printer.system_info:
                    available_services = self._printer.system_info["available_services"]
                    logging.info(f"Available services: {available_services}")
        except Exception as e:
            logging.error(f"Error getting available services: {e}")

        if not available_services:
            logging.info("Using default service list")
            available_services = ["klipper",
                                  "moonraker", "KlipperScreen", "go2rtc"]

        for service_id in available_services:
            if service_id in service_config:
                self.services.append({
                    "name": service_config[service_id],
                    "service": service_id,
                })
            else:
                self.services.append({
                    "name": service_id.capitalize(),
                    "service": service_id,
                })

        for i, service in enumerate(self.services):
            service_name_label = Gtk.Label()
            service_name_label.set_markup(f"<b>{service['name']}</b>")
            service_name_label.set_halign(Gtk.Align.START)
            service_name_label.set_hexpand(True)

            restart_btn = self._gtk.Button(
                image_name="refresh",
                label=_("Restart"),
                style="color3",
                scale=self.bts * 0.7,
                position=Gtk.PositionType.LEFT,
            )
            restart_btn.connect(
                "clicked", self.restart_service, service["service"])
            restart_btn.set_hexpand(False)
            restart_btn.set_size_request(180, -1)

            self.service_grid.attach(service_name_label, 0, i, 1, 1)
            self.service_grid.attach(restart_btn, 1, i, 1, 1)

            self.service_buttons[service["service"]] = restart_btn

        self.service_grid.show_all()

    def online_update_clicked(self, widget):
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(
            "<b>" + _("Online Update") + "</b>\n\n"
            + _("This will update the system online.\nAre you sure?") + "\n\n"
            + _("The machine will restart during update. Do not disconnect the power.")
        )

    def local_update_clicked(self, widget):
        try:
            scan_result = self.update_engine.scan_usb_image()

            if scan_result["status"] == "error":
                error_message = ""
                if scan_result["error_code"] == "NO_USB_DEVICE":
                    error_message = _(
                        "No USB device found!\nPlease insert a USB drive with upgrade image.")
                elif scan_result["error_code"] == "NO_IMAGE_FILE":
                    error_message = _("No update image found in USB device!")
                elif scan_result["error_code"] == "VERSION_READ_FAILED":
                    error_message = _("Failed to read image version!")
                else:
                    error_message = _(
                        "Unknown error occurred during USB scan!")

                label = Gtk.Label(wrap=True, vexpand=True)
                usb_update_title = _("USB Update")
                label.set_markup(
                    f"<b>{usb_update_title}</b>\n\n{error_message}")

                buttons = [
                    {"name": _("OK"), "response": Gtk.ResponseType.OK,
                     "style": "dialog-info"},
                ]

                self._gtk.Dialog(_("USB Update"), buttons, label,
                                 lambda d, r: self._gtk.remove_dialog(d))
                return

            self.upload_file = scan_result["selected_image"]
            self.firmware_version = scan_result["firmware_version"]
            self.is_beta = scan_result.get("is_beta", False)
            self.local_update_confirm()

        except Exception as e:
            logging.error(f"Failed to scan USB image: {e}")
            label = Gtk.Label(wrap=True, vexpand=True)
            usb_update_title = _("USB Update")
            error_msg = _("Failed to scan USB device: %s").format(str(e))
            label.set_markup(f"<b>{usb_update_title}</b>\n\n{error_msg}")

            buttons = [
                {"name": _("OK"), "response": Gtk.ResponseType.OK,
                 "style": "dialog-info"},
            ]

            self._gtk.Dialog(_("USB Update"), buttons, label,
                             lambda d, r: self._gtk.remove_dialog(d))

    def local_update_confirm(self):
        if not self.upload_file or not self.firmware_version:
            return

        version_info = f"{self.firmware_version}"
        if self.is_beta:
            version_info += " <span color='red'>({})</span>".format(
                _("Beta Version"))

        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(
            "<b>" + _("USB Update") + "</b>\n\n"
            + _("Found update image: ") +
            f"{os.path.basename(self.upload_file)}\n\n"
            + _("Firmware version:") + f" {version_info}\n\n"
            + _("Are you sure to update to version {} ?").format(self.firmware_version) + "\n\n"
            + _("The machine will restart during update. Do not disconnect the power.")
        )

        buttons = [
            {"name": _("Update"), "response": Gtk.ResponseType.OK,
             "style": "dialog-info"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-error"},
        ]

        self._gtk.Dialog(_("USB Update"), buttons, label, self.do_local_update)

    def do_local_update(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK and self.upload_file:
            logging.info(f"Starting local update from: {self.upload_file}")
            label = Gtk.Label(wrap=True, vexpand=True)
            label.set_markup(
                "<b>" + _("USB Update") + "</b>\n\n"
                + _("Preparing for update, please wait...\n\nThis may take some time.\n\nDo not power off the device!")
            )

            self.upgrade_dialog = self._gtk.Dialog(
                title=_("USB Update"),
                buttons=None,
                content=label,
                callback=lambda d, r: None
            )

            GLib.timeout_add_seconds(0.1, self.execute_local_update)

    def execute_local_update(self):
        try:
            upgrade_result = self.update_engine.run_upgrade(
                self.upload_file, reboot=False)

            if hasattr(self, 'upgrade_dialog'):
                self._gtk.remove_dialog(self.upgrade_dialog)
                delattr(self, 'upgrade_dialog')

            if upgrade_result["status"] != "success":
                logging.error(f"USB update failed: {upgrade_result}")
                error_code = upgrade_result.get('error_code', 'UNKNOWN')
                label = Gtk.Label(wrap=True, vexpand=True)
                label.set_markup(
                    "<b>" + _("USB Update") + "</b>\n\n"
                    + _("USB update failed!") + "\n\n"
                    + _("The upgrade process did not complete successfully.\n\n")
                    + _("Error code:") + f" {error_code}\n\n"
                    + _("Please check the logs for more information.\n\n")
                    + _("Do not power off the device!\n\n")
                )

                buttons = [
                    {"name": _("OK"), "response": Gtk.ResponseType.OK,
                     "style": "dialog-error"},
                ]

                self._gtk.Dialog(_("USB Update"), buttons, label,
                                 lambda d, r: self._gtk.remove_dialog(d))

        except Exception as e:
            if hasattr(self, 'upgrade_dialog'):
                self._gtk.remove_dialog(self.upgrade_dialog)
                delattr(self, 'upgrade_dialog')

            logging.error(f"USB update failed: {e}")

            label = Gtk.Label(wrap=True, vexpand=True)
            label.set_markup(
                "<b>" + _("USB Update") + "</b>\n\n"
                + _("USB update failed!") + "\n\n"
                + _("An unexpected error occurred during the upgrade process.\n\n")
                + _("Error message:") + f"\n{str(e)}\n\n"
                + _("Please check the logs for more information.\n\n")
                + _("Do not power off the device!")
            )

            buttons = [
                {"name": _("OK"), "response": Gtk.ResponseType.OK,
                 "style": "dialog-error"},
            ]

            self._gtk.Dialog(_("USB Update"), buttons, label,
                             lambda d, r: self._gtk.remove_dialog(d))
        return False

    def factory_reset_clicked(self, widget):
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(
            "<b>" + _("Factory Reset") + "</b>\n\n"
            + _("This will restore factory settings!") + "\n\n"
            + _("All user data will be cleared.") + "\n"
            + _("Are you sure?") + "\n\n"
            + _("The system will reboot after reset.")
        )
        label.set_margin_top(20)
        clear_files_checkbox = Gtk.CheckButton(
            label=" " + _("Clear internal storage files"))
        clear_files_checkbox.set_halign(Gtk.Align.CENTER)
        clear_files_checkbox.set_valign(Gtk.Align.CENTER)
        clear_files_checkbox.set_active(False)

        grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        grid.set_row_spacing(20)
        grid.attach(label, 0, 0, 1, 1)
        grid.attach(clear_files_checkbox, 0, 1, 1, 1)

        buttons = [
            {"name": _("Reset"), "response": Gtk.ResponseType.OK,
             "style": "dialog-error"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-info"},
        ]

        self._gtk.Dialog(
            _("Factory Reset"),
            buttons,
            grid,
            self.factory_reset_confirm,
            clear_files_checkbox,
        )

    def factory_reset_confirm(self, dialog, response_id, clear_files_checkbox):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            clear_gcode = clear_files_checkbox.get_active()
            logging.info(f"Starting factory reset, clear gcode: {clear_gcode}")

            try:
                if clear_gcode:
                    logging.info(
                        "Executing full factory reset with gcode files deletion")
                    self.update_engine.misc_wipe_all()
                else:
                    logging.info(
                        "Executing factory reset without gcode files deletion")
                    self.update_engine.misc_wipe_overlay()

            except Exception as e:
                logging.error(f"Factory reset failed: {e}")
                label = Gtk.Label(wrap=True, vexpand=True)
                factory_reset_title = _("Factory Reset")
                error_msg = _("Factory reset failed: %s").format(str(e))
                label.set_markup(
                    f"<b>{factory_reset_title}</b>\n\n{error_msg}")

                buttons = [
                    {"name": _("OK"), "response": Gtk.ResponseType.OK,
                     "style": "dialog-info"},
                ]

                self._gtk.Dialog(_("Factory Reset"), buttons,
                                 label, lambda d, r: self._gtk.remove_dialog(d))

    def export_logs_clicked(self, widget):
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(
            "<b>" + _("Export Logs") + "</b>\n\n"
            + _("Please insert a USB drive first!\nThis will export logs to the USB device.\n\nAre you sure you want to continue?")
        )

        buttons = [
            {"name": _("Export"), "response": Gtk.ResponseType.OK,
             "style": "dialog-info"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-error"},
        ]

        self._gtk.Dialog(_("Export Logs"), buttons,
                         label, self.confirm_export_logs)

    def confirm_export_logs(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            self.show_exporting_dialog()
            GLib.timeout_add_seconds(1, self.execute_export_logs)

    def show_exporting_dialog(self):
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(
            "<b>" + _("Export Logs") + "</b>\n\n"
            + _("Exporting logs, please wait...\n\nThis will take some time.")
        )

        self.exporting_dialog = self._gtk.Dialog(
            title=_("Export Logs"),
            buttons=None,
            content=label,
            callback=lambda dialog, response: None
        )

    def execute_export_logs(self):
        try:
            export_result = self.update_engine.export_logs()

            if hasattr(self, 'exporting_dialog'):
                self._gtk.remove_dialog(self.exporting_dialog)
                delattr(self, 'exporting_dialog')

            if export_result["status"] == "success":
                logging.info(f"Logs exported successfully: {export_result}")

                label = Gtk.Label(wrap=True, vexpand=True)
                label.set_markup(
                    "<b>" + _("Export Logs") + "</b>\n\n"
                    + _("Logs exported successfully!") + "\n\n"
                    + _("File saved to:") +
                    f"{os.path.basename(export_result['output_file'])}"
                )

                buttons = [
                    {"name": _("OK"), "response": Gtk.ResponseType.OK,
                     "style": "dialog-info"},
                ]

                self._gtk.Dialog(_("Export Logs"), buttons, label,
                                 lambda d, r: self._gtk.remove_dialog(d))
            else:
                error_message = ""
                if export_result["error_code"] == "NO_USB_DEVICE":
                    error_message = _("No USB device found!")
                elif export_result["error_code"] == "NO_LOG_FOLDERS":
                    error_message = _("No log folders found!")
                elif export_result["error_code"] == "EXPORT_FAILED":
                    error_message = _("Failed to export logs!") + \
                        f"\n{export_result['message']}"
                else:
                    error_message = _(
                        "Unknown error occurred during log export!")

                logging.error(f"Failed to export logs: {export_result}")

                label = Gtk.Label(wrap=True, vexpand=True)
                export_logs_title = _("Export Logs")
                label.set_markup(
                    f"<b>{export_logs_title}</b>\n\n{error_message}")

                buttons = [
                    {"name": _("OK"), "response": Gtk.ResponseType.OK,
                     "style": "dialog-error"},
                ]

                self._gtk.Dialog(_("Export Logs"), buttons, label,
                                 lambda d, r: self._gtk.remove_dialog(d))

        except Exception as e:
            if hasattr(self, 'exporting_dialog'):
                self._gtk.remove_dialog(self.exporting_dialog)
                delattr(self, 'exporting_dialog')

            logging.error(f"Failed to export logs: {e}")

            label = Gtk.Label(wrap=True, vexpand=True)
            label.set_markup(
                "<b>" + _("Export Logs") + "</b>\n\n"
                + _("Failed to export logs!") + f"\n\n{str(e)}"
            )

            buttons = [
                {"name": _("OK"), "response": Gtk.ResponseType.OK,
                 "style": "dialog-error"},
            ]

            self._gtk.Dialog(_("Export Logs"), buttons, label,
                             lambda d, r: self._gtk.remove_dialog(d))
        return False

    def restart_service(self, widget, service_name):
        label = Gtk.Label(wrap=True, vexpand=True)
        label.set_markup(
            "<b>" + _("Restart Service") + "</b>\n\n"
            + _("Are you sure to restart: ") + f"{service_name}?"
        )

        buttons = [
            {"name": _("Restart"), "response": Gtk.ResponseType.OK,
             "style": "dialog-warning"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-error"},
        ]

        self._gtk.Dialog(
            _("Restart Service"),
            buttons,
            label,
            self.restart_service_confirm,
            service_name,
        )

    def restart_service_confirm(self, dialog, response_id, service_name):
        self._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            logging.info(f"Restarting service: {service_name}")

            if service_name == "klipper":
                self._screen._ws.send_method(
                    "machine.services.restart",
                    {"service": "klipper"}
                )
            elif service_name == "moonraker":
                self._screen._ws.send_method(
                    "machine.services.restart",
                    {"service": "moonraker"}
                )
            elif service_name == "KlipperScreen":
                os.system("systemctl restart KlipperScreen.service")
            elif service_name == "go2rtc":
                self._screen._ws.send_method(
                    "machine.services.restart",
                    {"service": "go2rtc"}
                )

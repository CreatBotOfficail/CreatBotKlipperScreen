import subprocess
import os
import logging


class ModelConfig:

    def __init__(self):
        home = os.path.expanduser("~/")
        printer_data_config = os.path.join(home, "printer_data", "config")
        self.moonraker_config_path = printer_data_config + "/moonraker.conf"
        self.klipperscreen_config_path = printer_data_config + "/KlipperScreen.conf"
        self.printer_config_path = printer_data_config + "/printer.cfg"

    def get_mac_address(self, interface):
        try:
            result = subprocess.run(
                ["ip", "link", "show", interface], capture_output=True, text=True
            )
            output = result.stdout

            for line in output.split("\n"):
                if "link/ether" in line:
                    mac_address = line.split()[1]
                    return mac_address

        except Exception as e:
            logging.error(f"get mac address error: {e}")
            return None

    def generate_machine_name(self, model):
        mac_address = self.get_mac_address("eth0")
        if mac_address:
            mac_address = mac_address.replace(":", "")
            last_four = mac_address[-4:]
            machine_name = f"{model}-{last_four.upper()}"
            return machine_name
        else:
            return None

    def write_mdns_config(self, device_name):
        if device_name:
            try:
                with open(self.moonraker_config_path, "r") as file:
                    lines = file.readlines()

                with open(self.moonraker_config_path, "w") as file:
                    found_zeroconf_section = False
                    modified = False

                    for line in lines:
                        if line.strip().startswith("[zeroconf]"):
                            found_zeroconf_section = True
                        elif found_zeroconf_section and line.strip().startswith(
                            "mdns_hostname"
                        ):
                            file.write(f"mdns_hostname:{device_name}\n")
                            found_zeroconf_section = False
                            modified = True
                            continue
                        elif found_zeroconf_section and line.strip().startswith(
                            "enable_ssdp"
                        ):
                            file.write("enable_ssdp: True")
                            found_zeroconf_section = False
                            modified = True
                            continue

                        file.write(line)

                    if not modified:
                        file.write("\n[zeroconf]\n")
                        file.write(f"mdns_hostname:{device_name}\n")
                        file.write("enable_ssdp: True")
                logging.info(f"Setting MDNS address to {device_name}")
            except FileNotFoundError:
                logging.error(
                    f"The configuration file {self.moonraker_config_path} not found"
                )

    def write_device_name_config(self, device_name):
        if device_name:
            try:
                with open(self.klipperscreen_config_path, "r+") as file:
                    lines = file.readlines()
                    file.seek(0)
                    found_printer_section = False
                    for i, line in enumerate(lines):
                        if line.strip().startswith("[printer"):
                            lines[i] = f"[printer {device_name}]\n"
                            found_printer_section = True
                            break
                    if not found_printer_section:
                        lines.insert(0, f"[printer {device_name}]\n")
                    file.truncate(0)
                    file.writelines(lines)
                logging.info(f"Setting device name to {device_name}")
            except FileNotFoundError:
                logging.error(
                    f"Configuration file {self.klipperscreen_config_path} not found."
                )

    def wirte_printer_config(self, device_name):
        config_dict = {
            "CreatBot_F430NX": "CreatBot_F430NX",
            "CreatBot_D600Pro2HS": "CreatBot_D600Pro2",
            "CreatBot_D600Pro2HS_KIT": "CreatBot_D600Pro2_V0",
            "CreatBot_D1000HS": "CreatBot_D1000",
            "CreatBot_D1000HS_KIT": "CreatBot_D1000_V0",
            "CreatBot_P800": "CreatBot_P800",
        }
        if device_name:
            source_path = f"{os.path.expanduser('~')}/klipper/config/{config_dict.get(device_name)}/"
            target_path = f"{os.path.expanduser('~')}/printer_data/config/"
            if not os.path.exists(target_path):
                os.makedirs(target_path)
            source_base_path = os.path.join(source_path, os.path.basename("base.cfg"))
            target_base_path = os.path.join(target_path, os.path.basename("base.cfg"))
            try:
                if os.path.islink(target_base_path) or os.path.exists(target_base_path):
                    os.remove(target_base_path)
                os.symlink(source_base_path, target_base_path)
                logging.info(f"Created config symlink for {device_name}.")
            except FileExistsError:
                logging.error(f"Failed to create config symlink for {device_name}.")
            except PermissionError:
                logging.error(f"No permission to create symlink for {device_name}.")
            except Exception as e:
                logging.error(f"Error creating symlink for{device_name}:{e}")

            source_printer_path = os.path.join(source_path, os.path.basename("printer.cfg"))
            target_printer_path = os.path.join(target_path, os.path.basename("printer.cfg"))
            command = ['cp','-f', source_printer_path, target_printer_path]
            try:
                subprocess.run(command, check=True, text=True, capture_output=True)
                logging.info(f"Configuration file copied successfully. {source_printer_path}' to '{target_printer_path}'")
            except subprocess.CalledProcessError as e:
                logging.error(f"Copy error config file: {e.stderr}")
            except Exception as e:
                logging.error(f"Copy error printer file: {e.stderr}")

    def wirte_hostname(self, device_name):

        try:
            current_hostname = subprocess.check_output(["hostname"], text=True).strip()
            logging.info(f"Current hostname: {current_hostname}")
            subprocess.run(["hostnamectl", "set-hostname", device_name], check=True)
            logging.info(f"Hostname has been changed to: {device_name}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error while executing command: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")

    def generate_config(self, model):
        model_name = model
        model_name = model_name.split("_")[1]
        device_name = self.generate_machine_name(model_name)
        self.write_mdns_config(device_name)
        self.write_device_name_config(device_name)
        self.wirte_printer_config(model)
        self.wirte_hostname(device_name)
        os.system("systemctl restart klipper.service")
        os.system("systemctl restart moonraker.service")
        os.system("systemctl restart KlipperScreen.service")

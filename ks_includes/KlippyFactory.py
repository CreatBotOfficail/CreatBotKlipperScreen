import logging
import os
import configparser
import subprocess

from ks_includes.KlippyGcodes import KlippyGcodes

update_engine_available = False
try:
    from update_engine import UpdateEngine
    update_engine_available = True
    logging.info("UpdateEngine imported successfully")
except ImportError:
    logging.info("UpdateEngine not available")


class KlippyFactory:

    @staticmethod
    def clean_mainsail_web_config(connect):
        connect.get_database_list(KlippyFactory.clean_database_callback, connect, "mainsail")
        logging.info("clean mainsail web config")

    @staticmethod
    def clean_maintenance(connect):
        connect.get_database_list(KlippyFactory.clean_database_callback, connect, "maintenance")
        logging.info("clean maintenance config")

    @staticmethod
    def clean_gcode_metadata(connect):
        connect.get_database_list(KlippyFactory.clean_database_callback, connect, "gcode_metadata")
        logging.info("clean gcode metadata")

    @staticmethod
    def clean_update_manager(connect):
        connect.get_database_list(KlippyFactory.clean_database_callback, connect, "update_manager")
        logging.info("clean update manager")

    @staticmethod
    def clean_database_callback(result, method, params, connect, option):

        if "server.database.list" == method:
            connect.get_database_item(option, None, KlippyFactory.clean_database_callback, connect, option)
        elif "server.database.get_item" == method:
            if "result" in result and option == result["result"]["namespace"]:
                for key in result["result"]["value"]:
                    connect.del_database_item(option, key, None)

    @staticmethod
    def clean_job_history(connect):
        connect.reset_job_history_totals()
        connect.del_all_job_history()
        logging.info("clean_job_history")

    @staticmethod
    def reset_advanced_setting_factory(connect):
        option_list = {
            "adaptive_meshing": False,
            "power_loss_recovery": True,
            "auto_change_nozzle": False,
            "door_detect": "Disabled",
        }
        for key, val in option_list.items():
            script = KlippyGcodes.set_save_variables(key, val)
            connect.gcode_script(script)
        logging.info("reset advanced setting")

    @staticmethod
    def clean_screen_config(config, guide=False):
        config.del_all(guide)
        logging.info("clean screen config")

    @staticmethod
    def hostname_factory():
        logging.info("clean screen config")

    @staticmethod
    def clean_wlan():
        command = "nmcli connection show | grep wifi | awk '{print $1}' | xargs -I {} nmcli connection delete {}"
        subprocess.run(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logging.info("clean wlan config")

    @staticmethod
    def clean_gocde_file():
        exclude_dir = [
            ".PresetModel",
        ]
        command = "lsblk | grep '/home/klipper/printer_data/gcodes'"
        res = subprocess.run(command, shell=True, text=True, capture_output=True)

        if res.returncode == 0:
            output = res.stdout.strip()
            if output:
                lines = output.split("\n")
                for line in lines:
                    result = line.strip().split("/")[-1]
                    exclude_dir.append(f"{result}")

        homedir = os.path.expanduser("~")
        configdir = os.path.join(homedir, "printer_data", "gcodes")
        KlippyFactory.clear_directory(configdir, exclude_dirs=exclude_dir)
        logging.info("clean gocde file")

    @staticmethod
    def clean_log_file():
        homedir = os.path.expanduser("~")
        logdir = os.path.join(homedir, "printer_data", "logs")
        KlippyFactory.clear_directory(logdir)
        logging.info("clean log directory")

    @staticmethod
    def reset_user_password(connect):
        connect.reset_user_password()
        logging.info("Reset user password")

    @staticmethod
    def clean_config_backup_file():
        exclude_files = [
            "base.cfg",
            "printer.cfg",
            "config_variables.cfg",
            "crowsnest.conf",
            "KlipperScreen.conf",
            "mainsail.cfg",
            "moonraker.conf",
        ]
        exclude_dirs = ["module"]
        homedir = os.path.expanduser("~")
        configdir = os.path.join(homedir, "printer_data", "config")
        KlippyFactory.clear_directory(configdir, exclude_files, exclude_dirs)
        logging.info("clean config backup file")

    @staticmethod
    def clear_directory(directory, exclude_files=None, exclude_dirs=None):
        exclude_files = exclude_files or []
        exclude_dirs = exclude_dirs or []

        if os.path.exists(directory):
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.isdir(file_path) and filename in exclude_dirs:
                    continue
                if os.path.isfile(file_path) and filename in exclude_files:
                    continue

                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        for sub_filename in os.listdir(file_path):
                            sub_file_path = os.path.join(file_path, sub_filename)
                            if os.path.isfile(sub_file_path):
                                os.remove(sub_file_path)
                            elif os.path.isdir(sub_file_path):
                                os.rmdir(sub_file_path)
                        os.rmdir(file_path)
                except Exception as e:
                    logging.error(f"Error deleting {file_path}: {e}")
        else:
            logging.info(f"The directory {directory} does not exist.")

    @staticmethod
    def restart_application():
        os.system("systemctl restart klipper.service")
        os.system("systemctl restart moonraker.service")
        os.system("systemctl restart KlipperScreen.service")

    @staticmethod
    def user_factory_reset(connect, config, clean_gcode=False):
        KlippyFactory.clean_screen_config(config)
        KlippyFactory.clean_mainsail_web_config(connect)
        KlippyFactory.clean_maintenance(connect)
        KlippyFactory.clean_gcode_metadata(connect)
        KlippyFactory.clean_update_manager(connect)
        KlippyFactory.clean_job_history(connect)
        KlippyFactory.reset_advanced_setting_factory(connect)
        KlippyFactory.reset_user_password(connect)
        KlippyFactory.clean_wlan()
        KlippyFactory.clean_log_file()
        if clean_gcode:
            KlippyFactory.clean_gocde_file()
        logging.info("User factory reset completed")
        KlippyFactory.restart_application()

    @staticmethod
    def backup_printer_config():
        source_file = "/opt/printer_data/config/printer.cfg"
        backup_dir = "/oem/config"
        backup_file = os.path.join(backup_dir, "printer.cfg")

        try:
            if not os.path.exists(source_file):
                logging.warning(f"Source file {source_file} does not exist")
                return

            with open(source_file, "r") as f:
                lines = f.readlines()

            in_save_config = False
            backup_lines = []
            current_section = None
            has_content = False
            sections_to_backup = {
                "probe": ["z_offset"],
                "stepper_z": ["position_endstop"]
            }

            for line in lines:
                stripped_line = line.strip()

                if "#*# <---------------------- SAVE_CONFIG ---------------------->" in stripped_line:
                    in_save_config = True
                    continue

                if in_save_config:
                    if stripped_line.startswith("#*# [") and stripped_line.endswith("]"):
                        section_name = stripped_line[5:-1]
                        current_section = section_name
                        if section_name in sections_to_backup:
                            if has_content:
                                backup_lines.append("#*# \n")
                            backup_lines.append(line)
                    elif stripped_line.startswith("#*# ") and ("=" in stripped_line or ":" in stripped_line):
                        if current_section and current_section in sections_to_backup:
                            key = stripped_line[4:].split("=")[0].split(":")[0].strip()
                            if key in sections_to_backup[current_section]:
                                backup_lines.append(line)
                                has_content = True

            if backup_lines:
                if not os.path.exists(backup_dir):
                    os.makedirs(backup_dir, exist_ok=True)
                    logging.info(f"Created backup directory {backup_dir}")

                with open(backup_file, "w") as f:
                    f.writelines(backup_lines)

                logging.info(f"Printer config backed up to {backup_file}")
            else:
                logging.warning("No matching config items found in SAVE_CONFIG section")

        except Exception as e:
            logging.error(f"Error backing up printer config: {e}")

    @staticmethod
    def backup_nozzle_offset_variables():
        source_file = "/opt/printer_data/config/config_variables.cfg"
        backup_dir = "/oem/config"
        backup_file = os.path.join(backup_dir, "config_variables.cfg")
        variables_to_backup = ["nozzle_x_offset_val", "nozzle_y_offset_val", "nozzle_z_offset_val"]

        try:
            if not os.path.exists(source_file):
                logging.warning(f"Source file {source_file} does not exist")
                return

            config = configparser.ConfigParser()
            config.read(source_file)

            if "Variables" not in config:
                logging.warning("No [Variables] section found in config file")
                return

            backup_config = configparser.ConfigParser()
            backup_config["Variables"] = {}

            for var in variables_to_backup:
                if var in config["Variables"]:
                    backup_config["Variables"][var] = config["Variables"][var]
                    logging.info(f"Backed up {var} = {config['Variables'][var]}")
                else:
                    logging.warning(f"Variable {var} not found in config file")

            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir, exist_ok=True)
                logging.info(f"Created backup directory {backup_dir}")

            with open(backup_file, "w") as f:
                backup_config.write(f)

            logging.info(f"Nozzle offset variables backed up to {backup_file}")

        except Exception as e:
            logging.error(f"Error backing up nozzle offset variables: {e}")

    @staticmethod
    def production_factory_reset(connect, config):
        if update_engine_available:
            logging.info("Executing production factory reset with update_engine format")
            try:
                try:
                    from machine_config import MachineConfig
                    cfg = MachineConfig()
                    cfg.set("first_boot", True)
                except Exception as e:
                    logging.error(f"Error setting first_boot flag: {e}")
                KlippyFactory.backup_printer_config()
                KlippyFactory.backup_nozzle_offset_variables()
                update_engine = UpdateEngine()
                update_engine.misc_wipe_all()
                logging.info("Production factory reset completed with format")
            except Exception as e:
                logging.error(f"Production factory reset with format failed: {e}")
                # Fallback to legacy reset if update_engine fails
                KlippyFactory._legacy_production_factory_reset(connect, config)
        else:
            logging.info("UpdateEngine not available, using legacy production factory reset")
            KlippyFactory._legacy_production_factory_reset(connect, config)

    @staticmethod
    def _legacy_production_factory_reset(connect, config):
        KlippyFactory.clean_screen_config(config, True)
        KlippyFactory.clean_mainsail_web_config(connect)
        KlippyFactory.clean_maintenance(connect)
        KlippyFactory.clean_gcode_metadata(connect)
        KlippyFactory.clean_update_manager(connect)
        KlippyFactory.clean_job_history(connect)
        KlippyFactory.reset_advanced_setting_factory(connect)
        KlippyFactory.reset_user_password(connect)
        KlippyFactory.clean_wlan()
        KlippyFactory.clean_gocde_file()
        KlippyFactory.clean_log_file()
        KlippyFactory.clean_config_backup_file()
        logging.info("Production factory reset completed")
        KlippyFactory.restart_application()

import logging
import os
import subprocess

from ks_includes.KlippyGcodes import KlippyGcodes


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
        homedir = os.path.expanduser("~")
        configdir = os.path.join(homedir, "printer_data", "config")
        KlippyFactory.clear_directory(configdir, exclude_files)
        logging.info("clean config backup file")

    @staticmethod
    def clear_directory(directory, exclude_files=None, exclude_dirs=None):
        exclude_files = exclude_files or []
        exclude_dirs = exclude_dirs or []

        if os.path.exists(directory):
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if filename in exclude_files:
                    continue
                if filename in exclude_dirs and os.path.isdir(file_path):
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
        KlippyFactory.clean_wlan()
        KlippyFactory.clean_log_file()
        if clean_gcode:
            KlippyFactory.clean_gocde_file()
        logging.info("User factory reset completed")
        KlippyFactory.restart_application()

    @staticmethod
    def production_factory_reset(connect, config):
        KlippyFactory.clean_screen_config(config, True)
        KlippyFactory.clean_mainsail_web_config(connect)
        KlippyFactory.clean_maintenance(connect)
        KlippyFactory.clean_gcode_metadata(connect)
        KlippyFactory.clean_update_manager(connect)
        KlippyFactory.clean_job_history(connect)
        KlippyFactory.reset_advanced_setting_factory(connect)
        KlippyFactory.clean_wlan()
        KlippyFactory.clean_gocde_file()
        KlippyFactory.clean_log_file()
        KlippyFactory.clean_config_backup_file()
        logging.info("Production factory reset completed")
        KlippyFactory.restart_application()

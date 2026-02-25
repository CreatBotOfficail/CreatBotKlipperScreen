# This is the backend of the UI panel that communicates to sdbus-networkmanager
# TODO device selection/swtichability
# Alfredo Monclus (alfrix) 2024
import subprocess
import logging
import ipaddress

import sdbus
from sdbus_block.networkmanager import (
    NetworkManager,
    NetworkDeviceGeneric,
    NetworkDeviceWired,
    NetworkDeviceWireless,
    NetworkConnectionSettings,
    NetworkManagerSettings,
    AccessPoint,
    NetworkManagerConnectionProperties,
    IPv4Config,
    ActiveConnection,
    enums,
    exceptions,
)
from gi.repository import GLib, Gio
from uuid import uuid4

NONE = 0  # The access point has no special security requirements.
PAIR_WEP40 = 1  # 40/64-bit WEP is supported for pairwise/unicast encryption.
PAIR_WEP104 = 2  # 104/128-bit WEP is supported for pairwise/unicast encryption.
PAIR_TKIP = 4  # TKIP is supported for pairwise/unicast encryption.
PAIR_CCMP = 8  # AES/CCMP is supported for pairwise/unicast encryption.
GROUP_WEP40 = 16  # 40/64-bit WEP is supported for group/broadcast encryption.
GROUP_WEP104 = 32  # 104/128-bit WEP is supported for group/broadcast encryption.
GROUP_TKIP = 64  # TKIP is supported for group/broadcast encryption.
GROUP_CCMP = 128  # AES/CCMP is supported for group/broadcast encryption.
KEY_MGMT_PSK = 256  # WPA/RSN Pre-Shared Key encryption
KEY_MGMT_802_1X = 512  # 802.1x authentication and key management
KEY_MGMT_SAE = 1024  # WPA/RSN Simultaneous Authentication of Equals
KEY_MGMT_OWE = 2048  # WPA/RSN Opportunistic Wireless Encryption
KEY_MGMT_OWE_TM = 4096  # WPA/RSN Opportunistic Wireless Encryption transition mode
KEY_MGMT_EAP_SUITE_B_192 = 8192  # WPA3 Enterprise Suite-B 192


def get_encryption(flags):
    if flags == 0:
        return "Open"

    encryption_mapping = {
        PAIR_WEP40: "WEP",
        PAIR_WEP104: "WEP",
        PAIR_TKIP: "TKIP",
        PAIR_CCMP: "AES",
        GROUP_WEP40: "WEP",
        GROUP_WEP104: "WEP",
        GROUP_TKIP: "TKIP",
        GROUP_CCMP: "AES",
        KEY_MGMT_PSK: "WPA-PSK",
        KEY_MGMT_802_1X: "802.1x",
        KEY_MGMT_SAE: "WPA-SAE",
        KEY_MGMT_OWE: "OWE",
        KEY_MGMT_OWE_TM: "OWE-TM",
        KEY_MGMT_EAP_SUITE_B_192: "WPA3-B192",
    }

    encryption_methods = []
    for flag, method_name in encryption_mapping.items():
        if flags & flag and method_name not in encryption_methods:
            encryption_methods.append(method_name)
    return " ".join(encryption_methods)


def WifiChannels(freq: str):
    if freq == "2484":
        return "2.4", "14"
    try:
        freq = float(freq)
    except ValueError:
        return "?", "?"
    if 2412 <= freq <= 2472:
        return "2.4", str(int((freq - 2407) / 5))
    elif 3657.5 <= freq <= 3692.5:
        return "3", str(int((freq - 3000) / 5))
    elif 4915 <= freq <= 4980:
        return "5", str(int((freq - 4000) / 5))
    elif 5035 <= freq <= 5885:
        return "5", str(int((freq - 5000) / 5))
    elif 6455 <= freq <= 7115:
        return "6", str(int((freq - 5950) / 5))
    else:
        return "?", "?"


class SdbusNm:

    def __init__(self, popup_callback):
        self.ensure_nm_running()
        self.system_bus = sdbus.sd_bus_open_system()  # We need system bus
        if self.system_bus is None:
            return None
        sdbus.set_default_bus(self.system_bus)
        self.nm = NetworkManager()
        self.wlan_device = (
            self.get_wireless_interfaces()[0]
            if self.get_wireless_interfaces()
            else None
        )
        self.wifi = self.wlan_device is not None
        self.monitor_connection = False
        self.wifi_state = -1
        self.popup = popup_callback

    def _get_dbus_property(self, object_path, interface_name, property_name):
        """Get a DBus property using Gio.DBusProxy."""
        try:
            proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                'org.freedesktop.NetworkManager',
                object_path,
                'org.freedesktop.DBus.Properties',
                None
            )
            result = proxy.call_sync(
                'Get',
                GLib.Variant('(ss)', (interface_name, property_name)),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            return result.unpack()[0]
        except Exception as e:
            logging.debug(f"Failed to get DBus property {interface_name}.{property_name}: {e}")
            return None

    def _get_wired_device_path(self, interface):
        """Get the DBus path for a wired interface."""
        for device_path in self.nm.get_devices():
            device = NetworkDeviceGeneric(device_path)
            if device.device_type == enums.DeviceType.ETHERNET:
                if device.interface == interface:
                    return device_path
        return None

    def ensure_nm_running(self):
        """Check if NetworkManager is running by trying to connect to it via DBus."""
        try:
            proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                'org.freedesktop.NetworkManager',
                '/org/freedesktop/NetworkManager',
                'org.freedesktop.DBus.Properties',
                None
            )
            # Try to get the Version property to verify the service is running
            result = proxy.call_sync(
                'Get',
                GLib.Variant('(ss)', ('org.freedesktop.NetworkManager', 'Version')),
                Gio.DBusCallFlags.NONE,
                5000,  # 5 second timeout
                None
            )
            logging.debug(f"NetworkManager version: {result.unpack()[0]}")
        except Exception as e:
            logging.exception(f"Failed to detect NetworkManager service: {e}")
            raise RuntimeError(f"Failed to detect NetworkManager service: {e}") from e

    def is_wifi_enabled(self):
        return self.nm.wireless_enabled

    def get_interfaces(self):
        return [
            NetworkDeviceGeneric(device).interface for device in self.nm.get_devices()
        ]

    def get_wireless_interfaces(self):
        devices = {path: NetworkDeviceGeneric(path) for path in self.nm.get_devices()}
        return [
            NetworkDeviceWireless(path)
            for path, device in devices.items()
            if device.device_type == enums.DeviceType.WIFI
        ]

    def get_primary_interface(self):
        if self.nm.primary_connection == "/":
            if self.wlan_device:
                return self.wlan_device.interface
            return next(
                (interface for interface in self.get_interfaces() if interface != "lo"),
                None,
            )
        gateway = ActiveConnection(self.nm.primary_connection).devices[0]
        return NetworkDeviceGeneric(gateway).interface

    def get_wired_interfaces(self):
        devices = {path: NetworkDeviceGeneric(path) for path in self.nm.get_devices()}
        return [
            device.interface
            for device in devices.values()
            if device.device_type == enums.DeviceType.ETHERNET
        ]

    def get_wired_interface(self):
        interfaces = self.get_wired_interfaces()
        return interfaces[0] if interfaces else None

    def get_wired_carrier_state(self, interface):
        """Get the carrier (cable connected) state for a wired interface using DBus."""
        if not interface:
            return False
        device_path = self._get_wired_device_path(interface)
        if not device_path:
            return False
        carrier = self._get_dbus_property(
            device_path,
            'org.freedesktop.NetworkManager.Device.Wired',
            'Carrier'
        )
        if carrier is None:
            # Fallback to checking device state
            device = NetworkDeviceWired(device_path)
            return device.state == 100  # NM_DEVICE_STATE_ACTIVATED
        return bool(carrier)

    def get_wired_mac_address(self, interface):
        """Get the MAC address of the wired interface using DBus."""
        if not interface:
            return "--:--:--:--:--:--"
        device_path = self._get_wired_device_path(interface)
        if not device_path:
            return "--:--:--:--:--:--"
        try:
            device = NetworkDeviceWired(device_path)
            return device.hw_address or "--:--:--:--:--:--"
        except Exception as e:
            logging.debug(f"Failed to get MAC address: {e}")
            return "--:--:--:--:--:--"

    def get_wireless_mac_address(self):
        if self.wlan_device:
            return self.wlan_device.hw_address
        return "--:--:--:--:--:--"

    def get_wireless_ip_address(self):
        if self.wlan_device:
            if self.wlan_device.active_connection and self.wlan_device.active_connection != "/":
                active_connection = ActiveConnection(self.wlan_device.active_connection)
                if active_connection.ip4_config and active_connection.ip4_config != "/":
                    ip_info = IPv4Config(active_connection.ip4_config)
                    if ip_info.address_data:
                        return ip_info.address_data[0]["address"][1]
        return "?"

    def get_wireless_connection_name(self):
        """Get the connection name for the wireless interface using DBus."""
        if not self.wlan_device:
            return None
        try:
            if self.wlan_device.active_connection and self.wlan_device.active_connection != "/":
                active_connection = ActiveConnection(self.wlan_device.active_connection)
                return active_connection.id
        except Exception as e:
            logging.debug(f"Failed to get wireless connection name: {e}")
        return None

    def get_wireless_dhcp_state(self):
        """Check if wireless connection is using DHCP using DBus."""
        try:
            if self.wlan_device and self.wlan_device.active_connection and self.wlan_device.active_connection != "/":
                active_connection = ActiveConnection(self.wlan_device.active_connection)
                if active_connection.connection and active_connection.connection != "/":
                    settings = NetworkConnectionSettings(active_connection.connection)
                    profile = settings.get_profile()
                    return profile.ipv4.method == 'auto'
        except Exception as e:
            logging.debug(f"Failed to get wireless DHCP state: {e}")
        return True

    def get_wireless_connection_info(self):
        """Get wireless connection network info using DBus."""
        info = {
            "ip_address": "",
            "netmask": "",
            "gateway": "",
            "dns": "",
        }

        if not self.wlan_device:
            return info

        try:
            # Get IP info from active connection
            if self.wlan_device.active_connection and self.wlan_device.active_connection != "/":
                active_connection = ActiveConnection(self.wlan_device.active_connection)

                # Get IP configuration
                if active_connection.ip4_config and active_connection.ip4_config != "/":
                    ip4_config = IPv4Config(active_connection.ip4_config)

                    # Get address
                    if ip4_config.address_data:
                        addr_data = ip4_config.address_data[0]
                        info["ip_address"] = addr_data.get("address", ("s", ""))[1]
                        prefix = addr_data.get("prefix", ("u", 0))[1]
                        info["netmask"] = self.prefix_to_netmask(str(prefix))

                    # Get gateway
                    try:
                        gateway = ip4_config.gateway
                        if gateway:
                            info["gateway"] = gateway
                    except Exception:
                        pass

                    # Get DNS
                    try:
                        dns_data = ip4_config.nameserver_data
                        if dns_data:
                            dns_list = [d.get("address", ("s", ""))[1] for d in dns_data]
                            info["dns"] = ", ".join(dns_list)
                    except Exception:
                        pass

            # If no active connection or missing info, try connection settings
            if not info["ip_address"] and active_connection.connection and active_connection.connection != "/":
                settings = NetworkConnectionSettings(active_connection.connection)
                profile = settings.get_profile()

                if profile.ipv4.addresses:
                    addr = profile.ipv4.addresses[0] if profile.ipv4.addresses else None
                    address, prefix = self._parse_profile_ipv4_address(addr)
                    if address and prefix:
                        info["ip_address"] = address
                        info["netmask"] = self.prefix_to_netmask(prefix)

                if profile.ipv4.gateway:
                    info["gateway"] = profile.ipv4.gateway

                if profile.ipv4.dns:
                    info["dns"] = ", ".join(self._dns_to_text_list(profile.ipv4.dns))

        except Exception as e:
            logging.debug(f"Failed to get wireless connection info: {e}")

        return info

    def _set_ipv4_address(self, profile, address, prefix, gateway=None):
        """Set IPv4 address in legacy DBus format: [[addr_u32, prefix, gw_u32]]."""
        gateway_u32 = self._ipv4_to_u32(gateway) if gateway and self.is_valid_ipv4(gateway) else 0
        profile.ipv4.addresses = [[self._ipv4_to_u32(address), int(prefix), gateway_u32]]
        profile.ipv4.address_data = []

    @staticmethod
    def _ipv4_to_u32(address):
        """Convert dotted IPv4 string to DBus uint32 representation."""
        return int.from_bytes(ipaddress.IPv4Address(address).packed, byteorder='little')

    @staticmethod
    def _u32_to_ipv4(value):
        """Convert DBus uint32 IPv4 value to dotted string."""
        return str(ipaddress.IPv4Address(int(value).to_bytes(4, byteorder='little')))

    def _dns_to_u32_list(self, dns_values):
        """Normalize DNS values to uint32 list expected by NetworkManager settings."""
        return [self._ipv4_to_u32(dns) for dns in dns_values if self.is_valid_ipv4(dns)]

    def _dns_to_text_list(self, dns_values):
        """Normalize profile DNS values into dotted IPv4 strings."""
        result = []
        for dns in dns_values:
            if isinstance(dns, int):
                try:
                    result.append(self._u32_to_ipv4(dns))
                except Exception:
                    continue
            elif isinstance(dns, str) and self.is_valid_ipv4(dns):
                result.append(dns)
        return result

    def _parse_profile_ipv4_address(self, address_entry):
        """Parse profile.ipv4.addresses entry from either legacy int-array or string format."""
        if isinstance(address_entry, str):
            if '/' in address_entry:
                return address_entry.rsplit('/', 1)
            return None, None

        if isinstance(address_entry, (list, tuple)) and len(address_entry) >= 2:
            try:
                address = self._u32_to_ipv4(address_entry[0])
                prefix = str(int(address_entry[1]))
                return address, prefix
            except Exception:
                return None, None

        return None, None

    def set_wireless_dhcp(self, enable=True):
        """Enable or disable DHCP for wireless connection using DBus."""
        if not self.wlan_device or not self.wlan_device.active_connection or self.wlan_device.active_connection == "/":
            return {"error": "no_connection", "message": _("No wireless connection available")}

        try:
            active_connection = ActiveConnection(self.wlan_device.active_connection)
            conn_path = active_connection.connection

            if not conn_path or conn_path == "/":
                return {"error": "no_connection", "message": _("No wireless connection available")}

            settings = NetworkConnectionSettings(conn_path)
            profile = settings.get_profile()

            if enable:
                profile.ipv4.method = 'auto'
                profile.ipv4.address_data = []
                profile.ipv4.addresses = None
                profile.ipv4.gateway = None
                profile.ipv4.dns = []
            else:
                info = self.get_wireless_connection_info()
                ip = info.get("ip_address", "")
                netmask = info.get("netmask", "")
                gateway = info.get("gateway", "")
                dns = info.get("dns", "")

                if not self.is_valid_ipv4(ip):
                    ip = "0.0.0.0"
                if not netmask or not self.is_valid_ipv4(netmask):
                    netmask = "255.255.255.0"

                prefix = self.netmask_to_prefix(netmask)
                if prefix is None:
                    return {"error": "invalid_netmask", "message": _("Invalid subnet mask")}

                profile.ipv4.method = 'manual'
                valid_gateway = gateway if self.is_valid_ipv4(gateway) else None
                self._set_ipv4_address(profile, ip, prefix, valid_gateway)

                if valid_gateway:
                    profile.ipv4.gateway = valid_gateway
                else:
                    profile.ipv4.gateway = None

                if dns:
                    dns_ips = [d.strip() for d in dns.split(",") if self.is_valid_ipv4(d)]
                    profile.ipv4.dns = self._dns_to_u32_list(dns_ips)
                else:
                    profile.ipv4.dns = []

            settings.update_profile(profile, save_to_disk=True)

            # Activate the connection
            self.nm.activate_connection(conn_path)

            return {"status": "success"}

        except Exception as e:
            logging.exception("Failed to set wireless DHCP")
            return {"error": "dbus_error", "message": str(e)}

    def set_wireless_manual(self, address, netmask, gateway, dns_list):
        """Set static IP for wireless connection using DBus."""
        if not self.wlan_device or not self.wlan_device.active_connection or self.wlan_device.active_connection == "/":
            return {"error": "no_connection", "message": _("No wireless connection available")}

        prefix = self.netmask_to_prefix(netmask)
        if prefix is None:
            return {"error": "invalid_netmask", "message": _("Invalid subnet mask")}

        try:
            active_connection = ActiveConnection(self.wlan_device.active_connection)
            conn_path = active_connection.connection

            if not conn_path or conn_path == "/":
                return {"error": "no_connection", "message": _("No wireless connection available")}

            settings = NetworkConnectionSettings(conn_path)
            profile = settings.get_profile()

            profile.ipv4.method = 'manual'
            valid_gateway = gateway if self.is_valid_ipv4(gateway) else None
            self._set_ipv4_address(profile, address, prefix, valid_gateway)

            if valid_gateway:
                profile.ipv4.gateway = valid_gateway
            else:
                profile.ipv4.gateway = None

            filtered_dns_list = [dns for dns in dns_list if self.is_valid_ipv4(dns)]
            profile.ipv4.dns = self._dns_to_u32_list(filtered_dns_list)

            settings.update_profile(profile, save_to_disk=True)

            # Activate the connection
            self.nm.activate_connection(conn_path)

            return {"status": "success"}

        except Exception as e:
            logging.exception("Failed to set wireless manual IP")
            return {"error": "dbus_error", "message": str(e)}

    def _get_wired_connection_settings(self, interface):
        """Get the connection settings path for a wired interface using DBus."""
        device_path = self._get_wired_device_path(interface)
        if not device_path:
            return None

        try:
            device = NetworkDeviceWired(device_path)
            if device.active_connection and device.active_connection != "/":
                active_connection = ActiveConnection(device.active_connection)
                if active_connection.connection and active_connection.connection != "/":
                    return active_connection.connection

            # Try to find from available connections
            for conn_path in device.available_connections:
                settings = NetworkConnectionSettings(conn_path)
                profile = settings.get_profile()
                if profile.connection.interface_name == interface:
                    return conn_path

        except Exception as e:
            logging.debug(f"Failed to get wired connection settings: {e}")

        return None

    def _ensure_wired_connection(self, interface):
        """Ensure a wired connection exists for the interface, create if needed."""
        conn_path = self._get_wired_connection_settings(interface)
        if conn_path:
            return conn_path

        # Try to find existing connection
        try:
            nm_settings = NetworkManagerSettings()
            for path in nm_settings.list_connections():
                settings = NetworkConnectionSettings(path)
                profile = settings.get_profile()
                if (profile.connection.connection_type == '802-3-ethernet' and
                    profile.connection.interface_name == interface):
                    return path

            # Create a new connection profile
            device_path = self._get_wired_device_path(interface)
            if device_path:
                device = NetworkDeviceWired(device_path)
                # Add connection via NetworkManager
                conn_path = self.nm.add_and_activate_connection2(
                    {
                        'connection': {
                            'id': ('s', f'wired-{interface}'),
                            'type': ('s', '802-3-ethernet'),
                            'interface-name': ('s', interface),
                            'autoconnect': ('b', True),
                        },
                        'ipv4': {'method': ('s', 'auto')},
                        'ipv6': {'method': ('s', 'auto')},
                    },
                    device_path,
                    "/"
                )
                return conn_path

        except Exception as e:
            logging.exception(f"Failed to ensure wired connection: {e}")

        return None

    def netmask_to_prefix(self, netmask):
        if not netmask:
            return None
        try:
            return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
        except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
            return None

    def prefix_to_netmask(self, prefix):
        try:
            return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
        except Exception:
            return "?"

    def is_valid_ipv4(self, address):
        """Check if the given string is a valid IPv4 address."""
        if not address or address in ["?", "0.0.0.0", ""]:
            return False
        try:
            ipaddress.IPv4Address(address)
            return True
        except Exception:
            return False

    def get_wired_dhcp_state(self, interface):
        """Check if wired connection is using DHCP using DBus."""
        conn_path = self._get_wired_connection_settings(interface)
        if not conn_path:
            return True
        try:
            settings = NetworkConnectionSettings(conn_path)
            profile = settings.get_profile()
            return profile.ipv4.method == 'auto'
        except Exception as e:
            logging.debug(f"Failed to get wired DHCP state: {e}")
            return True

    def get_wired_info(self, interface):
        """Get wired connection network info using DBus."""
        info = {
            "ip_address": "",
            "netmask": "",
            "gateway": "",
            "dns": "",
        }

        device_path = self._get_wired_device_path(interface)
        if not device_path:
            return info

        try:
            device = NetworkDeviceWired(device_path)

            # Get IP info from active connection
            if device.active_connection and device.active_connection != "/":
                active_connection = ActiveConnection(device.active_connection)

                # Get IP configuration
                if active_connection.ip4_config and active_connection.ip4_config != "/":
                    ip4_config = IPv4Config(active_connection.ip4_config)

                    # Get address
                    if ip4_config.address_data:
                        addr_data = ip4_config.address_data[0]
                        info["ip_address"] = addr_data.get("address", ("s", ""))[1]
                        prefix = addr_data.get("prefix", ("u", 0))[1]
                        info["netmask"] = self.prefix_to_netmask(str(prefix))

                    # Get gateway
                    try:
                        gateway = ip4_config.gateway
                        if gateway:
                            info["gateway"] = gateway
                    except Exception:
                        pass

                    # Get DNS
                    try:
                        dns_data = ip4_config.nameserver_data
                        if dns_data:
                            dns_list = [d.get("address", ("s", ""))[1] for d in dns_data]
                            info["dns"] = ", ".join(dns_list)
                    except Exception:
                        pass

            # If no active connection or missing info, try connection settings
            if not info["ip_address"]:
                conn_path = self._get_wired_connection_settings(interface)
                if conn_path:
                    settings = NetworkConnectionSettings(conn_path)
                    profile = settings.get_profile()

                if profile.ipv4.addresses:
                    addr = profile.ipv4.addresses[0] if profile.ipv4.addresses else None
                    address, prefix = self._parse_profile_ipv4_address(addr)
                    if address and prefix:
                        info["ip_address"] = address
                        info["netmask"] = self.prefix_to_netmask(prefix)

                    if profile.ipv4.gateway:
                        info["gateway"] = profile.ipv4.gateway

                    if profile.ipv4.dns:
                        info["dns"] = ", ".join(self._dns_to_text_list(profile.ipv4.dns))

        except Exception as e:
            logging.debug(f"Failed to get wired info: {e}")

        return info

    def set_wired_dhcp(self, interface, enable=True):
        """Enable or disable DHCP for wired connection using DBus."""
        conn_path = self._ensure_wired_connection(interface)
        if not conn_path:
            return {"error": "no_connection", "message": _("No wired connection available")}

        try:
            settings = NetworkConnectionSettings(conn_path)
            profile = settings.get_profile()

            if enable:
                profile.ipv4.method = 'auto'
                profile.ipv4.address_data = []
                profile.ipv4.addresses = None
                profile.ipv4.gateway = None
                profile.ipv4.dns = []
            else:
                info = self.get_wired_info(interface)
                ip = info.get("ip_address", "")
                netmask = info.get("netmask", "")
                gateway = info.get("gateway", "")
                dns = info.get("dns", "")

                if not self.is_valid_ipv4(ip):
                    ip = "0.0.0.0"
                if not netmask or not self.is_valid_ipv4(netmask):
                    netmask = "255.255.255.0"

                prefix = self.netmask_to_prefix(netmask)
                if prefix is None:
                    return {"error": "invalid_netmask", "message": _("Invalid subnet mask")}

                profile.ipv4.method = 'manual'
                valid_gateway = gateway if self.is_valid_ipv4(gateway) else None
                self._set_ipv4_address(profile, ip, prefix, valid_gateway)

                if valid_gateway:
                    profile.ipv4.gateway = valid_gateway
                else:
                    profile.ipv4.gateway = None

                if dns:
                    dns_ips = [d.strip() for d in dns.split(",") if self.is_valid_ipv4(d)]
                    profile.ipv4.dns = self._dns_to_u32_list(dns_ips)
                else:
                    profile.ipv4.dns = []

            settings.update_profile(profile, save_to_disk=True)

            # Try to activate the connection
            try:
                device_path = self._get_wired_device_path(interface)
                if device_path:
                    self.nm.activate_connection(conn_path)
            except Exception as e:
                # Ignore errors if device has no carrier
                if "no carrier" not in str(e).lower():
                    logging.debug(f"Failed to activate connection: {e}")

            return {"status": "success"}

        except Exception as e:
            logging.exception("Failed to set wired DHCP")
            return {"error": "dbus_error", "message": str(e)}

    def set_wired_manual(self, interface, address, netmask, gateway, dns_list):
        """Set static IP for wired connection using DBus."""
        conn_path = self._ensure_wired_connection(interface)
        if not conn_path:
            return {"error": "no_connection", "message": _("No wired connection available")}

        prefix = self.netmask_to_prefix(netmask)
        if prefix is None:
            return {"error": "invalid_netmask", "message": _("Invalid subnet mask")}

        try:
            settings = NetworkConnectionSettings(conn_path)
            profile = settings.get_profile()

            profile.ipv4.method = 'manual'
            valid_gateway = gateway if self.is_valid_ipv4(gateway) else None
            self._set_ipv4_address(profile, address, prefix, valid_gateway)

            if valid_gateway:
                profile.ipv4.gateway = valid_gateway
            else:
                profile.ipv4.gateway = None

            filtered_dns_list = [dns for dns in dns_list if self.is_valid_ipv4(dns)]
            profile.ipv4.dns = self._dns_to_u32_list(filtered_dns_list)

            settings.update_profile(profile, save_to_disk=True)

            # Try to activate the connection
            try:
                device_path = self._get_wired_device_path(interface)
                if device_path:
                    self.nm.activate_connection(conn_path)
            except Exception as e:
                # Ignore errors if device has no carrier
                if "no carrier" not in str(e).lower():
                    logging.debug(f"Failed to activate connection: {e}")

            return {"status": "success"}

        except Exception as e:
            logging.exception("Failed to set wired manual IP")
            return {"error": "dbus_error", "message": str(e)}
        return {"status": "success"}

    @staticmethod
    def get_known_networks():
        known_networks = []
        saved_network_paths = NetworkManagerSettings().list_connections()
        for netpath in saved_network_paths:
            saved_con = NetworkConnectionSettings(netpath)
            con_settings = saved_con.get_settings()
            if con_settings["connection"]["type"][1] == "802-11-wireless":
                known_networks.append(
                    {
                        "SSID": con_settings["802-11-wireless"]["ssid"][1].decode(),
                        "UUID": con_settings["connection"]["uuid"][1],
                    }
                )
        return known_networks

    def is_known(self, ssid):
        return any(net["SSID"] == ssid for net in self.get_known_networks())

    def get_ip_address(self):
        active_connection_path = self.nm.primary_connection
        if not active_connection_path or active_connection_path == "/":
            return "?"
        active_connection = ActiveConnection(active_connection_path)
        ip_info = IPv4Config(active_connection.ip4_config)
        return ip_info.address_data[0]["address"][1]

    def get_networks(self):
        networks = []
        try:
            if self.wlan_device:
                seen_networks = {}
                all_aps = [AccessPoint(result) for result in self.wlan_device.access_points]
                for ap in all_aps:
                    if not ap.ssid:
                        continue

                    ssid = ap.ssid.decode("utf-8")
                    signal_level = ap.strength
                    if ssid in seen_networks:
                        if signal_level > seen_networks[ssid]["signal_level"]:
                            seen_networks[ssid] = {
                                "SSID": ssid,
                                "known": self.is_known(ssid),
                                "security": get_encryption(ap.rsn_flags or ap.wpa_flags or ap.flags),
                                "signal_level": signal_level,
                                "BSSID": ap.hw_address,
                            }
                    else:
                        seen_networks[ssid] = {
                            "SSID": ssid,
                            "known": self.is_known(ssid),
                            "security": get_encryption(ap.rsn_flags or ap.wpa_flags or ap.flags),
                            "signal_level": signal_level,
                            "BSSID": ap.hw_address,
                        }
                networks = list(seen_networks.values())
                return sorted(networks, key=lambda i: i["signal_level"], reverse=True)
            return networks
        except Exception as e:
            return networks

    def get_bssid_from_ssid(self, ssid):
        return next(net["BSSID"] for net in self.get_networks() if ssid == net["SSID"])

    def get_is_connected(self):
        state = self.wlan_device.state
        if state in [
            enums.DeviceState.ACTIVATED,
        ]:
            return True
        else:
            return False

    def get_connected_ap(self):
        if self.wlan_device.active_access_point == "/":
            return None
        return AccessPoint(self.wlan_device.active_access_point)

    def get_connected_bssid(self):
        return (
            self.get_connected_ap().hw_address
            if self.get_connected_ap() is not None
            else None
        )

    def get_signal_strength(self):
        ap = self.get_connected_ap()
        return ap.strength if ap else None

    def get_security_type(self, ssid):
        return next(
            (
                network["security"]
                for network in self.get_networks()
                if network["SSID"] == ssid
            ),
            None,
        )

    def add_network(self, ssid, psk, eap_method, identity="", phase2=None):
        security_type = self.get_security_type(ssid)
        logging.debug(f"Adding network of type: {security_type}")
        if security_type is None:
            return {"error": "network_not_found", "message": _("Network not found")}

        if self.is_known(ssid):
            self.delete_network(ssid)

        properties: NetworkManagerConnectionProperties = {
            "connection": {
                "id": ("s", ssid),
                "uuid": ("s", str(uuid4())),
                "type": ("s", "802-11-wireless"),
                "interface-name": ("s", self.wlan_device.interface),
            },
            "802-11-wireless": {
                "mode": ("s", "infrastructure"),
                "ssid": ("ay", ssid.encode("utf-8")),
                "security": ("s", "802-11-wireless-security"),
            },
            "ipv4": {"method": ("s", "auto")},
            "ipv6": {"method": ("s", "auto")},
        }

        if security_type == "Open":
            properties["802-11-wireless"]["security"] = ("s", "none")
        elif "WPA-PSK" in security_type:
            properties["802-11-wireless-security"] = {
                "key-mgmt": ("s", "wpa-psk"),
                "psk": ("s", psk),
            }
        elif "SAE" in security_type:
            properties["802-11-wireless-security"] = {
                "key-mgmt": ("s", "sae"),
                "psk": ("s", psk),
            }
        elif "WPA3-B192" in security_type:
            properties["802-11-wireless-security"] = {
                "key-mgmt": ("s", "wpa-eap-suite-b-192"),
                "psk": ("s", psk),
            }
        elif "OWE" in security_type:
            properties["802-11-wireless-security"] = {
                "key-mgmt": ("s", "owe"),
            }
        elif "802.1x" in security_type:
            properties["802-11-wireless-security"] = {
                "key-mgmt": ("s", "wpa-eap"),
                "eap": ("as", [eap_method]),
                "identity": ("s", identity),
                "password": ("s", psk),
            }
            if phase2:
                properties["802-11-wireless-security"]["phase2_auth"] = ("s", phase2)
        elif "WEP" in security_type:
            properties["802-11-wireless-security"] = {
                "key-mgmt": ("s", "none"),
                "wep-key-type": ("u", 2),
                "wep-key0": ("s", psk),
                "auth-alg": ("s", "shared"),
            }
        else:
            return {
                "error": "unknown_security_type",
                "message": _("Unknown security type"),
            }

        try:
            NetworkManagerSettings().add_connection(properties)
            return {"status": "success"}
        except exceptions.NmSettingsPermissionDeniedError:
            logging.exception("Insufficient privileges")
            return {
                "error": "insufficient_privileges",
                "message": _("Insufficient privileges"),
            }
        except exceptions.NmConnectionInvalidPropertyError:
            logging.exception("Invalid property")
            return {"error": "psk_invalid", "message": _("Invalid password")}
        except Exception as e:
            logging.exception("Couldn't add network")
            return {"error": "unknown", "message": _("Couldn't add network") + f"\n{e}"}

    def disconnect_network(self):
        self.wlan_device.disconnect()

    def delete_network(self, ssid):
        if path := self.get_connection_path_by_ssid(ssid):
            self.delete_connection_path(path)
        else:
            logging.debug(f"SSID '{ssid}' not found among saved connections")

    def delete_connection_path(self, path):
        try:
            NetworkConnectionSettings(path).delete()
            logging.info(f"Deleted connection path: {path}")
        except Exception as e:
            logging.exception(f"Failed to delete connection path: {path} - {e}")
            return {
                "error": "deletion_failed",
                "message": _("Failed to delete connection") + f"\n{e}",
            }

    def rescan(self):
        try:
            return self.wlan_device.request_scan({})
        except Exception as e:
            self.popup(f"Unexpected error: {e}")

    def get_connection_path_by_ssid(self, ssid):
        existing_networks = NetworkManagerSettings().list_connections()
        for connection_path in existing_networks:
            connection_settings = NetworkConnectionSettings(
                connection_path
            ).get_settings()
            if (
                connection_settings.get("802-11-wireless")
                and connection_settings["802-11-wireless"].get("ssid")
                and connection_settings["802-11-wireless"]["ssid"][1].decode() == ssid
            ):
                return connection_path
        return None

    def connect(self, ssid):
        if target_connection := self.get_connection_path_by_ssid(ssid):
            try:
                active_connection = self.nm.activate_connection(target_connection)
                return target_connection
            except Exception as e:
                logging.exception("Unexpected error")
                self.popup(f"Unexpected error: {e}")
        else:
            self.popup(f"SSID '{ssid}' not found among saved connections")

    def toggle_wifi(self, enable):
        self.nm.wireless_enabled = enable

    def monitor_connection_status(self):
        state = self.wlan_device.state
        if self.wifi_state != state:
            logging.debug(f"State changed: {state} {self.wlan_device.state_reason}")
            if self.wifi_state == -1:
                logging.debug("Starting to monitor state")
            elif state in [
                enums.DeviceState.PREPARE,
                enums.DeviceState.CONFIG,
            ]:
                self.popup(_("Connecting"), 1)
            elif state in [
                enums.DeviceState.IP_CONFIG,
                enums.DeviceState.IP_CHECK,
                enums.DeviceState.SECONDARIES,
            ]:
                self.popup(_("Getting IP address"), 1)
            elif state in [
                enums.DeviceState.ACTIVATED,
            ]:
                self.popup(_("Network connected"), 1)
            elif state in [
                enums.DeviceState.DISCONNECTED,
                enums.DeviceState.DEACTIVATING,
            ]:
                self.popup(_("Network disconnected"))
            elif state == enums.DeviceState.FAILED:
                self.popup(_("Connection failed"))
            self.wifi_state = state
        return self.monitor_connection

    def enable_monitoring(self, enable):
        self.monitor_connection = enable

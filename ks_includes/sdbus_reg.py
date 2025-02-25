from asyncio import new_event_loop, run_coroutine_threadsafe
from threading import Thread
import ast
import logging
from typing import Optional
from sdbus import DbusInterfaceCommonAsync, dbus_method_async, dbus_property_async

logger = logging.getLogger(__name__)


class RegistrationInterface(DbusInterfaceCommonAsync, interface_name="org.registration.interface"):

    def __init__(self, bus_name: str, object_path: str):
        super().__init__()
        self.proxy = self.new_proxy(bus_name, object_path)

    @dbus_property_async(property_signature="s")
    def get_unique_id(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature="a{sv}")
    def get_time_info(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature="b")
    def is_active(self) -> bool:
        raise NotImplementedError

    @dbus_property_async(property_signature="b")
    def is_trial_active(self) -> bool:
        raise NotImplementedError

    @dbus_method_async(input_signature="s", result_signature="b")
    async def verify_activation_code(self, val: str) -> bool:
        raise NotImplementedError

    @dbus_method_async(input_signature="s", result_signature="b")
    async def reset_registration(self, val: str) -> bool:
        raise NotImplementedError

    @dbus_property_async(property_signature="b")
    def enabled_registration(self) -> bool:
        raise NotImplementedError


class LicenseManager:

    def __init__(self, bus_name: str = "org.registration.link", object_path: str = "/"):
        self.loop = new_event_loop()
        self.registration_interface: Optional[RegistrationInterface] = None
        self.interface_valid = False
        self._thread: Optional[Thread] = None
        self.callback = None

        try:
            self.registration_interface = RegistrationInterface(bus_name, object_path)
            self.interface_valid = True
            logger.info("DBus connection established successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DBus connection: {e}")
            self._cleanup_resources()
            return

        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def _cleanup_resources(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self.loop.close()

    def is_interface_valid(self) -> bool:
        return self.interface_valid

    def _async_call(self, coroutine_func, default=None):
        if not self.is_interface_valid():
            logger.warning("Attempting to use invalid DBus interface")
            return default

        try:
            future = run_coroutine_threadsafe(coroutine_func(), self.loop)
            return future.result()
        except Exception as e:
            logger.error(f"DBus operation failed: {e}")
            self.interface_valid = False
            return default

    def get_unique_id(self) -> str:
        async def _get():
            return await self.registration_interface.proxy.get_unique_id

        return self._async_call(_get, default="")

    def get_trial_time(self) -> int:
        async def _get():
            return await self.registration_interface.proxy.get_time_info

        result = self._async_call(_get, default="{}")
        try:
            data_dict = ast.literal_eval(result)
            return data_dict.get("trial_time", 0)
        except Exception as e:
            logger.error(f"Parse time info failed: {e}")
            return 0

    def get_total_printed_time(self) -> int:
        async def _get():
            return await self.registration_interface.proxy.get_time_info

        result = self._async_call(_get, default="{}")
        try:
            data_dict = ast.literal_eval(result)
            return int(data_dict.get("total_printed_time", 0))
        except Exception as e:
            logger.error(f"Parse time info failed: {e}")
            return 0

    def is_active(self) -> bool:
        async def _get():
            return await self.registration_interface.proxy.is_active

        return self._async_call(_get, default=False)

    def is_trial_active(self) -> bool:
        async def _get():
            return await self.registration_interface.proxy.is_trial_active

        return self._async_call(_get, default=False)

    def is_time_sufficient(self, required_seconds: int = 40 * 3600) -> bool:
        trial_time = self.get_trial_time()
        printed_time = self.get_total_printed_time()
        return (trial_time - printed_time) > required_seconds

    def verify_activation_code(self, code: str) -> bool:
        async def _verify():
            return await self.registration_interface.proxy.verify_activation_code(code)

        return self._async_call(_verify, default=False)

    def reset_registration(self, code: str) -> bool:
        async def _reset():
            return await self.registration_interface.proxy.reset_registration(code)

        return self._async_call(_reset, default=False)

    def enabled_registration(self) -> bool:
        async def _get():
            return await self.registration_interface.proxy.enabled_registration

        return self._async_call(_get, default=False)

    def close(self) -> None:
        if self.is_interface_valid():
            logger.info("Closing DBus connection...")
            self._cleanup_resources()
            self.interface_valid = False

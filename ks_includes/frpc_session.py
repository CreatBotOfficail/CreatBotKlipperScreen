# frpc_session.py - frpc remote assist session management.
#
# Manages frpc without any systemd unit or shell script: render config ->
# spawn frpc detached from the caller (setsid, so a caller crash does not
# kill the session) -> watchdog thread (relaunches frpc on crash, reusing
# the existing config; exits once the stop flag is written).
#
# Pure standard library, no GTK: usable from any panel or CLI tool.
# API: start() / stop() / status(); failures raise SessionError.
import logging
import os
import random
import re
import shutil
import signal
import string
import subprocess
import threading
import time

FRPC_BIN = "frpc"
KEYS_FILE = "/etc/frp/keys.conf"

# ---- Site-specific parameter (not secret) ----
SERVER_PORT = 7000                         # frps bindPort

# Secrets (auth_token / dev_key) are NOT stored in this repo. They live in
# /etc/frp/keys.conf on the printer (chmod 600, deployed via a private
# channel / buildroot overlay), keeping them out of any public repository.
# Device owners can always extract them from the device itself - the point
# is only to keep them out of source control.
#
# keys.conf format (one key per line, values may be quoted):
#   server_addr = frps.creatbot.com
#   auth_token = xxxxx
#   dev_key = xxxxx

RESTART_SEC = 5        # watchdog delay before relaunching a crashed frpc
START_CONFIRM = 1.5    # how long to confirm the spawned frpc stays alive
STOP_TERM_WAIT = 2     # seconds to wait after SIGTERM before SIGKILL

# frpc config template. The xtcp leg's secretKey MUST be generated on the
# printer and embedded as the real value: the hole-punching sid probe
# packets are encrypted with each side's own secretKey and frps never sends
# back the rewritten key. This sk is reported via metadatas for the backend
# to record, and the ops client redeems the same value. The stcp legs keep
# the PLACEHOLDER marker: the real key is generated server-side in the
# NewProxy plugin callback and never stored on the printer.
FRPC_TEMPLATE = """serverAddr = "{server_addr}"
serverPort = {server_port}
auth.method = "token"
auth.token = "{auth_token}"

metadatas = {{ code = "{code}", dev_key = "{dev_key}", xtcp_sk = "{xtcp_sk}" }}

# ---- xtcp (P2P direct, preferred) ----

[[proxies]]
name = "assist-ssh-xtcp-{session}"
type = "xtcp"
secretKey = "{xtcp_sk}"
localIP = "127.0.0.1"
localPort = 22                       # printer SSH
transport.useEncryption = true
transport.useCompression = true

[[proxies]]
name = "assist-web-xtcp-{session}"
type = "xtcp"
secretKey = "{xtcp_sk}"
localIP = "127.0.0.1"
localPort = 80                       # printer web UI
transport.useEncryption = true
transport.useCompression = true

[[proxies]]
name = "assist-moonraker-xtcp-{session}"
type = "xtcp"
secretKey = "{xtcp_sk}"
localIP = "127.0.0.1"
localPort = 7125                     # Moonraker API (optional, diagnostics)
transport.useEncryption = true
transport.useCompression = true

# ---- stcp (relayed via frps, fallback) ----

[[proxies]]
name = "assist-ssh-{session}"
type = "stcp"
secretKey = "PLACEHOLDER"
localIP = "127.0.0.1"
localPort = 22                       # printer SSH
transport.useEncryption = true
transport.useCompression = true

[[proxies]]
name = "assist-web-{session}"
type = "stcp"
secretKey = "PLACEHOLDER"
localIP = "127.0.0.1"
localPort = 80                       # printer web UI
transport.useEncryption = true
transport.useCompression = true

[[proxies]]
name = "assist-moonraker-{session}"
type = "stcp"
secretKey = "PLACEHOLDER"
localIP = "127.0.0.1"
localPort = 7125                     # Moonraker API (optional, diagnostics)
transport.useEncryption = true
transport.useCompression = true
"""


class SessionError(Exception):
    """Session operation failure (start failed / stop failed)."""


def _load_keys():
    """Read server_addr / auth_token / dev_key from keys.conf.
    Returns a dict; raises SessionError if missing or incomplete."""
    required = ("server_addr", "auth_token", "dev_key")
    keys = {}
    try:
        with open(KEYS_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(("#", ";")):
                    continue
                k, _, v = line.partition("=")
                if _:
                    keys[k.strip()] = v.strip().strip("\"'")
    except OSError:
        pass
    missing = [k for k in required if not keys.get(k)]
    if missing:
        raise SessionError(
            "missing_keys: %s (see %s)" % (",".join(missing), KEYS_FILE))
    return keys


def _rand(chars, n):
    return "".join(random.SystemRandom().choice(chars) for _ in range(n))


class AssistSession:
    """Lifecycle management for a single assist session.

    Concurrency: start/stop/status are called serially by the panel (its
    busy flag guards re-entry); _lock only makes these entry points
    mutually exclusive. The watchdog thread does NOT take the lock - it is
    synchronized with stop via the stop flag file and join ordering: stop
    writes the flag first, joins the watchdog, then kills the process and
    removes files. The stop flag itself stays on disk and is cleared by the
    next _launch.
    """

    def __init__(self, run_dir="/tmp/frpc"):
        self.run_dir = run_dir
        self.conf_file = os.path.join(self.run_dir, "frpc-current.toml")
        self.pid_file = os.path.join(self.run_dir, "frpc.pid")
        self.code_file = os.path.join(self.run_dir, "code")
        self.stop_flag = os.path.join(self.run_dir, "stop")
        self._lock = threading.Lock()
        self._watchdog = None

    # ------------------------------------------------------------ process

    def _pid(self):
        """Return the frpc pid, or None. The pid file is only trusted when
        the process is alive and its cmdline references the session config
        (guards against pid reuse)."""
        try:
            with open(self.pid_file) as f:
                pid = int(f.read().strip())
        except (OSError, ValueError):
            return None
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as f:
                cmdline = f.read()
        except OSError:
            return None
        if b"frpc-current.toml" not in cmdline.replace(b"\0", b" "):
            return None
        return pid

    def _spawn(self):
        proc = subprocess.Popen(
            [FRPC_BIN, "-c", self.conf_file],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True)
        threading.Thread(
            target=self._pump_output, args=(proc,), daemon=True,
            name="frpc-logpump").start()
        with open(self.pid_file, "w") as f:
            f.write(str(proc.pid))

    def _pump_output(self, proc):
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    logging.info("[frpc] %s", line)
        except Exception as e:
            logging.warning("frpc log pump stopped: %s", e)
        finally:
            proc.stdout.close()

    def _kill_stale(self):
        """Kill any leftover frpc still running with a session config.

        Covers processes the pid file lost track of: an old run_dir path
        (e.g. after an upgrade moved the state dir), a /tmp cleanup after
        reboot with frpc still alive, or a pid file deleted while frpc
        kept running. Matched by cmdline so unrelated frpc usage elsewhere
        on the printer is never touched.
        """
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open("/proc/%s/cmdline" % entry, "rb") as f:
                    cmdline = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
            except OSError:
                continue
            if "frpc" not in cmdline or "frpc-current.toml" not in cmdline:
                continue
            try:
                os.kill(int(entry), signal.SIGTERM)
                logging.warning("killed stale frpc pid %s", entry)
            except (OSError, ValueError):
                pass
        time.sleep(1)

    def _launch(self, code, keys):
        """Render a fresh config and start frpc (new session entry point;
        also clears the stop flag left by the previous stop)."""
        os.makedirs(self.run_dir, exist_ok=True)
        os.chmod(self.run_dir, 0o700)
        try:
            os.remove(self.stop_flag)
        except OSError:
            pass
        self._kill_stale()
        conf = FRPC_TEMPLATE.format(
            server_addr=keys["server_addr"], server_port=SERVER_PORT,
            auth_token=keys["auth_token"], code=code, dev_key=keys["dev_key"],
            xtcp_sk=_rand(string.ascii_letters + string.digits, 32),
            session="S" + _rand(string.ascii_letters + string.digits, 8),
        )
        fd = os.open(self.conf_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(conf)
        self._spawn()

    def _terminate(self):
        """Stop frpc and wait for it to exit. Returns True if stopped."""
        pid = self._pid()
        if pid is None:
            return True
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        deadline = time.time() + STOP_TERM_WAIT
        while self._pid() is not None and time.time() < deadline:
            time.sleep(0.2)
        if self._pid() is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            time.sleep(0.5)
        if self._pid() is None:
            # pid file is gone but the process may have been reparented
            # without exiting (race); sweep by cmdline as a last resort
            self._kill_stale()
        return self._pid() is None

    # ----------------------------------------------------------- watchdog

    def _watchdog_loop(self):
        while True:
            time.sleep(1)
            if os.path.exists(self.stop_flag):
                return
            if self._pid() is not None:
                continue
            time.sleep(RESTART_SEC)
            # Crash restart reuses the existing config (assist code and
            # xtcp_sk stay the same). Missing files mean the session is
            # gone - exit instead of relaunching a broken session.
            if os.path.exists(self.stop_flag) or not os.path.exists(self.conf_file):
                return
            if self._pid() is None:
                try:
                    self._spawn()
                except OSError as e:
                    logging.error("frpc relaunch failed: %s", e)
                    return

    def _start_watchdog(self):
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="frpc-watchdog")
        self._watchdog.start()

    # --------------------------------------------------------- public API

    def start(self):
        """Start (or resume) an assist session. Returns a dict with
        assist_code; raises SessionError on failure. If the previous session
        ended abnormally (crash/power loss, no cleanup ran), the same code
        is reused for a new session so the ops client can redeem it again;
        a fresh code is only issued after a normal stop."""
        with self._lock:
            pid = self._pid()
            code = self._read_code()
            if pid is not None:
                if code and os.path.exists(self.conf_file):
                    return {"assist_code": code, "reused": True}
                # frpc alive but session files missing = broken session,
                # tear it down and start over
                self._stop_locked()
            if shutil.which(FRPC_BIN) is None:
                raise SessionError("missing_frpc")
            keys = _load_keys()
            code = code or _rand(string.digits, 6)
            try:
                self._launch(code, keys)
            except OSError as e:
                raise SessionError("start_frpc_failed: %s" % e)
            deadline = time.time() + START_CONFIRM
            while time.time() < deadline:
                if self._pid() is None:
                    raise SessionError("start_frpc_failed: see KlipperScreen.log")
                time.sleep(0.2)
            self._write_code(code)
            self._start_watchdog()
            return {"assist_code": code, "reused": False}

    def stop(self):
        """End the session: stop frpc (CloseProxy unregisters the backend
        mapping via the frp plugin) and clean up."""
        with self._lock:
            return self._stop_locked()

    def _stop_locked(self):
        with open(self.stop_flag, "w") as f:
            f.write("1")
        # Join the watchdog before killing the process: it may be inside the
        # RESTART_SEC wait; past the join timeout it still exits on its next
        # loop iteration when it sees the flag, so frpc cannot be revived.
        wd = self._watchdog
        if wd is not None and wd.is_alive():
            wd.join(timeout=RESTART_SEC + 2)
        if not self._terminate():
            raise SessionError("stop_frpc_failed")
        # A normal stop removes the code file too, so the next start issues
        # a fresh code. A leftover code file (abnormal end: crash/power loss,
        # this cleanup never ran) is exactly what triggers code reuse.
        for path in (self.conf_file, self.pid_file, self.code_file):
            try:
                os.remove(path)
            except OSError:
                pass
        return {"stopped": True}

    def status(self):
        with self._lock:
            running = self._pid() is not None
            code = self._read_code() if running else None
            if running and not (code and os.path.exists(self.conf_file)):
                # frpc alive but session files missing = broken session,
                # tear it down and report idle
                try:
                    self._stop_locked()
                except SessionError:
                    pass
                running = False
        return {"running": running, "assist_code": code}

    # ----------------------------------------------------------------- IO

    def _read_code(self):
        try:
            with open(self.code_file) as f:
                m = re.match(r"(\d{6})", f.read().strip())
            return m.group(1) if m else None
        except OSError:
            return None

    def _write_code(self, code):
        with open(self.code_file, "w") as f:
            f.write(code)

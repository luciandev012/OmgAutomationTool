"""Instance discovery and cancellable launch; no GUI or account handling."""
from __future__ import annotations
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_mumu_start_lock = threading.Lock()


class EmulatorError(RuntimeError):
    pass


class LaunchCancelled(InterruptedError):
    pass


@dataclass(frozen=True)
class Instance:
    index: str
    name: str
    running: bool = False
    serial: str = ""


@dataclass(frozen=True)
class Emulator:
    kind: str
    console: Path
    adb: Path

    @property
    def label(self):
        return "MuMu" if self.kind == "mumu" else "LDPlayer"

    def command(self, *args, timeout=20):
        try:
            result = subprocess.run([str(self.console), *map(str, args)],
                cwd=str(self.console.parent), capture_output=True, timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EmulatorError(f"{self.label}: {exc}") from exc
        output = result.stdout.decode("utf-8-sig", "replace").strip()
        if result.returncode:
            raise EmulatorError(f"{self.label}: {result.stderr.decode('utf-8', 'replace').strip() or output}")
        if self.kind == "mumu" and output.startswith("{"):
            try:
                error = json.loads(output)
            except ValueError:
                error = {}
            if error.get("errcode", 0):
                raise EmulatorError(f"{self.label}: {error.get('errmsg', output)}")
        return output

    def instances(self):
        if self.kind == "mumu":
            raw = self.command("info", "-v", "all")
            try:
                data = json.loads(raw)
                entries = [data] if isinstance(data, dict) and "index" in data else (data.values() if isinstance(data, dict) else data)
                return [Instance(str(v["index"]), v.get("name", str(v["index"])),
                    bool(v.get("is_process_started")),
                    f"127.0.0.1:{v['adb_port']}" if v.get("adb_port") else "") for v in entries]
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                raise EmulatorError("Không đọc được danh sách instance MuMu.") from exc
        instances = []
        for line in self.command("list2").splitlines():
            fields = line.split(",")
            if len(fields) >= 7 and fields[0].isdigit():
                instances.append(Instance(fields[0], fields[1], fields[4] != "0" or fields[5].lstrip("-").isdigit() and int(fields[5]) > 0))
        return instances

    def launch(self, index):
        if self.kind == "mumu":
            self.ensure_main_ready()
            self.command("control", "-v", index, "launch", timeout=30)
        else:
            self.command("launch", "--index", index, timeout=30)

    def ensure_main_ready(self, timeout=30):
        if self.kind != 'mumu':
            return
        def ready():
            try:
                data = json.loads(self.command('info', '-v', 'all', timeout=8))
                entries = [data] if isinstance(data, dict) and 'index' in data else list(data.values())
                return bool(entries) and all(v.get('info_source') == 'rpc' for v in entries)
            except (EmulatorError, ValueError, TypeError, AttributeError):
                return False
        # Two launch workers must not bootstrap the main application twice.
        with _mumu_start_lock:
            if ready():
                return
            self.command('main', 'launch', timeout=15)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if ready():
                    return
                time.sleep(.5)
            raise EmulatorError('MuMu chính chưa tạo được kết nối điều khiển (RPC). '
                'Lệnh mở MuMu đã gửi nhưng ứng dụng chưa sẵn sàng hoặc đã thoát. '
                'Hãy mở MuMu chính từ Windows và kiểm tra nhật ký khởi động.')

    def shutdown(self, index):
        if self.kind == 'mumu':
            self.command('control', '-v', index, 'shutdown', timeout=30)
        else:
            self.command('quit', '--index', index, timeout=30)

    def serial(self, index):
        if self.kind == "mumu":
            matches = [i for i in self.instances() if i.index == index]
            return matches[0].serial if matches else ""
        query = "-H 127.0.0.1"
        server_port = os.environ.get("OMG_ADB_SERVER_PORT", "")
        if server_port.isdigit():
            query += f" -P {server_port}"
        output = self.command("adb", "--index", index, "--command", query + " get-serialno", timeout=8)
        matches = re.findall(r"(?m)^(emulator-\d+|127\.0\.0\.1:\d+)\s*$", output)
        return matches[-1] if matches else ""


def detect_emulators(mumu_manager, ld_manager):
    """Discover installed providers; do not launch a VM during detection."""
    providers = []
    hint = os.environ.get("OMG_MUMU_MANAGER", "").strip().strip('"')
    manager = Path(hint) if hint else Path(mumu_manager)
    if manager.is_file() and (manager.parent / "adb.exe").is_file():
        providers.append(Emulator("mumu", manager, manager.parent / "adb.exe"))
    if ld_manager:
        root = Path(ld_manager).parent
        roots = [root, root.parent, *(root.parent / v for v in ("LDPlayer9", "LDPlayer14", "LDPlayer64", "LDPlayer4"))]
        for base in roots:
            console = next((base / n for n in ("ldconsole.exe", "dnconsole.exe") if (base / n).is_file()), None)
            if console and (base / "adb.exe").is_file():
                providers.append(Emulator("ld", console, base / "adb.exe"))
                break
    return providers


class LaunchControl:
    def __init__(self):
        self.cancelled = threading.Event()
        self.paused = threading.Event()
        self.pause_seconds = 0.0

    def checkpoint(self):
        if self.paused.is_set():
            started = time.monotonic()
            try:
                while self.paused.is_set():
                    if self.cancelled.wait(.1):
                        raise LaunchCancelled("Đã dừng tác vụ; instance đã bật được giữ nguyên.")
            finally:
                self.pause_seconds += time.monotonic() - started
        if self.cancelled.is_set():
            raise LaunchCancelled("Đã dừng tác vụ; instance đã bật được giữ nguyên.")

    def clock(self):
        return time.monotonic() - self.pause_seconds

    def sleep(self, seconds):
        deadline = self.clock() + max(0, seconds)
        while True:
            self.checkpoint()
            remaining = deadline - self.clock()
            if remaining <= 0:
                return
            self.cancelled.wait(min(.1, remaining))


def open_instance(provider, instance, package, run_adb, launch_game, control, progress, timeout=180, on_device=None):
    """Bind to the selected instance only; never choose the first adb device."""
    if not re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+", package):
        raise EmulatorError("Tên gói game chưa hợp lệ.")
    control.checkpoint()
    progress(f"Đang khởi động {provider.label} · {instance.name}…")
    if not instance.running:
        provider.launch(instance.index)
    deadline = time.monotonic() - control.pause_seconds + timeout
    last_error = "Chưa tìm thấy thiết bị ADB của instance."
    while time.monotonic() - control.pause_seconds < deadline:
        control.checkpoint()
        try:
            # LD's console also needs the shared server before get-serialno.
            run_adb(str(provider.adb), "start-server", timeout=8)
            serial = provider.serial(instance.index)
            if serial:
                adb = str(provider.adb)
                if on_device:
                    on_device(adb, serial)
                if ":" in serial:
                    run_adb(adb, "connect", serial, timeout=8)
                control.checkpoint()
                boot = run_adb(adb, "-s", serial, "shell", "getprop", "sys.boot_completed", timeout=8)
                if boot.strip() == b"1":
                    control.checkpoint()
                    progress(f"Đang mở OMG 3Q · {instance.name}…")
                    launch_game(adb, serial, package)
                    # Confirm the activity actually became foreground.
                    for _ in range(15):
                        control.checkpoint()
                        focus = run_adb(adb, "-s", serial, "shell", "dumpsys", "activity", "activities", timeout=8)
                        lines = focus.decode("utf-8", "replace").splitlines()
                        if any(package + "/" in line and ("ResumedActivity" in line or "topResumedActivity" in line) for line in lines):
                            return adb, serial
                        control.cancelled.wait(1)
                    raise EmulatorError("Đã gửi lệnh mở game nhưng chưa xác nhận OMG 3Q ở phía trước.")
        except LaunchCancelled:
            raise
        except Exception as exc:
            last_error = str(exc)
        control.cancelled.wait(2)
    raise EmulatorError(f"Hết thời gian chờ {instance.name}. {last_error}")


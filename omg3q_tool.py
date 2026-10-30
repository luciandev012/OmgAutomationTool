"""MuMu Player 12 automation for OMG 3Q. Run with the project's virtual environment."""

from __future__ import annotations

import os
import queue
import re
import shlex
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from login_engine import AdbDevice, PACKAGE
from account_excel import AccountWorkbook
from excel_scripts import ExcelCycle, ScriptBatch, shutdown_session
from dungeon_engine import DungeonDetector, DungeonEngine
from equipment_skill import EquipmentDetector, TeamEquipmentSkill
from emulator_instances import detect_emulators
from instance_dialog import InstanceDialog
from task_sessions import SessionRegistry, active_session, guard_command


TITLE = "OMG 3Q · Công cụ tự động hóa"
DEFAULT_ADB = Path(r"C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe")
DEFAULT_MANAGER = Path(r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe")


class AdbError(RuntimeError):
    pass


def find_ldmultiplayer() -> Path | None:
    """Find the instance manager, not dnplayer.exe or the console launcher."""
    hint = os.environ.get("OMG_LDMULTIPLAYER", "").strip().strip('"')
    if hint and Path(hint).is_file():
        return Path(hint)
    roots = [Path(r"C:\LDPlayer"), Path(r"C:\leidian")]
    for key, default in (("ProgramFiles", r"C:\Program Files"),
                         ("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        roots.append(Path(os.environ.get(key, default)) / "LDPlayer")
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                try:
                    with winreg.OpenKey(hive, key) as parent:
                        for index in range(winreg.QueryInfoKey(parent)[0]):
                            try:
                                with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as child:
                                    label = str(winreg.QueryValueEx(child, "DisplayName")[0])
                                    if "ldplayer" not in label.lower():
                                        continue
                                    for value in ("InstallLocation", "DisplayIcon"):
                                        try:
                                            raw = str(winreg.QueryValueEx(child, value)[0]).strip()
                                            if not raw:
                                                continue
                                            path = Path(raw.rsplit(",", 1)[0].strip('"'))
                                            root = path.parent if value == "DisplayIcon" else path
                                            roots.extend((root, root.parent))
                                        except OSError:
                                            pass
                            except OSError:
                                continue
                except OSError:
                    continue
    except ImportError:
        pass
    relative_paths = ("ldmutiplayer/dnmultiplayerex.exe", "dnmultiplayerex.exe", "dnmultiplayer.exe")
    for root in dict.fromkeys(roots):
        for base in (root, *(root / folder for folder in ("LDPlayer14", "LDPlayer9", "LDPlayer64", "LDPlayer4"))):
            for relative in relative_paths:
                candidate = base / relative
                if candidate.is_file():
                    return candidate
    found = shutil.which("dnmultiplayerex.exe") or shutil.which("dnmultiplayer.exe")
    return Path(found) if found else None


def find_adb() -> str:
    if DEFAULT_ADB.is_file():
        return str(DEFAULT_ADB)
    found = shutil.which("adb")
    if found:
        return found
    raise AdbError("Không tìm thấy adb.exe của MuMu. Hãy kiểm tra đường dẫn cài MuMu Player 12.")


_adb_start_lock = threading.Lock()


def run_adb(adb: str, *args: str, timeout: int = 25, data: bytes | None = None) -> bytes:
    guard_command(adb, args)
    try:
        server_port = os.environ.get("OMG_ADB_SERVER_PORT")
        prefix = [adb, "-H", "127.0.0.1"]
        if server_port and server_port.isdigit():
            prefix += ["-P", server_port]
        result = subprocess.run(
            [*prefix, *args],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode and b"cannot connect to daemon at tcp:127.0.0.1:" in result.stderr:
            # -H disables automatic daemon startup, even for loopback. Start
            # locally without -H, then keep explicit IPv4 for device commands.
            with _adb_start_lock:
                guard_command(adb, args)
                probe = subprocess.run(
                    [*prefix, "start-server"], capture_output=True, timeout=timeout,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if probe.returncode:
                    port = server_port if server_port and server_port.isdigit() else "5037"
                    started = subprocess.run(
                        [adb, "-L", f"tcp:{port}", "start-server"],
                        capture_output=True, timeout=timeout,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if started.returncode:
                        detail = started.stderr.decode("utf-8", "replace").strip()
                        raise AdbError(f"Không khởi động được máy chủ ADB (cổng {port}): {detail}")
            guard_command(adb, args)
            result = subprocess.run(
                [*prefix, *args], input=data, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=timeout, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdbError(f"ADB không phản hồi: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise AdbError(detail or f"ADB trả về mã lỗi {result.returncode}.")
    return result.stdout


def connect(adb: str, serial: str) -> tuple[int, int]:
    if not re.fullmatch(r"(?:(?:127\.0\.0\.1|localhost):\d{2,5}|emulator-\d+)", serial):
        raise AdbError("Địa chỉ ADB phải có dạng 127.0.0.1:16384.")
    if ":" in serial:
        reply = run_adb(adb, "connect", serial, timeout=15).decode("utf-8", "replace")
        if "connected" not in reply and "already" not in reply:
            raise AdbError(f"Không kết nối được giả lập: {reply.strip()}")
    state = run_adb(adb, "-s", serial, "get-state").decode("utf-8", "replace").strip()
    if state != "device":
        raise AdbError(f"Thiết bị chưa sẵn sàng: {state}")
    size = run_adb(adb, "-s", serial, "shell", "wm", "size").decode("utf-8", "replace")
    match = re.search(r"(\d+)x(\d+)", size)
    if not match:
        raise AdbError(f"Không đọc được độ phân giải thiết bị: {size.strip()}")
    return int(match.group(1)), int(match.group(2))


def input_text(adb: str, serial: str, value: str) -> None:
    """Send text via stdin so credentials never appear in Windows process arguments."""
    if not value or any(ord(ch) < 32 or ord(ch) > 126 for ch in value):
        raise AdbError("ADB chỉ nhập ổn định ký tự ASCII 32–126; kiểm tra tài khoản/mật khẩu.")
    if "%s" in value:
        raise AdbError("Chuỗi '%s' chưa được hỗ trợ bởi lệnh nhập văn bản của Android.")
    encoded = value.replace(" ", "%s")
    command = f"input text {shlex.quote(encoded)}\nexit\n".encode("ascii")
    try:
        run_adb(adb, "-s", serial, "shell", timeout=25, data=command)
    except AdbError:
        raise AdbError("Không nhập được nội dung vào game. Đã dừng để bảo vệ thông tin đăng nhập.") from None


def launch_game(adb: str, serial: str, package: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+", package):
        raise AdbError("Tên gói ứng dụng không hợp lệ.")
    reply = run_adb(adb, "-s", serial, "shell", "monkey", "-p", package, "1")
    if b"No activities found" in reply or b"Events injected: 0" in reply:
        raise AdbError(f"Không mở được ứng dụng {package}.")


def foreground_package(adb: str, serial: str) -> str:
    raw = run_adb(adb, "-s", serial, "shell", "dumpsys", "window", timeout=30)
    text = raw.decode("utf-8", "replace")
    for pattern in (r"mCurrentFocus[^\n]*?\bu\d+\s+([\w.]+)/",
                    r"mCurrentFocus[^\n]*?\s([\w.]+)/"):
        match = re.search(pattern, text)
        if match:
            package = match.group(1)
            if package not in {"com.android.systemui", "com.android.launcher3"}:
                return package
    raise AdbError("Chưa nhận ra game đang mở. Hãy vào OMG 3Q rồi thử lại.")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(TITLE)
        root.resizable(True, True)
        root.minsize(820, 300)
        self.events: queue.Queue = queue.Queue()
        self.sessions = SessionRegistry()
        self.busy = False
        # The instance manager can be opened even when MuMu ADB is absent.
        try:
            self.adb = find_adb()
        except AdbError:
            self.adb = ""
        self.providers = detect_emulators(DEFAULT_MANAGER, find_ldmultiplayer())
        self.provider_name = tk.StringVar(value=self.providers[0].label if self.providers else "")
        self.instance_dialog = None
        if self.providers:
            self.adb = str(self.providers[0].adb)
        self.serial = tk.StringVar(value="")
        self.excel_path = tk.StringVar(value=str(Path(__file__).with_name("account.xlsx")))
        self.batch_running = False
        self.dungeon_limit = tk.StringVar(value="0")
        self.status = tk.StringVar(value="Mở instance, kết nối rồi chọn Script A, B hoặc C.")
        self._build()
        self._refresh_busy()
        root.update_idletasks()
        root.minsize(820, root.winfo_reqheight())
        root.geometry("")  # Fit the initial window to its contents.
        root.protocol("WM_DELETE_WINDOW", self._close)
        self.serial.trace_add("write", lambda *args: self._refresh_busy())
        root.after(100, self._drain_events)

    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Giả lập").grid(row=0, column=0, sticky="w")
        self.provider_combo = ttk.Combobox(top, textvariable=self.provider_name,
            values=[p.label for p in self.providers], state="readonly", width=14)
        self.provider_combo.grid(row=0, column=1, padx=6)
        self.provider_combo.bind("<<ComboboxSelected>>", self._provider_changed)
        self.open_emulator_button = ttk.Button(top, text=f"Mở {self.provider_name.get() or 'giả lập'}",
            command=self.open_instances, state="normal" if self.providers else "disabled")
        self.open_emulator_button.grid(row=0, column=2, padx=4)
        self.catalog_text = tk.StringVar(value="Đang quét instance…" if self.providers else "Chưa tìm thấy MuMu hoặc LDPlayer.")
        ttk.Label(top, textvariable=self.catalog_text, wraplength=340).grid(row=0, column=3, columnspan=4, padx=10, sticky="w")
        self._scan_catalog()

        ttk.Label(top, text="Thao tác trên").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.target_name = tk.StringVar()
        self.target_sessions = []
        self.target_combo = ttk.Combobox(top, textvariable=self.target_name, state="readonly", width=38)
        self.target_combo.grid(row=1, column=1, columnspan=3, sticky="w", padx=6, pady=(8, 0))
        self.target_combo.bind("<<ComboboxSelected>>", self._target_changed)
        ttk.Label(top, text="Mỗi instance có tác vụ và điều khiển dừng riêng", wraplength=280).grid(row=1, column=4, columnspan=3, sticky="w", pady=(8, 0))

        excel = ttk.LabelFrame(self.root, text="Tài khoản Excel", padding=9)
        excel.pack(fill="x", padx=10)
        excel.columnconfigure(3, weight=1)
        ttk.Label(excel, text="Tệp Excel").grid(row=0, column=0, sticky="w")
        ttk.Entry(excel, textvariable=self.excel_path, width=40).grid(row=0, column=1, columnspan=3, padx=8, sticky="ew")
        ttk.Button(excel, text="Chọn tệp…", command=self.choose_excel).grid(row=0, column=4)
        self.script_buttons = []
        for col, script in enumerate(("A", "B", "C")):
            button = ttk.Button(excel, text=f"Script {script}", command=lambda name=script: self.run_excel_script(name))
            button.grid(row=1, column=col, padx=(0, 8), pady=(8, 0))
            self.script_buttons.append(button)
        ttk.Label(excel, text="A: ngày 1 · B: ngày tiếp theo 2–15 · C: hoàn thành ≥ 2 ngày").grid(row=1, column=3, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(excel, text="Chạy trên các instance đã kết nối · Hết tài khoản sẽ tự tắt instance").grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))
        self.excel_test_button = ttk.Button(excel, text="Test Excel · 2 MuMu × 3 lượt", command=self.run_excel_login_test)
        self.excel_test_button.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(excel, text="3 lượt/máy · Giữ X/V để kiểm tra").grid(row=3, column=3, columnspan=2, sticky="w", pady=(8, 0))
        dungeon = ttk.LabelFrame(self.root, text="Cỗ Máy Thời Gian · Phó Bản", padding=8)
        dungeon.pack(fill="x", padx=10, pady=(8, 0))
        self.dungeon_button = ttk.Button(dungeon, text="Tự động vượt phó bản", command=self.run_dungeon)
        self.dungeon_button.pack(side="left")
        ttk.Label(dungeon, text="Dừng sau số ải thắng:").pack(side="left", padx=(16, 5))
        ttk.Spinbox(dungeon, from_=0, to=999, width=5, textvariable=self.dungeon_limit).pack(side="left")
        ttk.Label(dungeon, text="0 = chạy đến khi thua · Dùng phiên game đang mở", wraplength=290).pack(side="left", padx=12)

        equipment = ttk.Frame(self.root, padding=(10, 8, 10, 0))
        equipment.pack(fill="x")
        self.equipment_button = ttk.Button(equipment, text="Trang bị + Cường hóa toàn đội", command=self.run_equipment)
        self.equipment_button.pack(side="left")
        ttk.Label(equipment, text="Cỗ Máy Thời Gian · Tối đa 6 tướng · Lưu kết quả từng tướng").pack(side="left", padx=12)

        foot = ttk.Frame(self.root, padding=(10, 12, 10, 10))
        foot.pack(fill="x")
        ttk.Button(foot, text="Dừng sau bước hiện tại", command=self.stop_current).pack(side="left", padx=8)
        ttk.Label(foot, textvariable=self.status, wraplength=540).pack(side="left", padx=12)

    def _close(self) -> None:
        self.sessions.stop_all()
        self.root.destroy()

    def choose_excel(self):
        if self.batch_running:
            return
        path = filedialog.askopenfilename(title="Chọn danh sách tài khoản", filetypes=[("Excel", "*.xlsx")])
        if path:
            self.excel_path.set(path)

    def run_excel_login_test(self):
        if self.batch_running or any(s.active for s in self.sessions.connected()):
            self.status.set("Đang có tác vụ; hãy dừng trước khi test.")
            return
        provider = next((p for p in self.providers if p.kind == 'mumu'), None)
        if provider is None:
            self.status.set("Chưa tìm thấy MuMu.")
            return
        try:
            from excel_login_test import ExcelLoginTest
            test = ExcelLoginTest(self.sessions, provider, self.excel_path.get().strip(),
                run_adb, input_text, launch_game,
                lambda session, text: self.events.put(('device_progress', (session, text), None)),
                wait_forever=getattr(self, '_test_wait_forever', False),
                rounds=getattr(self, '_test_rounds', 3),
                iteration_offset=getattr(self, '_test_iteration_offset', 0),
                **getattr(self, '_test_options', {}))
        except Exception as exc:
            messagebox.showerror("Test Excel", str(exc))
            return
        self._test_expected = test.rounds * (1 if test.instance_name else 2)
        self._test_wait_forever = False
        self._test_options = {}
        self.batch_running = True
        self.excel_test_button.configure(state='disabled')
        for button in self.script_buttons:
            button.configure(state='disabled')
        def work():
            try:
                results = test.run()
            except Exception:
                results = [{'completed': 0, 'error': 'Không hoàn tất phiên test; xem nhật ký.', 'closed': False}]
            self.events.put(('excel_test_done', results, None))
        threading.Thread(target=work, daemon=True).start()
        self.status.set(f"Test {test.instance_name or '2 MuMu'} × {test.rounds} lượt · " + ("không timeout" if test.wait_forever else "timeout mặc định") + " · Dừng từ hộp điều khiển instance.")


    def run_excel_script(self, script):
        if self.batch_running:
            self.status.set("Đang chạy một script; hãy chờ hoặc dừng các instance trước.")
            return
        sessions = self.sessions.connected()
        if not sessions:
            self.status.set("Hãy mở và kết nối ít nhất một instance trước.")
            return
        if any(session.active for session in sessions):
            self.status.set("Có instance đang chạy tác vụ; hãy chờ hoặc dừng trước khi chọn script.")
            return
        try:
            workbook = AccountWorkbook(self.excel_path.get().strip())
        except Exception as exc:
            messagebox.showerror("Excel", f"Không mở/ghi được Excel. Hãy đóng tệp trong Excel rồi thử lại.\n{exc}")
            return
        started = []
        for session in sessions:
            if not session.begin():
                for previous in started:
                    previous.finish('Sẵn sàng')
                self.status.set("Instance vừa nhận tác vụ khác; chưa bắt đầu script.")
                return
            started.append(session)
        package = PACKAGE
        self.batch_running = True
        for button in self.script_buttons:
            button.configure(state='disabled')
        def progress(session, message):
            self.events.put(('device_progress', (session, message), None))
        def cycle(session):
            connect(*session.connection)
            return ExcelCycle(session, run_adb, input_text, package,
                              lambda text: progress(session, text))
        batch = ScriptBatch(workbook, script, sessions, cycle,
                            lambda session: shutdown_session(session, run_adb), progress)
        def work():
            try:
                results = batch.run()
                self.events.put(('batch_done', results, None))
            except Exception as exc:
                for session in sessions:
                    session.finish('Lỗi điều phối')
                self.events.put(('batch_done', [{'error': str(exc), 'closed': False, 'completed': 0}], None))
        threading.Thread(target=work, daemon=True).start()
        self.status.set(f"Script {script} đang chạy trên {len(sessions)} instance.")
        self._refresh_busy()

    def run_dungeon(self) -> None:
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not DungeonDetector().results_ready:
            messagebox.showinfo("Phó bản · thiếu tệp nhận diện", "Bộ ảnh nhận diện phó bản chưa đầy đủ. Hãy khôi phục thư mục assets/dungeon từ bản tool đầy đủ rồi mở lại.")
            return
        try:
            limit = int(self.dungeon_limit.get())
            if limit < 0:
                raise ValueError()
        except ValueError:
            messagebox.showinfo("Phó bản", "Số ải thắng phải là số nguyên từ 0 trở lên. Nhập 0 để chạy đến khi thua.")
            return
        serial = self.serial.get().strip()
        package = PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(kind, value):
            self.events.put(("device_" + kind, (session, value), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào nhân vật muốn chạy phó bản trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package)
            engine = DungeonEngine(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                                   progress=lambda text: emit("progress", text))
            return engine.run(max_wins=limit)

        self._worker(work, self._dungeon_complete)

    def _dungeon_complete(self, result) -> None:
        self.last_dungeon_result = result
        self.status.set(result.message)
        if result.status in {"error", "unknown", "timeout", "needs_samples", "existing_result"}:
            messagebox.showwarning("Phó bản đã dừng", result.message +
                                   (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    @property
    def busy(self):
        if hasattr(self, "sessions") and hasattr(self, "serial"):
            return self.sessions.device(self.adb, self.serial.get().strip()).active
        return getattr(self, "_manual_busy", False)

    @busy.setter
    def busy(self, value):
        self._manual_busy = value

    def _refresh_busy(self):
        value = self.busy or not self.serial.get().strip()
        self.dungeon_button.configure(state="disabled" if value else "normal")
        self.equipment_button.configure(state="disabled" if value else "normal")

    def _set_busy(self, value, message=None):
        self._refresh_busy()
        if message:
            self.status.set(message)

    def stop_current(self):
        self.sessions.device(self.adb, self.serial.get().strip()).control.cancelled.set()
        self.status.set("Đang dừng tác vụ trên instance đang chọn sau lệnh hiện tại.")

    def _refresh_targets(self):
        current = self.sessions.device(self.adb, self.serial.get().strip())
        self.target_sessions = [session for session in self.sessions.connected()
                                if session.name != "Thiết bị đang chọn"]
        self.target_combo.configure(values=[session.name for session in self.target_sessions])
        if current in self.target_sessions:
            self.target_combo.current(self.target_sessions.index(current))
        elif self.target_sessions and not current.active:
            self.target_combo.current(0)
            self._target_changed()

    def _target_changed(self, event=None):
        index = self.target_combo.current()
        if 0 <= index < len(self.target_sessions):
            session = self.target_sessions[index]
            self.adb, serial = session.connection
            self.serial.set(serial)
            self.status.set(session.name + " · " + session.state())
            self._refresh_busy()

    def run_equipment(self) -> None:
        if self.busy:
            self.status.set("Đang thực hiện một thao tác khác.")
            return
        if not EquipmentDetector().ready:
            messagebox.showinfo("Trang bị", "Thiếu bộ ảnh assets/equipment. Hãy khôi phục bộ tool đầy đủ.")
            return
        serial, package = self.serial.get().strip(), PACKAGE
        adb = self.adb
        session = self.sessions.device(adb, serial)
        control = session.control
        def emit(kind, value):
            self.events.put(("device_" + kind, (session, value), None))

        def work():
            connect(adb, serial)
            if foreground_package(adb, serial) != package:
                raise AdbError("Hãy mở OMG 3Q và vào sảnh Cỗ Máy Thời Gian hoặc Đội Hình trước.")
            device = AdbDevice(adb, serial, run_adb, input_text, package)
            skill = TeamEquipmentSkill(device, stop=control.cancelled, clock=control.clock, sleeper=control.sleep,
                                   progress=lambda text: emit("progress", text))
            return skill.run()

        self._worker(work, self._equipment_complete)

    def _equipment_complete(self, result) -> None:
        self.last_equipment_result = result
        self.status.set(result.message)
        if result.status in {"error", "blocked", "needs_samples"}:
            messagebox.showwarning("Skill trang bị đã dừng", result.message +
                                   (f"\nẢnh kiểm tra: {result.screenshot}" if result.screenshot else ""))

    def _worker(self, func, done=None):
        if not self.serial.get().strip():
            self.status.set("Hãy mở và chọn instance ở ô Thao tác trên trước.")
            return
        if not self.adb:
            try:
                self.adb = find_adb()
            except AdbError as exc:
                messagebox.showerror("ADB", str(exc))
                return
        session = self.sessions.device(self.adb, self.serial.get().strip())
        if not session.begin():
            self.status.set("Instance này đang có tác vụ; hãy chọn instance khác ở ô Thao tác trên.")
            return
        self._refresh_busy()
        def runner():
            result, error = None, None
            try:
                with active_session(session):
                    result = func()
                session.finish(getattr(result, "message", "Đã hoàn tất"))
            except InterruptedError:
                session.finish("Đã dừng tác vụ")
            except Exception as exc:
                error = str(exc)
                session.finish("Lỗi: " + error)
            self.events.put(("task_done", (session, result, error), done))
        threading.Thread(target=runner, daemon=True).start()

    def _drain_events(self) -> None:
        try:
            while True:
                kind, value, done = self.events.get_nowait()
                if kind == "excel_test_done":
                    self.batch_running = False
                    self.excel_test_button.configure(state='normal')
                    for button in self.script_buttons:
                        button.configure(state='normal')
                    completed = sum(r.get('completed', 0) for r in value)
                    errors = sum(bool(r.get('error')) for r in value)
                    self.status.set(f"Test kết thúc · {completed}/{getattr(self, '_test_expected', 6)} lượt · {errors} instance lỗi · Giữ nguyên X/V trong Excel.")
                    self._refresh_busy()
                elif kind == "batch_done":
                    self.batch_running = False
                    for button in self.script_buttons:
                        button.configure(state='normal')
                    self._refresh_busy()
                    errors = [r['error'] for r in value if r.get('error')]
                    completed = sum(r.get('completed', 0) for r in value)
                    message = "Đã xong" if not errors and all(r.get('closed') for r in value) else f"Đã kết thúc · hoàn thành {completed} tài khoản. " + " · ".join(errors)
                    self.status.set(message)
                    messagebox.showinfo('Script Excel', message)
                elif kind == "instance_ready":
                    self._refresh_targets()
                    self._refresh_busy()
                elif kind == "session_changed":
                    self._refresh_busy()
                elif kind == "device_progress":
                    session, payload = value
                    session.status = payload
                    if session is self.sessions.device(self.adb, self.serial.get().strip()):
                        self.status.set(session.name + " · " + payload)
                elif kind == "task_done":
                    session, result, error = value
                    self._refresh_busy()
                    if session is self.sessions.device(self.adb, self.serial.get().strip()):
                        if error:
                            self.status.set(session.name + " · " + error)
                            messagebox.showerror("OMG 3Q", error)
                        elif done and result is not None:
                            done(result)
                        else:
                            self.status.set(session.name + " · " + session.state())
                elif kind == "catalog":
                    name, text = value
                    if self.provider_name.get() == name:
                        self.catalog_text.set(text)
                elif kind == "progress":
                    self.status.set(value)
                elif kind == "error":
                    self._set_busy(False, value)
                    messagebox.showerror("OMG 3Q", value)
                else:
                    self._set_busy(False)
                    if done:
                        done(value)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _provider_changed(self, event=None):
        provider = next((p for p in self.providers if p.label == self.provider_name.get()), None)
        if provider and not self.sessions.connected():
            self.adb = str(provider.adb)
        self.open_emulator_button.configure(text=f"Mở {self.provider_name.get()}")
        self._scan_catalog()

    def _scan_catalog(self):
        name = self.provider_name.get()
        self.active_provider_name = name
        provider = next((p for p in self.providers if p.label == name), None)
        if not provider:
            return
        self.catalog_text.set("Đang quét instance…")
        def work():
            try:
                text = f"{len(provider.instances())} instance có sẵn · Tự mở OMG 3Q sau khởi động"
            except Exception as exc:
                text = f"Chưa quét được instance: {exc}"
            self.events.put(("catalog", (name, text), None))
        threading.Thread(target=work, daemon=True).start()

    def open_instances(self):
        if self.instance_dialog and self.instance_dialog.window.winfo_exists():
            self.instance_dialog.window.lift()
            return
        provider = next((p for p in self.providers if p.label == self.provider_name.get()), None)
        if provider:
            self.instance_dialog = InstanceDialog(self, provider)
            self.provider_combo.configure(state="disabled")

    def start_mumu(self):
        self.provider_name.set("MuMu")
        self.open_instances()

    def start_ldmultiplayer(self):
        self.provider_name.set("LDPlayer")
        self.open_instances()


def main() -> None:
    root = tk.Tk()
    try:
        app = App(root)
        import sys
        if '--excel-login-test' in sys.argv:
            app._test_wait_forever = '--test-no-timeout' in sys.argv
            app._test_rounds = 1 if '--test-fourth-round' in sys.argv else 3
            app._test_iteration_offset = 3 if '--test-fourth-round' in sys.argv else 0
            if '--test-stt9-no-wait' in sys.argv:
                app._test_rounds = 1
                app._test_iteration_offset = 0
                app._test_options = dict(fixed_waits=False, instance_name='Android Device-1', target_stt=9, reuse_existing=True)
            if '--test-stt7-8-no-wait' in sys.argv:
                app._test_rounds = 2
                app._test_iteration_offset = 0
                app._test_options = dict(fixed_waits=False, instance_name='Android Device-1', allowed_stts=[7,8], reuse_existing=False)
            root.after(500, app.run_excel_login_test)
    except (AdbError, ValueError) as exc:
        messagebox.showerror("OMG 3Q", str(exc))
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()

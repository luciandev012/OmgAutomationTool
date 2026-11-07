"""Opt-in two-MuMu Excel login test; ordinary scripts retain their timeouts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import json
import shutil
import threading
import time

from account_excel import AccountWorkbook
from emulator_instances import open_instance
from login_engine import AdbDevice, Detector, LoginEngine, PACKAGE
from task_sessions import active_session
import cv2
import numpy as np


class MeasuredDetector(Detector):
    def __init__(self):
        super().__init__()
        self.match_seconds = 0.0
        self.match_calls = 0

    def find(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return super().find(*args, **kwargs)
        finally:
            self.match_seconds += time.perf_counter() - started
            self.match_calls += 1


class ExcelLoginTest:
    def __init__(self, registry, provider, path, runner, writer, launcher, progress,
                 rounds=3, log_path=None, wait_forever=False, iteration_offset=0,
                 fixed_waits=True, instance_name=None, target_stt=None, reuse_existing=False, allowed_stts=None):
        self.registry, self.provider = registry, provider
        self.runner, self.writer, self.launcher = runner, writer, launcher
        self.external_progress = progress
        self.stages = {}
        self.rounds = rounds
        self.fixed_waits = fixed_waits
        self.instance_name = instance_name
        self.target_stt = target_stt
        self.allowed_stts = allowed_stts
        self.reuse_existing = reuse_existing
        self.wait_forever = wait_forever
        self.iteration_offset = iteration_offset
        self.log_path = Path(log_path or Path(__file__).with_name('runtime') / 'excel_login_test.jsonl')
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_lock = threading.Lock()
        self.run_id = datetime.now().strftime('%Y%m%d-%H%M%S')
        # Preserve the pre-test workbook, including any earlier progress.
        backup = self.log_path.parent / f'account-before-test-{self.run_id}.xlsx'
        shutil.copy2(path, backup)
        self.book = AccountWorkbook(path, status_marks=('X', 'V'))
        self.audit('workbook_ready', accounts=len(self.book.rows), rounds=rounds, fixed_waits=fixed_waits, wait_forever=wait_forever, target_stt=target_stt, instance_name=instance_name, reuse_existing=reuse_existing, allowed_stts=allowed_stts)

    def progress(self, session, text):
        now = time.perf_counter()
        previous = self.stages.get(session.name)
        if previous is None or previous[0] != text:
            if previous:
                self.audit('stage_duration', session, stage=previous[0], seconds=round(now-previous[1], 4))
            self.stages[session.name] = (text, now)
            self.audit('stage_started', session, stage=text)
        self.external_progress(session, text)

    def timed_runner(self, session):
        def run(adb, *args, **kwargs):
            if 'screencap' in args:
                kind = 'screenshot'
            elif 'tap' in args:
                kind = 'tap'
            elif 'keyevent' in args:
                kind = 'clear_field'
            elif 'force-stop' in args:
                kind = 'force_stop'
            elif 'monkey' in args:
                kind = 'launch_game'
            elif 'ps' in args:
                kind = 'verify_exit'
            else:
                kind = 'adb_other'
            started = time.perf_counter()
            try:
                return self.runner(adb, *args, **kwargs)
            finally:
                self.audit('command_timing', session, command=kind, seconds=round(time.perf_counter()-started, 4))
        return run

    def timed_writer(self, session):
        def write(*args):
            started = time.perf_counter()
            try:
                return self.writer(*args)
            finally:
                self.audit('command_timing', session, command='type_text', seconds=round(time.perf_counter()-started, 4))
        return write

    def audit(self, event, session=None, **fields):
        record = {'time': datetime.now().astimezone().isoformat(timespec='seconds'),
                  'run': self.run_id, 'event': event, **fields}
        if session is not None:
            record['instance'] = session.name
        # Only row numbers and progress are logged, never credentials or raw ADB errors.
        with self.log_lock:
            with self.log_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')

    def sleep(self, session, seconds):
        session.control.sleep(seconds if self.fixed_waits else 0)

    def prepare(self, device, session):
        """Wait for fresh login UI, closing the launch notice before claiming a row."""
        detector = Detector()
        deadline = None if self.wait_forever else session.control.clock() + 240
        while True:
            session.control.checkpoint()
            if deadline is not None and session.control.clock() >= deadline:
                raise TimeoutError('Chưa thấy màn hình đăng nhập trong phiên test thường.')
            try:
                png = device.capture()
                frame = detector.decode(png)
                notice = detector.find(frame, 'notice_accept', .94)
                if notice:
                    raw = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
                    device.tap(*notice.center, (raw.shape[1], raw.shape[0]))
                    self.progress(session, 'Đã đóng thông báo; chờ màn hình đổi tài khoản…')
                elif (detector.find(frame, 'start_game', .94) and detector.find(frame, 'switch_account', .94)) or detector.find(frame, 'zingid', .95) or detector.find(frame, 'zingid_form', .94):
                    self.audit('login_ui_ready', session)
                    return
            except InterruptedError:
                raise
            except Exception:
                self.progress(session, 'Chưa lấy được màn hình; tiếp tục chờ, không timeout…')
            self.sleep(session, 1)

    def _invalid_account(self, account, session, iteration):
        self.book.mark_error(account, session)
        self.audit('excel_error', session, row=account.row, stt=account.row-1,
                   iteration=iteration, status='ERR', code=8011)
        self.progress(session, f'Excel STT {account.row-1}: ERR (8011); tìm tài khoản trống tiếp theo.')

    def worker(self, instance):
        session = self.registry.instance(self.provider, instance)
        if not session.begin():
            return {'instance': session.name, 'completed': 0, 'error': 'Instance đang có tác vụ.'}
        completed, error = 0, ''
        try:
            with active_session(session):
                if self.reuse_existing:
                    if not instance.running:
                        raise ValueError('Instance đã chọn chưa chạy; không tự khởi động trong lần đo này.')
                    serial = self.provider.serial(instance.index)
                    if not serial:
                        raise ValueError('Chưa có địa chỉ ADB của instance đã chọn.')
                    self.registry.bind(session, str(self.provider.adb), serial)
                    if ':' in serial:
                        self.runner(str(self.provider.adb), 'connect', serial, timeout=8)
                    self.progress(session, 'Dùng game đang mở; bắt đầu từ đóng thông báo…')
                    self.audit('attached_existing_game', session)
                else:
                    open_instance(self.provider, instance, PACKAGE, self.runner, self.launcher,
                        session.control, lambda text: self.progress(session, text), timeout=None if self.wait_forever else 180,
                        on_device=lambda adb, serial: self.registry.bind(session, adb, serial))
                device = AdbDevice(*session.connection, self.timed_runner(session), self.timed_writer(session), PACKAGE,
                    capture_options={'checkpoint': session.control.checkpoint,
                                     'sleeper': lambda seconds: self.sleep(session, seconds),
                                     'progress': lambda text: self.progress(session, text)})
                while completed < self.rounds:
                    iteration = completed + 1 + self.iteration_offset
                    # The worker which reaches login UI first gets the first blank row.
                    self.prepare(device, session)
                    saved_at = time.perf_counter()
                    if self.allowed_stts is not None:
                        account = self.book.claim('A', session, allowed_stts=self.allowed_stts)
                    else:
                        account = self.book.claim('A', session, stt=self.target_stt) if self.target_stt is not None else self.book.claim('A', session)
                    if account is None:
                        self.audit('no_accounts', session, completed=completed)
                        break
                    self.audit('excel_reserved', session, row=account.row, stt=account.row-1,
                               iteration=iteration, status='X', save_seconds=round(time.perf_counter()-saved_at, 4))
                    self.progress(session, f'Excel STT {account.row-1}: X · lượt {iteration}/{self.iteration_offset + self.rounds}')
                    recognition = MeasuredDetector()
                    result = LoginEngine(device, detector=recognition, timeout=None if self.wait_forever else 240, stop=session.control.cancelled,
                        clock=session.control.clock, sleeper=session.control.sleep, fixed_waits=self.fixed_waits,
                        metrics=lambda **data: self.audit('observation_timing', session, **data),
                        progress=lambda text: self.progress(session, text)).run(
                            account.username, account.password, reset=False, launch_on_start=not self.reuse_existing,
                            accept_terms=True, enter_game=True, prefer_played_server=True,
                            on_invalid_credentials=lambda: self._invalid_account(account, session, iteration))
                    self.audit('recognition_total', session, iteration=iteration,
                               seconds=round(recognition.match_seconds, 4), calls=recognition.match_calls)
                    if result.status == 'invalid_credentials':
                        # ERR rows stay excluded; failed credentials do not consume a successful test round.
                        self.target_stt = None
                        continue
                    if result.status != 'success':
                        if result.status == 'cancelled':
                            raise InterruptedError()
                        error = result.status
                        self.audit('login_failed', session, row=account.row, status=result.status)
                        break
                    self.audit('entered_game', session, row=account.row, iteration=iteration)
                    self.progress(session, 'Thoát game và xác nhận đã đóng…')
                    session.control.checkpoint()
                    device.run('shell', 'am', 'force-stop', PACKAGE)
                    # Confirm the process exited before recording completion.
                    exit_deadline = None if self.wait_forever else session.control.clock() + 30
                    while True:
                        session.control.checkpoint()
                        if exit_deadline is not None and session.control.clock() >= exit_deadline:
                            raise TimeoutError('Chưa xác nhận được game đã thoát.')
                        processes = device.run('shell', 'ps', '-A').decode('utf-8', 'replace')
                        if not any(line.split() and (line.split()[-1] == PACKAGE or line.split()[-1].startswith(PACKAGE + ':')) for line in processes.splitlines()):
                            break
                        self.sleep(session, 1)
                    self.progress(session, 'Ghi V và ngày 1 vào Excel…')
                    saved_at = time.perf_counter()
                    self.book.complete(account, session)
                    completed += 1
                    self.audit('excel_completed', session, row=account.row, stt=account.row-1,
                               iteration=iteration, status='V', day=1, value=1,
                               save_seconds=round(time.perf_counter()-saved_at, 4))
                    self.progress(session, f'Excel STT {account.row-1}: V · Ngày 1 = 1 · lượt {iteration}/{self.iteration_offset + self.rounds}')
                    self.progress(session, 'Mở lại game và đóng thông báo…')
                    device.launch(reset=False)
                # Finish the last restart too. Keep V and day 1 for the user's review.
                if not error:
                    self.prepare(device, session)
        except InterruptedError:
            error = 'cancelled'
            self.audit('cancelled', session, completed=completed)
        except Exception as exc:
            error = type(exc).__name__
            self.audit('error', session, error=error, completed=completed)
        finally:
            session.finish(error or f'Đã test {completed}/{self.rounds} lượt')
            self.audit('worker_done', session, completed=completed, error=error)
        return {'instance': session.name, 'completed': completed, 'error': error, 'closed': False}

    def run(self):
        available = self.provider.instances()
        instances = [i for i in available if i.name == self.instance_name] if self.instance_name else available[:2]
        required = 1 if self.instance_name else 2
        if len(instances) != required:
            raise ValueError('Không tìm thấy đủ instance đã chọn để test.')
        with ThreadPoolExecutor(max_workers=len(instances)) as pool:
            results = list(pool.map(self.worker, instances))
        self.audit('test_done', results=results)
        return results

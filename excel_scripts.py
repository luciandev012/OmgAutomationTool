"""Account batches: one chosen script, independent devices, one workbook writer."""
import concurrent.futures
import threading
import time
import cv2
import numpy as np

from login_engine import AdbDevice, Detector, LoginEngine
from dungeon_engine import DungeonDetector
from task_sessions import active_session


class ExcelCycle:
    def __init__(self, session, runner, writer, package, progress):
        self.session, self.control = session, session.control
        self.device = AdbDevice(*session.connection, runner, writer, package)
        self.progress = progress

    def run(self, account):
        result = LoginEngine(self.device, stop=self.control.cancelled,
            clock=self.control.clock, sleeper=self.control.sleep, progress=self.progress,
            timeout=240).run(account.username, account.password, reset=False,
                accept_terms=True, enter_game=True, prefer_played_server=True)
        if result.status != 'success':
            raise ValueError(result.message)
        detector = DungeonDetector()
        deadline = self.control.clock() + 90
        last = None
        while self.control.clock() < deadline:
            self.control.checkpoint()
            png = self.device.capture()
            frame = detector.decode(png)
            if detector.find(frame, 'event_home'):
                break
            intro = detector.find(frame, 'event_intro')
            target = detector.find(frame, 'intro_dismiss') if intro else detector.find(frame, 'time_machine')
            if target and last != target.name:
                self.progress('Vào Cỗ Máy Thời Gian…')
                x, y = target.center
                raw = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
                self.device.tap(round(x * 1920 / frame.shape[1]), round(y * 1080 / frame.shape[0]),
                                (raw.shape[1], raw.shape[0]))
                last = target.name
            self.control.sleep(.8)
        else:
            raise ValueError('Chưa xác nhận được sảnh Cỗ Máy Thời Gian.')
        self.progress('Đã vào Cỗ Máy Thời Gian; đóng và mở lại game…')
        self.control.checkpoint()
        self.device.launch(reset=True)
        detector = Detector()
        deadline = self.control.clock() + 120
        while self.control.clock() < deadline:
            self.control.checkpoint()
            frame = detector.decode(self.device.capture())
            if detector.find(frame, 'notice_accept', .94):
                self.progress('Đã về thông báo; ghi kết quả Excel trước khi chuyển tài khoản…')
                return
            self.control.sleep(1)
        raise ValueError('Chưa thấy thông báo sau khi mở lại game; chưa đánh dấu hoàn thành.')


def shutdown_session(session, runner):
    """Only clear reservations after the selected VM is confirmed stopped."""
    control = session.control
    provider = getattr(session, 'provider', None)
    index = getattr(session, 'instance_index', None)
    if provider is not None:
        provider.shutdown(index)
    else:
        runner(*session.connection[:1], '-s', session.connection[1], 'shell', 'reboot', '-p')
    deadline = control.clock() + 60
    while control.clock() < deadline:
        control.checkpoint()
        if provider is not None:
            matches = [i for i in provider.instances() if i.index == index]
            if matches and not matches[0].running:
                return
        else:
            try:
                runner(session.connection[0], '-s', session.connection[1], 'get-state', timeout=5)
            except Exception:
                return
        control.sleep(1)
    raise ValueError('Chưa xác nhận giả lập đã tắt; giữ nguyên Status.')


class ScriptBatch:
    def __init__(self, workbook, script, sessions, cycle_factory, shutdown, progress,
                 audit=lambda *args: None):
        self.workbook, self.script, self.sessions = workbook, script, sessions
        self.cycle_factory, self.shutdown, self.progress, self.audit = cycle_factory, shutdown, progress, audit
        self.abort = threading.Event()

    def worker(self, session):
        count, closed, error = 0, False, ''
        secret = ''
        try:
            with active_session(session):
                cycle = self.cycle_factory(session)
                while not self.abort.is_set():
                    session.control.checkpoint()
                    account = self.workbook.claim(self.script, session)
                    if account is None:
                        break
                    secret = account.password
                    self.audit('reserved', session, account.row)
                    self.progress(session, f'Script {self.script} · dòng {account.row} · Status x')
                    cycle.run(account)
                    session.control.checkpoint()
                    self.workbook.complete(account, session)
                    count += 1
                    self.audit('completed', session, account.row)
                    self.progress(session, f'Dòng {account.row} đã hoàn thành · Status v')
                if not self.abort.is_set():
                    self.progress(session, 'Hết tài khoản phù hợp; đang tắt giả lập…')
                    self.shutdown(session)
                    closed = True
                    self.workbook.release_after_shutdown(session)
                    self.audit('released', session, None)
        except InterruptedError:
            error = 'Đã dừng tác vụ; giữ nguyên Excel và giả lập.'
        except Exception as exc:
            error = str(exc).replace(secret, '[ẩn]') if secret else str(exc)
            self.abort.set()
        finally:
            session.finish(error or 'Đã tắt giả lập')
        return {'instance': session.name, 'completed': count, 'closed': closed, 'error': error}

    def run(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.sessions)) as pool:
            return list(pool.map(self.worker, self.sessions))

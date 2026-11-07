"""Persistent independent instance sessions and worker-local command routing."""
from contextlib import contextmanager
from pathlib import Path
import threading
from emulator_instances import LaunchControl

_context = threading.local()


def device_key(adb, serial):
    return (str(Path(adb).resolve()).casefold(), serial.replace('localhost:', '127.0.0.1:'))


class InstanceSession:
    def __init__(self, name):
        self.name = name
        self.control = LaunchControl()
        self.connection = None
        self.active = False
        self.status = 'Sẵn sàng'
        self.lock = threading.Lock()

    def begin(self):
        with self.lock:
            if self.active:
                return False
            self.active = True
            if self.control.cancelled.is_set():
                self.control.paused.clear()
            self.control.cancelled.clear()
            self.status = 'Đang chạy'
            return True

    def finish(self, status):
        with self.lock:
            self.active = False
            self.status = status

    def state(self):
        if self.control.cancelled.is_set():
            return 'Đang dừng' if self.active else 'Đã dừng tác vụ'
        if self.control.paused.is_set():
            return 'Tạm dừng sau lệnh hiện tại' if self.active else 'Đã tạm dừng thao tác'
        return self.status


class SessionRegistry:
    def __init__(self):
        self.instances = {}
        self.devices = {}
        self.lock = threading.RLock()

    def instance(self, provider, instance):
        key = (provider.kind, str(provider.console.resolve()).casefold(), instance.index)
        with self.lock:
            if key not in self.instances:
                self.instances[key] = InstanceSession(f'{provider.label} · {instance.name}')
            session = self.instances[key]
            session.name = f'{provider.label} · {instance.name}'
            session.provider = provider
            session.instance_index = instance.index
            return session

    def bind(self, session, adb, serial):
        with self.lock:
            key = device_key(adb, serial)
            existing = self.devices.get(key)
            if existing is not None and existing is not session:
                # Never transfer an active device to a different worker.
                if existing.active:
                    raise RuntimeError('Thiết bị đang có tác vụ khác; không thể đổi quyền điều khiển.')
            self.devices[key] = session
            session.connection = (adb, serial)

    def device(self, adb, serial):
        with self.lock:
            key = device_key(adb, serial)
            if key not in self.devices:
                session = InstanceSession('Thiết bị đang chọn')
                session.connection = (adb, serial)
                self.devices[key] = session
            return self.devices[key]

    def connected(self):
        with self.lock:
            return list(dict.fromkeys(self.devices.values()))

    def stop_all(self):
        with self.lock:
            for session in set(self.instances.values()) | set(self.devices.values()):
                session.control.cancelled.set()


@contextmanager
def active_session(session):
    previous = getattr(_context, 'session', None)
    _context.session = session
    try:
        yield
    finally:
        _context.session = previous


def guard_command(adb, args):
    session = getattr(_context, 'session', None)
    if session is None:
        return
    session.control.checkpoint()
    if session.connection and '-s' in args:
        serial = args[args.index('-s') + 1]
        if device_key(adb, serial) != device_key(*session.connection):
            raise RuntimeError('Đã chặn lệnh gửi nhầm instance.')

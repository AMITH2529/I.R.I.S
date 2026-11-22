import time
import threading
from typing import Optional, Callable
import serial
from serial import SerialException

class SerialHandler:

    def __init__(self, port: str='COM5', baudrate: int=115200, reconnect_interval: float=2.0, on_line_received: Optional[Callable[[str], None]]=None, on_connection_changed: Optional[Callable[[bool, str], None]]=None):
        self.port = port
        self.baudrate = baudrate
        self.reconnect_interval = reconnect_interval
        self.on_line_received = on_line_received
        self.on_connection_changed = on_connection_changed
        self._serial: Optional[serial.Serial] = None
        self._running = False
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._write_lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected and self._serial is not None and self._serial.is_open

    def start(self) -> 'SerialHandler':
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name='IRIS-ESP32-Serial')
        self._thread.start()
        return self

    def stop(self) -> None:
        self._running = False
        self._disconnect()
        if self._thread is not None and self._thread.is_alive():
            if threading.current_thread() != self._thread:
                self._thread.join(timeout=1.0)
        self._thread = None

    def send_command(self, cmd: str) -> bool:
        if not self.is_connected:
            return False
        try:
            with self._write_lock:
                if not cmd.endswith('\n'):
                    cmd += '\n'
                self._serial.write(cmd.encode('utf-8'))
                self._serial.flush()
            return True
        except (SerialException, OSError):
            self._disconnect()
            return False

    def _connect(self) -> bool:
        try:
            self._serial = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=0.2, write_timeout=0.2)
            self._connected = True
            if self.on_connection_changed:
                self.on_connection_changed(True, f'Connected to {self.port} at {self.baudrate} baud')
            return True
        except (SerialException, OSError, FileNotFoundError):
            self._serial = None
            self._connected = False
            return False

    def _disconnect(self) -> None:
        was_connected = self._connected
        self._connected = False
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except Exception:
                pass
            self._serial = None
        if was_connected and self.on_connection_changed:
            self.on_connection_changed(False, f'Disconnected from {self.port}')

    def _worker_loop(self) -> None:
        buffer = bytearray()
        while self._running:
            if not self.is_connected:
                if self._connect():
                    buffer.clear()
                else:
                    time.sleep(self.reconnect_interval)
                    continue
            try:
                waiting = self._serial.in_waiting
                if waiting > 0:
                    raw_data = self._serial.read(waiting)
                    if raw_data:
                        buffer.extend(raw_data)
                        while b'\n' in buffer:
                            line_bytes, buffer = buffer.split(b'\n', 1)
                            line_str = line_bytes.decode('utf-8', errors='ignore').strip()
                            if line_str and self.on_line_received:
                                self.on_line_received(line_str)
                else:
                    time.sleep(0.01)
            except (SerialException, OSError):
                self._disconnect()
                time.sleep(self.reconnect_interval)

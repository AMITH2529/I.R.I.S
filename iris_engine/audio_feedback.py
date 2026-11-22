import threading
import time
import winsound
from typing import Optional
try:
    import win32com.client
    _HAS_SAPI = True
except ImportError:
    _HAS_SAPI = False

class AudioFeedbackEngine:

    def __init__(self, enable_chimes: bool=True, enable_speech: bool=True):
        self.enable_chimes = enable_chimes
        self.enable_speech = enable_speech
        self._speaker = None
        if _HAS_SAPI:
            try:
                self._speaker = win32com.client.Dispatch('SAPI.SpVoice')
                self._speaker.Rate = 1
                self._speaker.Volume = 95
            except Exception:
                self._speaker = None

    def _async_beep(self, sequence: list) -> None:
        if not self.enable_chimes:
            return

        def _worker():
            try:
                for freq, dur in sequence:
                    if freq > 0:
                        winsound.Beep(int(freq), int(dur))
                    else:
                        time.sleep(dur / 1000.0)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def speak(self, text: str) -> None:
        if not self.enable_speech or not self._speaker or (not text):
            return

        def _worker():
            try:
                self._speaker.Speak(text, 1)
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def left_click(self) -> None:
        self._async_beep([(1350, 25)])

    def right_click(self) -> None:
        self._async_beep([(1600, 25), (1900, 30)])

    def double_click(self) -> None:
        self._async_beep([(1400, 20), (0, 30), (1700, 30)])

    def scroll_up(self) -> None:
        self._async_beep([(700, 15)])

    def scroll_down(self) -> None:
        self._async_beep([(500, 15)])

    def recenter(self) -> None:
        self._async_beep([(523, 30), (659, 30), (784, 45)])

    def pause(self) -> None:
        self._async_beep([(800, 35), (450, 45)])

    def resume(self) -> None:
        self._async_beep([(450, 35), (800, 45)])

    def calibrate(self) -> None:
        self._async_beep([(880, 40), (1175, 60)])

    def sniper_toggle(self, is_on: bool) -> None:
        if is_on:
            self._async_beep([(600, 25), (900, 35)])
        else:
            self._async_beep([(900, 25), (600, 35)])

    def dwell_toggle(self, is_on: bool) -> None:
        if is_on:
            self._async_beep([(750, 25), (1050, 35)])
        else:
            self._async_beep([(1050, 25), (750, 35)])

    def arm_system(self) -> None:
        self._async_beep([(600, 30), (800, 30), (1100, 50)])
        self.speak('System Armed')

    def disarm_system(self) -> None:
        self._async_beep([(1100, 30), (800, 30), (500, 50)])
        self.speak('System Disarmed')

    def proximity_alert(self) -> None:
        self._async_beep([(2200, 35), (0, 25), (2200, 35)])

    def motion_alert(self) -> None:
        self._async_beep([(950, 40), (0, 20), (950, 40)])

    def voice_command_recognized(self, command_name: str, verbal_response: Optional[str]=None) -> None:
        self._async_beep([(1050, 20), (1450, 30)])
        if verbal_response:
            self.speak(verbal_response)
        elif command_name:
            self.speak(command_name)

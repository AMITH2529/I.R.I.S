import os
import sys
import time
import math
import queue
import string
import collections
import subprocess
import threading
from typing import Optional, Callable, Dict, Any, List
import numpy as np
try:
    import sounddevice as sd
    _HAS_SD = True
except ImportError:
    _HAS_SD = False
try:
    import speech_recognition as sr
    _HAS_SR = True
except ImportError:
    _HAS_SR = False
if _HAS_SR:

    def _safe_get_flac_data(self, convert_rate=None, convert_width=None):
        wav_data = self.get_wav_data(convert_rate, convert_width)
        flac_converter = sr.get_flac_converter()
        startup_info = None
        if os.name == 'nt':
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup_info.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen([flac_converter, '--stdout', '--totally-silent', '--best', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startup_info)
        flac_data, stderr = process.communicate(wav_data)
        return flac_data
    sr.AudioData.get_flac_data = _safe_get_flac_data

class SpeechControlEngine:

    def __init__(self, command_callback: Optional[Callable[[str, Dict[str, Any]], None]]=None, sample_rate: int=16000, energy_threshold: float=28.0, silence_timeout: float=0.38):
        self.command_callback = command_callback
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_timeout = silence_timeout
        self.is_running = False
        self.is_listening = False
        self.last_transcript = ''
        self.last_action_text = ''
        self.last_action_time = 0.0
        self.audio_q: queue.Queue = queue.Queue()
        self.stream: Optional[Any] = None
        self.thread: Optional[threading.Thread] = None
        self.recognizer = sr.Recognizer() if _HAS_SR else None
        if self.recognizer:
            self.recognizer.energy_threshold = 200
            self.recognizer.dynamic_energy_threshold = False

    def start(self) -> bool:
        if not _HAS_SD or not _HAS_SR:
            print('[WARN] sounddevice or speech_recognition not available. Speech control disabled.')
            return False
        if self.is_running:
            return True
        self.is_running = True
        try:
            try:
                ambient_sample = sd.rec(int(self.sample_rate * 0.25), samplerate=self.sample_rate, channels=1, dtype='int16')
                sd.wait()
                ambient_rms = float(np.sqrt(np.mean(ambient_sample.astype(np.float32) ** 2)))
                self.energy_threshold = max(24.0, min(55.0, ambient_rms * 1.3))
                print(f'[INFO] Microphone calibrated (Ambient RMS: {ambient_rms:.1f}, Speech Threshold: {self.energy_threshold:.1f})')
            except Exception:
                self.energy_threshold = 28.0
            self.stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype='int16', blocksize=2048, callback=self._audio_callback)
            self.stream.start()
            self.thread = threading.Thread(target=self._speech_worker_loop, daemon=True)
            self.thread.start()
            print('[INFO] Speech Control Engine Online (Microphone Active).')
            return True
        except Exception as e:
            print(f'[ERROR] Failed to start microphone audio stream: {e}')
            self.is_running = False
            return False

    def stop(self) -> None:
        self.is_running = False
        self.is_listening = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if self.is_running:
            self.audio_q.put(indata.copy())

    def _speech_worker_loop(self) -> None:
        phrase_buffer: List[np.ndarray] = []
        pre_roll_buffer: collections.deque = collections.deque(maxlen=3)
        is_speaking = False
        silence_start = 0.0
        while self.is_running:
            try:
                chunk = self.audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            float_chunk = chunk.astype(np.float32)
            rms = math.sqrt(float(np.mean(float_chunk * float_chunk))) if len(float_chunk) > 0 else 0.0
            peak = float(np.max(np.abs(float_chunk))) if len(float_chunk) > 0 else 0.0
            now = time.time()
            has_speech = rms > self.energy_threshold or (peak > 260.0 and rms > self.energy_threshold * 0.65)
            if has_speech:
                if not is_speaking:
                    is_speaking = True
                    self.is_listening = True
                    phrase_buffer = list(pre_roll_buffer)
                phrase_buffer.append(chunk)
                silence_start = now
            elif is_speaking:
                phrase_buffer.append(chunk)
                if now - silence_start >= self.silence_timeout:
                    is_speaking = False
                    self.is_listening = False
                    total_samples = sum((len(c) for c in phrase_buffer))
                    if total_samples > self.sample_rate * 0.1:
                        combined_pcm = np.concatenate(phrase_buffer)
                        threading.Thread(target=self._process_audio_phrase, args=(combined_pcm,), daemon=True).start()
                    phrase_buffer = []
            else:
                pre_roll_buffer.append(chunk)

    def _process_audio_phrase(self, pcm_data: np.ndarray) -> None:
        if not self.recognizer:
            return
        raw_bytes = pcm_data.tobytes()
        audio_data = sr.AudioData(raw_bytes, self.sample_rate, 2)
        try:
            text = self.recognizer.recognize_google(audio_data, language='en-US').strip().lower()
            cleaned = text.replace('-', ' ').translate(str.maketrans('', '', string.punctuation)).strip()
            if cleaned:
                print(f"[VOICE] Recognized: '{text}' -> Intent: '{cleaned}'")
                self.last_transcript = cleaned
                self._dispatch_verbal_command(cleaned)
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            print(f'[WARN] Speech Recognition API unreachable: {e}')
        except Exception as e:
            print(f'[WARN] Speech recognition error: {e}')

    def _dispatch_verbal_command(self, raw_text: str) -> None:
        text = raw_text.strip().lower()
        now = time.time()
        action_name = ''
        action_data: Dict[str, Any] = {'raw_text': text}
        verbal_response = ''
        if any((w in text for w in ('double click', 'doubleclick', 'double'))):
            action_name = 'double_click'
            verbal_response = 'Double click'
        elif any((w in text for w in ('right click', 'rightclick', 'context menu'))):
            action_name = 'right_click'
            verbal_response = 'Right click'
        elif any((w in text for w in ('click', 'left click', 'press', 'select'))):
            action_name = 'left_click'
            verbal_response = 'Click'
        elif 'scroll up' in text or text == 'up' or 'page up' in text:
            action_name = 'scroll_up'
            verbal_response = 'Scroll up'
        elif 'scroll down' in text or text == 'down' or 'page down' in text:
            action_name = 'scroll_down'
            verbal_response = 'Scroll down'
        elif any((w in text for w in ('center', 'recenter', 'middle'))):
            action_name = 'recenter'
            verbal_response = 'Recentered'
        elif any((w in text for w in ('pause', 'freeze', 'sleep'))):
            action_name = 'pause'
            verbal_response = 'Paused'
        elif any((w in text for w in ('resume', 'track', 'wake up'))):
            action_name = 'resume'
            verbal_response = 'Resumed'
        elif any((w in text for w in ('sniper', 'precision'))):
            action_name = 'toggle_sniper'
            verbal_response = 'Precision mode'
        elif any((w in text for w in ('dwell', 'auto click'))):
            action_name = 'toggle_dwell'
            verbal_response = 'Dwell click'
        elif any((w in text for w in ('calibrate', 'reset baseline'))):
            action_name = 'calibrate'
            verbal_response = 'Calibrated'
        elif 'chrome' in text or 'browser' in text or 'google' in text:
            action_name = 'open_app'
            action_data['target'] = 'chrome'
            self.launch_application('chrome')
            verbal_response = 'Opening Chrome'
        elif 'youtube' in text:
            action_name = 'open_url'
            action_data['url'] = 'https://www.youtube.com'
            self.launch_uri('https://www.youtube.com')
            verbal_response = 'Opening YouTube'
        elif 'notepad' in text or 'text editor' in text:
            action_name = 'open_app'
            action_data['target'] = 'notepad'
            self.launch_application('notepad')
            verbal_response = 'Opening Notepad'
        elif 'calculator' in text or 'calc' in text:
            action_name = 'open_app'
            action_data['target'] = 'calc'
            self.launch_application('calc')
            verbal_response = 'Opening Calculator'
        elif 'files' in text or 'explorer' in text or 'file manager' in text:
            action_name = 'open_app'
            action_data['target'] = 'explorer'
            self.launch_application('explorer')
            verbal_response = 'Opening File Explorer'
        elif 'settings' in text:
            action_name = 'open_uri'
            self.launch_uri('ms-settings:')
            verbal_response = 'Opening Settings'
        elif 'task manager' in text:
            action_name = 'open_app'
            self.launch_application('taskmgr')
            verbal_response = 'Opening Task Manager'
        elif 'paint' in text:
            action_name = 'open_app'
            self.launch_application('mspaint')
            verbal_response = 'Opening Paint'
        elif 'camera' in text:
            action_name = 'open_uri'
            self.launch_uri('microsoft.windows.camera:')
            verbal_response = 'Opening Camera'
        elif 'word' in text:
            action_name = 'open_app'
            self.launch_application('winword')
            verbal_response = 'Opening Word'
        elif 'excel' in text:
            action_name = 'open_app'
            self.launch_application('excel')
            verbal_response = 'Opening Excel'
        elif text.startswith('open '):
            app_query = text[5:].strip()
            if app_query:
                action_name = 'open_app'
                action_data['target'] = app_query
                self.launch_application(app_query)
                verbal_response = f'Opening {app_query}'
        elif 'close' in text and ('window' in text or 'app' in text):
            action_name = 'close_window'
            self._dispatch_hotkey(['alt', 'f4'])
            verbal_response = 'Window closed'
        elif 'minimize' in text:
            action_name = 'minimize_window'
            self._dispatch_hotkey(['win', 'down'])
            verbal_response = 'Minimized'
        elif 'maximize' in text or 'full screen' in text:
            action_name = 'maximize_window'
            self._dispatch_hotkey(['win', 'up'])
            verbal_response = 'Maximized'
        elif 'desktop' in text:
            action_name = 'show_desktop'
            self._dispatch_hotkey(['win', 'd'])
            verbal_response = 'Desktop'
        elif 'disarm' in text:
            action_name = 'disarm'
            verbal_response = 'Disarming system'
        elif 'arm' in text:
            action_name = 'arm'
            verbal_response = 'Arming system'
        elif 'test led' in text or 'test light' in text:
            action_name = 'test_leds'
            verbal_response = 'Testing LEDs'
        elif 'time' in text:
            cur_time_str = time.strftime('%I:%M %p')
            verbal_response = f'The time is {cur_time_str}'
            action_name = 'time'
        elif 'help' in text:
            verbal_response = 'You can say: click, scroll up, scroll down, center, open Chrome, open Notepad, or minimize window'
            action_name = 'help'
        if action_name:
            self.last_action_text = f'VOICE: {text.upper()}'
            self.last_action_time = now
            action_data['verbal_response'] = verbal_response
            if self.command_callback:
                self.command_callback(action_name, action_data)

    @staticmethod
    def launch_application(app_name: str) -> bool:
        try:
            alias_map = {'chrome': 'chrome.exe', 'browser': 'start https://www.google.com', 'notepad': 'notepad.exe', 'calc': 'calc.exe', 'calculator': 'calc.exe', 'explorer': 'explorer.exe', 'files': 'explorer.exe', 'mspaint': 'mspaint.exe', 'paint': 'mspaint.exe', 'taskmgr': 'taskmgr.exe', 'winword': 'winword.exe', 'excel': 'excel.exe'}
            cmd = alias_map.get(app_name.lower(), app_name)
            subprocess.Popen(f'start {cmd}', shell=True)
            return True
        except Exception:
            return False

    @staticmethod
    def launch_uri(uri: str) -> bool:
        try:
            subprocess.Popen(f'start {uri}', shell=True)
            return True
        except Exception:
            return False

    @staticmethod
    def _dispatch_hotkey(keys: list) -> None:
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
        except Exception:
            pass

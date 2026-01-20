import json
import os
import time
from pynput import keyboard

class Config:
    def __init__(self, config_path='config.json'):
        self.config_path = os.path.abspath(config_path)
        self._last_mtime = 0
        self._last_check_time = 0
        self._data = {}
        
        # Default values
        self._default_data = {
            "方向键急停映射": {
                "w": "s",
                "s": "w",
                "a": "d",
                "d": "a"
            },
            "跳跃按键": "space",
            "跳跃后禁用急停时长_秒": 0.85,
            "开启功能快捷键": "home",
            "关闭功能快捷键": "end",
            "按住临时禁用键": "shift",
            "最小触发急停的按键时长_毫秒": 150,
            "双键快速冲突延迟_毫秒": 5,
            "快速Peek检测窗口_毫秒": 150,
            "急停触发预留延迟_毫秒": 15,
            "最大有效急停按键时长_毫秒": 1200,
            "多键同时按下时是否触发急停": False,
            "急停按键最大持续时长_毫秒": 70,
            "急停时长缩放比例": 0.25,
            "仅在指定窗口激活": "Counter-Strike 2"
        }
        self._data = self._default_data.copy()
        
        # Initial load
        self.load()

    def load(self):
        try:
            if not os.path.exists(self.config_path):
                print(f"Config file not found, creating default at: {self.config_path}")
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self._default_data, f, indent=2, ensure_ascii=False)
                self._data = self._default_data.copy()
                self._last_mtime = os.path.getmtime(self.config_path)
                return

            mtime = os.path.getmtime(self.config_path)
            # Only reload if file modified
            if mtime <= self._last_mtime:
                return

            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
            
            # Merge with defaults to ensure all keys exist
            self._data = self._default_data.copy()
            self._data.update(new_data)
            
            self._last_mtime = mtime
            print(f"Config loaded/reloaded from {self.config_path}")
        except Exception as e:
            print(f"Error loading config: {e}")

    def check_update(self):
        # Rate limit checks to once per second
        current_time = time.time()
        if current_time - self._last_check_time < 1:
            return
        self._last_check_time = current_time
        self.load()

    def _get_key(self, key_name):
        try:
            return getattr(keyboard.Key, key_name)
        except AttributeError:
            # If not a special key, return the character itself if it's a single char?
            # Or maybe the user provided a char like 'a'.
            # pynput KeyCode.from_char('a')
            if len(key_name) == 1:
                return keyboard.KeyCode.from_char(key_name)
            return getattr(keyboard.Key, 'space') # Fallback

    @property
    def keyboard(self):
        self.check_update()
        return self._data.get('方向键急停映射', self._default_data['方向键急停映射'])

    @property
    def enable_key(self):
        self.check_update()
        key_name = self._data.get('开启功能快捷键', 'home')
        return self._get_key(key_name)

    @property
    def disable_toggle_key(self):
        self.check_update()
        key_name = self._data.get('关闭功能快捷键', 'end')
        return self._get_key(key_name)

    @property
    def jump_key(self):
        self.check_update()
        key_name = self._data.get('跳跃按键', 'space')
        return self._get_key(key_name)

    @property
    def space_timer(self):
        self.check_update()
        return self._data.get('跳跃后禁用急停时长_秒', 0.85)

    @property
    def disable_key(self):
        self.check_update()
        key_name = self._data.get('按住临时禁用键', 'shift')
        # Handle shift specially as it can be left or right
        if key_name.lower() == 'shift':
            return [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r]
        
        k = self._get_key(key_name)
        return [k]

    @property
    def min_stop_trigger_ms(self):
        self.check_update()
        return self._data.get('最小触发急停的按键时长_毫秒', 150)

    @property
    def press_delay_ms(self):
        self.check_update()
        return self._data.get('双键快速冲突延迟_毫秒', 5)

    @property
    def peek_window_ms(self):
        self.check_update()
        return self._data.get('快速Peek检测窗口_毫秒', 150)

    @property
    def peek_delay_ms(self):
        self.check_update()
        return self._data.get('急停触发预留延迟_毫秒', 15)

    @property
    def max_stop_hold_ms(self):
        self.check_update()
        return self._data.get('最大有效急停按键时长_毫秒', 1200)

    @property
    def stop_on_multi_keys(self):
        self.check_update()
        return self._data.get('多键同时按下时是否触发急停', False)

    @property
    def stop_duration_ms(self):
        self.check_update()
        return self._data.get('急停按键最大持续时长_毫秒', 70)

    @property
    def stop_scaling_ratio(self):
        self.check_update()
        return self._data.get('急停时长缩放比例', 0.25)

    @property
    def target_window(self):
        self.check_update()
        return self._data.get('仅在指定窗口激活', 'Counter-Strike 2')

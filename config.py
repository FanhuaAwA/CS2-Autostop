import json
import os
import time
import threading
from pynput import keyboard

class Config:
    def __init__(self, config_path='config.json'):
        self.config_path = os.path.abspath(config_path)
        self._last_mtime = 0
        self._data = {}
        self._cache = {}
        self._lock = threading.Lock()
        
        # Default values
        self._default_data = {
            "方向键急停映射": {"w": "s", "s": "w", "a": "d", "d": "a"},
            "跳跃按键": "space",
            "跳跃后禁用急停时长_秒": 0.85,
            "开启功能快捷键": "home",
            "关闭功能快捷键": "end",
            "按住临时禁用键": "shift",
            "最小触发急停的按键时长_毫秒": 150,
            "双键快速冲突延迟_毫秒": 5,
            "快速Peek检测窗口_毫秒": 150,
            "急停触发预留延迟_毫秒": 8,
            "最大有效急停按键时长_毫秒": 1200,
            "多键同时按下时是否触发急停": True,
            "急停按键最大持续时长_毫秒": 70,
            "急停时长缩放比例": 0.25,
            "仅在指定窗口激活": "Counter-Strike 2",
            "是否开启自动检测窗口": True
        }
        
        # Initial load
        self._load_and_cache()
        
        # Start background reload thread
        self._stop_event = threading.Event()
        self._reload_thread = threading.Thread(target=self._reload_loop, daemon=True)
        self._reload_thread.start()

    def _reload_loop(self):
        while not self._stop_event.is_set():
            time.sleep(2)  # Check every 2 seconds
            self._load_and_cache()

    def _load_and_cache(self):
        try:
            if not os.path.exists(self.config_path):
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self._default_data, f, indent=2, ensure_ascii=False)
                mtime = os.path.getmtime(self.config_path)
                data = self._default_data.copy()
            else:
                mtime = os.path.getmtime(self.config_path)
                if mtime <= self._last_mtime:
                    return
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = self._default_data.copy()
                    data.update(json.load(f))

            new_cache = {}
            # Pre-parse keys
            new_cache['keyboard'] = data.get('方向键急停映射', self._default_data['方向键急停映射'])
            new_cache['enable_key'] = self._get_key_obj(data.get('开启功能快捷键', 'home'))
            new_cache['disable_toggle_key'] = self._get_key_obj(data.get('关闭功能快捷键', 'end'))
            new_cache['jump_key'] = self._get_key_obj(data.get('跳跃按键', 'space'))
            new_cache['space_timer'] = data.get('跳跃后禁用急停时长_秒', 0.85)
            
            dk = data.get('按住临时禁用键', 'shift')
            if dk.lower() == 'shift':
                new_cache['disable_key'] = [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r]
            else:
                new_cache['disable_key'] = [self._get_key_obj(dk)]
            
            new_cache['min_stop_trigger_ms'] = data.get('最小触发急停的按键时长_毫秒', 150)
            new_cache['press_delay_ms'] = data.get('双键快速冲突延迟_毫秒', 5)
            new_cache['peek_window_ms'] = data.get('快速Peek检测窗口_毫秒', 150)
            new_cache['peek_delay_ms'] = data.get('急停触发预留延迟_毫秒', 15)
            new_cache['max_stop_hold_ms'] = data.get('最大有效急停按键时长_毫秒', 2300)
            new_cache['stop_on_multi_keys'] = data.get('多键同时按下时是否触发急停', False)
            new_cache['stop_duration_ms'] = data.get('急停按键最大持续时长_毫秒', 70)
            new_cache['stop_scaling_ratio'] = data.get('急停时长缩放比例', 0.25)
            new_cache['target_window'] = data.get('仅在指定窗口激活', 'Counter-Strike 2')
            # 强制默认开启自动检测窗口
            new_cache['auto_window_detection'] = data.get('是否开启自动检测窗口', True)

            with self._lock:
                self._data = data
                self._cache = new_cache
                self._last_mtime = mtime
            # print(f"Config auto-reloaded: {time.strftime('%H:%M:%S')}") # 注释掉频繁的日志
        except Exception as e:
            print(f"Error loading config: {e}")

    def _get_key_obj(self, key_name):
        try:
            return getattr(keyboard.Key, key_name)
        except AttributeError:
            if len(key_name) == 1:
                return keyboard.KeyCode.from_char(key_name)
            return keyboard.Key.space

    @property
    def keyboard(self): return self._cache.get('keyboard')
    @property
    def enable_key(self): return self._cache.get('enable_key')
    @property
    def disable_toggle_key(self): return self._cache.get('disable_toggle_key')
    @property
    def jump_key(self): return self._cache.get('jump_key')
    @property
    def space_timer(self): return self._cache.get('space_timer')
    @property
    def disable_key(self): return self._cache.get('disable_key')
    @property
    def min_stop_trigger_ms(self): return self._cache.get('min_stop_trigger_ms')
    @property
    def press_delay_ms(self): return self._cache.get('press_delay_ms')
    @property
    def peek_window_ms(self): return self._cache.get('peek_window_ms')
    @property
    def peek_delay_ms(self): return self._cache.get('peek_delay_ms')
    @property
    def max_stop_hold_ms(self): return self._cache.get('max_stop_hold_ms')
    @property
    def stop_on_multi_keys(self): return self._cache.get('stop_on_multi_keys')
    @property
    def stop_duration_ms(self): return self._cache.get('stop_duration_ms')
    @property
    def stop_scaling_ratio(self): return self._cache.get('stop_scaling_ratio')
    @property
    def target_window(self): return self._cache.get('target_window')
    @property
    def auto_window_detection(self): return self._cache.get('auto_window_detection')

    def update_setting(self, key, value):
        """手动更新某个配置项并保存到文件"""
        with self._lock:
            self._data[key] = value
            # 同时更新缓存以保证实时性
            if key == "是否开启自动检测窗口":
                self._cache['auto_window_detection'] = value
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

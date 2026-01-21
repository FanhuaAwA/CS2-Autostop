from pynput.keyboard import Controller
from pynput import keyboard
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from config import Config
from utils import key_to_str, get_active_window_title


class AutoStop:
    def __init__(self):
        self.config = Config()
        
        # 核心状态
        self.active = True           # Home/End 控制的总开关
        self.manual_override = False # 非游戏窗口手动开启
        self.window_active = False   # 默认关闭，等待检测线程激活
        self.space_flag = False      # 跳跃禁用
        self.disable_flag = False    # Shift 临时禁用

        # 按键状态追踪 (加锁保护)
        self.lock = threading.Lock()
        self.press_timer = {}        # {key_str: start_ts}
        self.physical_keys = set()   # {key_str}
        self.simulated_press_count = {}   # {key_str: count}
        self.simulated_release_count = {} # {key_str: count}
        self.key_press_history = {}       # {key_str: last_press_ts}
        
        # 快速连按冲突抑制
        self.last_press_ts = 0.0
        self.last_press_key = None
        self.suppressed_keys = set()

        self.keyboard_controller = Controller()
        self.executor = ThreadPoolExecutor(max_workers=4) # 限制线程池大小，复用线程

        # 双击检测状态
        self.last_home_press = 0
        self.double_click_threshold = 0.4 # 400ms 内连按两次视为双击

        # 启动后台任务
        self._stop_event = threading.Event()
        self._window_thread = threading.Thread(target=self._window_monitor_loop, daemon=True)
        self._window_thread.start()

        print("AutoStop engine initialized.")
        self.run()

    def _window_monitor_loop(self):
        """独立线程监控窗口聚焦状态，减少监听器主线程压力"""
        while not self._stop_event.is_set():
            # 只有在 active 且开启了 auto_window_detection 时才进行检测
            if self.active and self.config.auto_window_detection:
                target = self.config.target_window
                if target:
                    title = get_active_window_title()
                    new_state = target in title
                    if new_state != self.window_active:
                        self.window_active = new_state
            else:
                # 全局模式或关闭状态下，保持 window_active 为 True 避免逻辑阻塞
                if not self.window_active:
                    self.window_active = True
            
            time.sleep(1.0) # 1秒检查一次足够了

    def on_press(self, key):
        try:
            # 1. 处理控制快捷键 (优先级最高)
            if key == self.config.enable_key:
                now_ts = time.time()
                # 检查双击逻辑
                if now_ts - self.last_home_press < self.double_click_threshold:
                    # 双击：开启自动检测窗口 (且确保功能是开启的)
                    self.active = True
                    self.config.update_setting("是否开启自动检测窗口", True)
                    self.manual_override = False # 双击切换到自动检测模式
                    print("\n>>> [SYSTEM] Mode: Auto Window Detection ENABLED")
                    self.last_home_press = 0 
                else:
                    # 单击：仅开启功能（全局模式）
                    if not self.active or self.config.auto_window_detection:
                        self.active = True
                        self.config.update_setting("是否开启自动检测窗口", False)
                        self.window_active = True
                        self.manual_override = False
                        print("\n>>> [SYSTEM] Mode: Global (Window Detection DISABLED)")
                    self.last_home_press = now_ts
                return

            if key == self.config.disable_toggle_key:
                if self.active:
                    self.active = False
                    self.manual_override = False
                    self.config.update_setting("是否开启自动检测窗口", False)
                    print("\n>>> [SYSTEM] AutoStop: DISABLED")
                return

            key_str = key_to_str(key)
            if not key_str: return

            # 2. 模拟按键过滤
            with self.lock:
                if self.simulated_press_count.get(key_str, 0) > 0:
                    self.simulated_press_count[key_str] -= 1
                    return
                
                self.physical_keys.add(key_str)
                self.key_press_history[key_str] = time.time()
            
            # 记录移动键按下日志 (仅在功能开启且符合触发条件时输出)
            if self.active and key_str in self.config.keyboard:
                # 如果是自动检测模式，必须窗口激活才输出日志
                if not self.config.auto_window_detection or self.window_active:
                    print(f"[Key] Pressed: {key_str.upper()}")
            
            # 3. 功能性按键处理
            if key == self.config.jump_key:
                self.executor.submit(self._handle_jump_delay)
                return

            if key in self.config.disable_key:
                self.disable_flag = True
                return

            # 4. 逻辑触发检查
            if not self.active or self.space_flag: return
            
            # 如果开启了自动检测，则需要检查窗口激活状态
            if self.config.auto_window_detection and not self.window_active:
                return

            # 5. 快速连按冲突抑制
            now = time.time()
            if now - self.last_press_ts < (self.config.press_delay_ms / 1000.0):
                # 修复斜向移动 BUG: 只有当按下的是同一个键，或者是非移动键时，才进行抑制
                # 对于移动键（WASD），快速切换/组合是正常操作，不应抑制
                is_movement_key = key_str in self.config.keyboard
                is_same_key = (self.last_press_key == key)
                
                if not is_movement_key or is_same_key:
                    with self.lock:
                        self.suppressed_keys.add(key_str)
                        if self.last_press_key:
                            pk_str = key_to_str(self.last_press_key)
                            if pk_str: self.suppressed_keys.add(pk_str)
            
            self.last_press_ts = now
            self.last_press_key = key

            # 6. 移动键逻辑
            if key_str in self.config.keyboard:
                with self.lock:
                    # 只有在没有对立键按下时才开始计时
                    opposite = self.config.keyboard[key_str]
                    if key_str not in self.press_timer and opposite not in self.physical_keys:
                        self.press_timer[key_str] = now

        except Exception as e:
            print(f"Error on_press: {e}")

    def on_release(self, key):
        try:
            if key in self.config.disable_key:
                self.disable_flag = False
                return

            key_str = key_to_str(key)
            if not key_str: return

            # 模拟释放过滤
            with self.lock:
                if self.simulated_release_count.get(key_str, 0) > 0:
                    self.simulated_release_count[key_str] -= 1
                    return
                
                if key_str in self.physical_keys:
                    self.physical_keys.remove(key_str)
            
            if not self.active: return

            # 核心触发逻辑
            if key_str in self.config.keyboard:
                with self.lock:
                    # 清理抑制列表
                    if key_str in self.suppressed_keys:
                        self.suppressed_keys.discard(key_str)
                        self.press_timer.pop(key_str, None)
                        return

                    # 只有被记录了按下时间的键才处理
                    if key_str not in self.press_timer: return
                    
                    start_ts = self.press_timer.pop(key_str)
                    duration = time.time() - start_ts

                # 各种抑制条件检查
                if self.disable_flag or self.space_flag: return
                
                # 如果开启了自动检测，则需要检查窗口激活状态
                if self.config.auto_window_detection and not self.window_active:
                    return
                
                # 1. 长按抑制 (撞墙保护)
                if duration * 1000 > self.config.max_stop_hold_ms: return
                
                # 2. 短按抑制 (死区保护)
                if duration * 1000 < self.config.min_stop_trigger_ms: return

                # 3. Peek 连按抑制
                opposite_key = self.config.keyboard.get(key_str)
                with self.lock:
                    last_opp = self.key_press_history.get(opposite_key, 0)
                
                # 斜向移动急停修复：
                # 只有在非多键按下的情况下，才启用严格的 Peek 连按抑制
                # 如果当前有多个移动键按下（例如 WA），则放宽或跳过此检查
                is_multi_key = len([k for k in self.press_timer if k in self.config.keyboard]) > 0
                
                if not is_multi_key:
                    if (time.time() - last_opp) * 1000 < self.config.peek_window_ms: return


                # 执行急停
                self.executor.submit(self._do_stop, key_str, duration)

        except Exception as e:
            print(f"Error on_release: {e}")

    def _do_stop(self, key_str, pressed_time):
        """执行急停物理操作"""
        # 预先获取配置，减少在延迟期间的锁竞争
        peek_delay = self.config.peek_delay_ms
        opposite_key = self.config.keyboard[key_str]
        
        if peek_delay > 0:
            time.sleep(peek_delay / 1000.0)

        # 再次检查物理按键状态
        with self.lock:
            if opposite_key in self.physical_keys: return
            self.simulated_press_count[opposite_key] = self.simulated_press_count.get(opposite_key, 0) + 1
        
        # 动态计算时长
        stop_duration = min(
            self.config.stop_duration_ms / 1000.0, 
            pressed_time * self.config.stop_scaling_ratio
        )

        try:
            self.keyboard_controller.press(opposite_key)
            print(f"[Auto] Stop Triggered: {key_str.upper()} -> {opposite_key.upper()} ({stop_duration*1000:.1f}ms)")
            time.sleep(stop_duration)
            
            with self.lock:
                if opposite_key not in self.physical_keys:
                    self.simulated_release_count[opposite_key] = self.simulated_release_count.get(opposite_key, 0) + 1
                    self.keyboard_controller.release(opposite_key)
        except Exception:
            pass

    def _handle_jump_delay(self):
        """处理跳跃后的全局延迟"""
        with self.lock:
            self.press_timer.clear()
            self.space_flag = True
        time.sleep(self.config.space_timer)
        with self.lock:
            self.space_flag = False

    def run(self):
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()

import threading
from pynput.keyboard import Controller
from pynput import keyboard
import time
from config import Config
from utils import key_to_str, get_active_window_title


class AutoStop:
    def __init__(self):
        self.config = Config()
        print("inited config")

        # 核心状态追踪
        self.press_timer = {}        # 记录按键首次按下时间: {key_str: ts}
        self.physical_keys = set()   # 当前物理按下的按键: {key_str}
        self.simulated_press_count = {}   # 记录模拟按下的次数: {key_str: count}
        self.simulated_release_count = {} # 记录模拟释放的次数: {key_str: count}
        self.key_press_history = {}  # 记录每个按键最后一次按下的时间: {key_str: ts}
        
        self.space_flag = False      # 跳跃禁用标志
        self.forward_flag = False    # 前进标志 (用于特殊处理 w)
        self.disable_flag = False    # 全局禁用标志 (Shift)
        self.active = True           # 功能开启/关闭状态 (Home/End)
        self.window_active = True    # 窗口检测状态
        self.last_window_check = 0   # 窗口检查计时
        self.manual_override = False # 手动覆盖标志 (当在非游戏窗口手动按下 Home 时)
        
        # 冲突检测
        self.last_press_ts = 0.0
        self.last_press_key = None
        self.suppressed_keys = set()

        self.keyboard_controller = Controller()
        self.lock = threading.Lock() # 状态保护锁

        print("init successful, starting listener")
        self.run()

    def on_press(self, key):
        try:
            # 1. 优先处理功能开关，不依赖 key_to_str 和 窗口检测
            if key == self.config.enable_key:
                if not self.active:
                    self.active = True
                    print(">>> AutoStop ENABLED (Home)")
                
                # 检查是否是在非游戏窗口手动开启的
                target = self.config.target_window
                if target:
                    title = get_active_window_title()
                    if target not in title:
                        self.manual_override = True
                        print(f">>> Manual Override: Enabled in non-target window ({title})")
                    else:
                        self.manual_override = False
                return
            
            if key == self.config.disable_toggle_key:
                if self.active:
                    self.active = False
                    self.manual_override = False
                    print(">>> AutoStop DISABLED (End)")
                return

            # 2. 窗口聚焦检测 (仅在功能开启且未手动覆盖时生效)
            if self.active and not self.manual_override:
                now = time.time()
                if now - self.last_window_check > 0.5: # 0.5秒检查一次窗口
                    self.last_window_check = now
                    target = self.config.target_window
                    if target:
                        title = get_active_window_title()
                        if target in title:
                            if not self.window_active:
                                self.window_active = True
                                # print(f">>> Target window focus: {title}")
                        else:
                            if self.window_active:
                                self.window_active = False
                                # print(f">>> Lost focus, AutoStop paused: {title}")

            key_str = key_to_str(key)
            if not key_str: return

            # 3. 识别并过滤模拟按键
            with self.lock:
                count = self.simulated_press_count.get(key_str, 0)
                if count > 0:
                    self.simulated_press_count[key_str] = count - 1
                    return
                
                # 记录物理按下状态
                self.physical_keys.add(key_str)
                self.key_press_history[key_str] = time.time()

            # 4. 检查跳跃
            if key == self.config.jump_key:
                threading.Thread(target=self.trigger_space, daemon=True).start()
                return

            # 5. 检查禁用键 (Shift)
            if key in self.config.disable_key:
                self.disable_flag = True
                return

            # 核心开关与窗口状态检查
            if not self.active or self.space_flag:
                return
            
            # 如果不在目标窗口且未开启手动覆盖，则不触发逻辑
            if not self.window_active and not self.manual_override:
                return

            # 3. 冲突检测 (快速连按)
            press_time = time.time()
            if press_time - self.last_press_ts < (self.config.press_delay_ms / 1000.0):
                with self.lock:
                    if key_str: self.suppressed_keys.add(key_str)
                    if self.last_press_key:
                        prev_key_str = key_to_str(self.last_press_key)
                        if prev_key_str: self.suppressed_keys.add(prev_key_str)
                print(f"Suppressing rapid press: {key_str}")

            self.last_press_ts = press_time
            self.last_press_key = key

            # 4. 业务逻辑处理
            if key_str in self.config.keyboard:
                with self.lock:
                    if key_str == 'w':
                        self.forward_flag = True
                    
                    # 如果对立键没被按下，且自己也没被记录，则记录时间
                    opposite_key = self.config.keyboard[key_str]
                    if key_str not in self.press_timer and opposite_key not in self.physical_keys:
                        self.press_timer[key_str] = press_time
                        print(f"Listen press: {key_str}")
        except Exception as e:
            print(f"Error in on_press: {e}")

    def on_release(self, key):
        try:
            # 1. 优先处理禁用键释放 (Shift)，不依赖 key_to_str
            if key in self.config.disable_key:
                self.disable_flag = False
                return

            key_str = key_to_str(key)
            if not key_str: return

            # 2. 识别并过滤模拟释放
            with self.lock:
                count = self.simulated_release_count.get(key_str, 0)
                if count > 0:
                    self.simulated_release_count[key_str] = count - 1
                    return

            release_time = time.time()

            # 更新物理状态
            with self.lock:
                if key_str in self.physical_keys:
                    self.physical_keys.remove(key_str)

            if key_str == 'w':
                self.forward_flag = False

            # 3. 核心逻辑
            if not self.active:
                return
            if key_str in self.config.keyboard:
                with self.lock:
                    # 如果在抑制列表中，只清理不触发
                    if key_str in self.suppressed_keys:
                        self.suppressed_keys.discard(key_str)
                        self.press_timer.pop(key_str, None)
                        return

                    # 只有被记录了按下时间的键才处理
                    if key_str in self.press_timer:
                        duration = release_time - self.press_timer.pop(key_str)
                        
                        # 1. 长按抑制 (解决撞墙回弹 Bug)
                        # 如果按键时间过长，说明角色可能已经撞墙停止或处于匀速运动很久，不需要全力急停
                        if duration * 1000 > self.config.max_stop_hold_ms:
                            print(f"Long hold detected ({duration:.2f}s): skipping autostop for {key_str}")
                            return

                        # 2. 多键关联抑制 (可选)
                        # 如果用户当前还按着其他方向键，可能不需要触发该键的急停（避免斜向移动时的鬼畜）
                        if not self.config.stop_on_multi_keys:
                            other_movement_keys = [k for k in self.config.keyboard.keys() if k != key_str]
                            if any(k in self.physical_keys for k in other_movement_keys):
                                print(f"Multi-key detected: skipping autostop for {key_str}")
                                return

                        # Peek 优化：如果对立键在短时间内刚被按下，说明正在进行快速 Peek，不触发急停
                        opposite_key = self.config.keyboard.get(key_str)
                        if opposite_key:
                            last_opp_press = self.key_press_history.get(opposite_key, 0)
                            if (release_time - last_opp_press) * 1000 < self.config.peek_window_ms:
                                print(f"Peek detected: skipping autostop for {key_str}")
                                return

                        # 基础校验：主开关开启、非禁用状态、非前进冲突(除非是w本身)
                        if self.active and not self.disable_flag and (not self.forward_flag or key_str == 'w'):
                            # 触发急停
                            threading.Thread(
                                target=self.trigger_stop, 
                                args=(key_str, duration), 
                                daemon=True
                            ).start()
        except Exception as e:
            print(f"Error in on_release: {e}")

    def trigger_stop(self, key_str, pressed_time):
        # 增加一个极小的延迟 (默认 15ms)，给物理按键一个“插队”的机会
        if self.config.peek_delay_ms > 0:
            time.sleep(self.config.peek_delay_ms / 1000.0)

        # 急停逻辑
        if pressed_time * 1000 > self.config.min_stop_trigger_ms:
            opposite_key = self.config.keyboard[key_str]
            
            # 关键优化 1：根据按下时长动态计算急停时长
            # 如果是短促的移动（比如在墙边），急停按键也会相应缩短，避免回弹
            # 计算公式：min(设定的最大急停时长, 按下时长 * 缩放比例)
            stop_duration = min(
                self.config.stop_duration_ms / 1000.0, 
                pressed_time * self.config.stop_scaling_ratio
            )

            # 关键优化 2：如果在此期间用户已经物理按下了对立键，则绝对不触发模拟
            with self.lock:
                if opposite_key in self.physical_keys:
                    print(f"Manual peek detected during delay: skipping autostop for {key_str}")
                    return

            print(f"Trigger AutoStop: {key_str} -> {opposite_key} (duration: {stop_duration*1000:.1f}ms)")
            try:
                # 1. 模拟按下
                with self.lock:
                    self.simulated_press_count[opposite_key] = self.simulated_press_count.get(opposite_key, 0) + 1
                
                self.keyboard_controller.press(opposite_key)
                
                # 等待动态计算出的触发时间
                time.sleep(stop_duration)
                
                # 2. 模拟释放前二次检查
                with self.lock:
                    # 如果用户已经物理按下了该键，则接管，不执行释放
                    if opposite_key in self.physical_keys:
                        print(f"User takeover detected: {opposite_key}")
                        return
                    
                    self.simulated_release_count[opposite_key] = self.simulated_release_count.get(opposite_key, 0) + 1
                
                self.keyboard_controller.release(opposite_key)
            except Exception as e:
                print(f"Error simulating key: {e}")
                # 异常处理：确保状态一致性（这里较难处理，因为无法确认 event 是否已发出，但尽量尝试释放）
                try:
                    self.keyboard_controller.release(opposite_key)
                except:
                    pass

    def trigger_space(self):
        # 跳跃时重置所有状态并暂时禁用
        with self.lock:
            self.press_timer.clear()
            self.space_flag = True
        
        time.sleep(self.config.space_timer)
        
        with self.lock:
            self.space_flag = False

    def run(self):
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()

    def stop(self):
        # 紧急重置所有模拟状态
        with self.lock:
            self.simulated_press_count.clear()
            self.simulated_release_count.clear()
            self.physical_keys.clear()
            self.press_timer.clear()

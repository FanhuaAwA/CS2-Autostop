import ctypes

def get_active_window_title():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value
        return ""
    except Exception:
        return ""

def key_to_str(key):
    try:
        # 如果是普通字符键
        return key.char
    except AttributeError:
        # 如果是特殊功能键 (如 Key.shift, Key.home 等)
        # 返回其字符串名称，例如 'shift', 'home'
        s = str(key)
        if s.startswith('Key.'):
            return s.replace('Key.', '')
        return s
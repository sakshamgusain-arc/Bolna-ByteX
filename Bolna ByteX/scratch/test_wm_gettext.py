import ctypes
from ctypes import wintypes, create_unicode_buffer, c_ssize_t

user32 = ctypes.windll.user32
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = c_ssize_t

print("SendMessageW configured successfully with c_ssize_t restype.")

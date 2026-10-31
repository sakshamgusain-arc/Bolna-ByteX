import ctypes
user32 = ctypes.windll.user32
h = user32.GetForegroundWindow()
b1 = ctypes.create_unicode_buffer(256)
b2 = ctypes.create_unicode_buffer(256)
user32.GetWindowTextW(h, b1, 256)
user32.GetClassNameW(h, b2, 256)
print(f"Foreground HWND={h}, Title='{b1.value}', Class='{b2.value}'")


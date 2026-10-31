import ctypes
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

h_cur = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
h_in = user32.OpenInputDesktop(0, False, 0x01FF)
print(f"Current thread desktop: {h_cur}, Input desktop: {h_in}")

# If we switch to input desktop
if h_in:
    ret_sd = user32.SetThreadDesktop(h_in)
    print(f"SetThreadDesktop returned: {ret_sd}")
    print(f"Foreground window after SetThreadDesktop: {user32.GetForegroundWindow()}")


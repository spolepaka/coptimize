import sys
import time
import platform
import subprocess
import threading
import re

def play_beep():
    os_name = platform.system()
    if os_name == 'Windows':
        import winsound
        winsound.Beep(1000, 500)  # Frequency 1000 Hz, duration 500 ms
    elif os_name == 'Darwin':  # macOS
        subprocess.call(['afplay', '-v', '2', 'BEEP.aiff'])
    else:
        print('\a')  # Fallback for other OS

def monitor_webcam_windows():
    import winreg
    was_in_use = False
    while True:
        in_use = False
        try:
            # Check packaged apps
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam")
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    last_used_stop, _ = winreg.QueryValueEx(subkey, "LastUsedTimeStop")
                    if last_used_stop == 0:
                        in_use = True
                        break
                    winreg.CloseKey(subkey)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)

            # Check non-packaged apps
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam\NonPackaged")
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    last_used_stop, _ = winreg.QueryValueEx(subkey, "LastUsedTimeStop")
                    if last_used_stop == 0:
                        in_use = True
                        break
                    winreg.CloseKey(subkey)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Error checking registry: {e}")

        if in_use and not was_in_use:
            play_beep()
        was_in_use = in_use
        time.sleep(1)  # Poll every second

def monitor_webcam_mac():
    command = [
        'log', 'stream', '--predicate',
        'eventMessage CONTAINS "AVCaptureSessionDidStartRunningNotification" OR eventMessage CONTAINS "AVCaptureSessionDidStopRunningNotification"'
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    was_in_use = False
    while True:
        line = process.stdout.readline().strip()
        if line and re.match(r'^\d{4}-\d{2}-\d{2}', line):
            if "AVCaptureSessionDidStartRunningNotification" in line:
                if not was_in_use:
                    print("Webcam access started:", line)
                    play_beep()
                was_in_use = True
            elif "AVCaptureSessionDidStopRunningNotification" in line:
                print("Webcam access stopped:", line)
                was_in_use = False

if __name__ == "__main__":
    os_name = platform.system()
    if os_name == 'Windows':
        monitor_webcam_windows()
    elif os_name == 'Darwin':
        monitor_webcam_mac()
    else:
        print("Unsupported OS")
        sys.exit(1)
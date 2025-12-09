#!/usr/bin/env python3
"""
Webcam Monitor with Mobile Notifications

Monitors webcam access and plays an alert sound when the camera is activated.
Optionally sends notifications to a mobile app via Firebase.

Usage:
    python main.py

Mobile Notifications Setup (Optional):
    1. Create a Firebase project at https://console.firebase.google.com
    2. Enable Realtime Database
    3. Download service account JSON from Project Settings > Service Accounts
    4. Save it as 'firebase-service-account.json' in this directory
    5. Set FIREBASE_DATABASE_URL below (or use environment variable)
    6. Install firebase-admin: pip install firebase-admin
"""

import sys
import time
import platform
import subprocess
import threading
import re
import os
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

# Firebase Configuration (Optional - for mobile notifications)
# You can set these via environment variables or edit directly here
FIREBASE_CREDENTIALS_FILE = os.environ.get(
    'FIREBASE_CREDENTIALS_FILE', 
    'firebase-service-account.json'
)
FIREBASE_DATABASE_URL = os.environ.get(
    'FIREBASE_DATABASE_URL', 
    ''  # e.g., 'https://your-project-id.firebaseio.com'
)

# Local alert sound (macOS)
BEEP_SOUND_FILE = 'BEEP.aiff'
BEEP_VOLUME = 2  # 1-10

# ============================================================================
# FIREBASE INITIALIZATION (Graceful degradation if not configured)
# ============================================================================

FIREBASE_ENABLED = False
_firebase_db = None

def _init_firebase():
    """Initialize Firebase if credentials are available. Returns True if successful."""
    global FIREBASE_ENABLED, _firebase_db
    
    # Check if firebase-admin is installed
    try:
        import firebase_admin
        from firebase_admin import credentials, db
    except ImportError:
        print("ℹ️  firebase-admin not installed - mobile notifications disabled")
        print("   To enable: pip install firebase-admin")
        return False
    
    # Check for credentials file
    if not os.path.exists(FIREBASE_CREDENTIALS_FILE):
        print(f"ℹ️  Firebase credentials not found ({FIREBASE_CREDENTIALS_FILE})")
        print("   Mobile notifications disabled")
        return False
    
    # Check for database URL
    if not FIREBASE_DATABASE_URL:
        print("ℹ️  FIREBASE_DATABASE_URL not set - mobile notifications disabled")
        print("   Set it in the script or as an environment variable")
        return False
    
    # Try to initialize
    try:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_FILE)
        firebase_admin.initialize_app(cred, {
            'databaseURL': FIREBASE_DATABASE_URL
        })
        _firebase_db = db
        FIREBASE_ENABLED = True
        print("✅ Firebase initialized - mobile notifications enabled")
        return True
    except Exception as e:
        print(f"⚠️  Firebase initialization failed: {e}")
        return False

# ============================================================================
# MOBILE NOTIFICATION
# ============================================================================

def notify_mobile(event_type: str, details: str = ""):
    """
    Send webcam event to Firebase for mobile app consumption.
    Silently does nothing if Firebase is not configured.
    
    Args:
        event_type: 'start' or 'stop'
        details: Optional additional information (e.g., log line)
    """
    if not FIREBASE_ENABLED or _firebase_db is None:
        return
    
    try:
        ref = _firebase_db.reference('webcam_events')
        event_data = {
            'type': event_type,
            'timestamp': int(time.time() * 1000),  # milliseconds for JS compatibility
            'datetime': datetime.now().isoformat(),
            'device_name': platform.node(),
            'device_os': platform.system(),
            'details': details[:500] if details else ""  # Limit details length
        }
        ref.push(event_data)
        print(f"   📱 Mobile notified: {event_type}")
    except Exception as e:
        print(f"   ⚠️  Failed to notify mobile: {e}")

# ============================================================================
# SOUND ALERT
# ============================================================================

def play_beep():
    """Play an alert sound appropriate for the current OS."""
    os_name = platform.system()
    
    if os_name == 'Windows':
        try:
            import winsound
            winsound.Beep(1000, 500)  # Frequency 1000 Hz, duration 500 ms
        except Exception as e:
            print(f"   ⚠️  Sound error: {e}")
            
    elif os_name == 'Darwin':  # macOS
        sound_file = BEEP_SOUND_FILE
        # Fallback to system sound if custom file doesn't exist
        if not os.path.exists(sound_file):
            sound_file = '/System/Library/Sounds/Ping.aiff'
        try:
            subprocess.call(['afplay', '-v', str(BEEP_VOLUME), sound_file])
        except Exception as e:
            print(f"   ⚠️  Sound error: {e}")
            
    else:  # Linux and others
        print('\a')  # Terminal bell

# ============================================================================
# WINDOWS WEBCAM MONITORING
# ============================================================================

def monitor_webcam_windows():
    """Monitor webcam access on Windows via registry polling."""
    import winreg
    
    was_in_use = False
    print("Monitoring Windows webcam registry...\n")
    
    while True:
        in_use = False
        try:
            # Check packaged apps (Microsoft Store apps)
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
                )
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        if subkey_name == "NonPackaged":
                            i += 1
                            continue
                        subkey = winreg.OpenKey(key, subkey_name)
                        try:
                            last_used_stop, _ = winreg.QueryValueEx(subkey, "LastUsedTimeStop")
                            if last_used_stop == 0:
                                in_use = True
                        except FileNotFoundError:
                            pass
                        winreg.CloseKey(subkey)
                        if in_use:
                            break
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except FileNotFoundError:
                pass

            # Check non-packaged apps (traditional desktop apps)
            if not in_use:
                try:
                    key = winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam\NonPackaged"
                    )
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkey = winreg.OpenKey(key, subkey_name)
                            try:
                                last_used_stop, _ = winreg.QueryValueEx(subkey, "LastUsedTimeStop")
                                if last_used_stop == 0:
                                    in_use = True
                            except FileNotFoundError:
                                pass
                            winreg.CloseKey(subkey)
                            if in_use:
                                break
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except FileNotFoundError:
                    pass
                    
        except Exception as e:
            print(f"Error checking registry: {e}")

        # State change detection
        if in_use and not was_in_use:
            print(f"🔴 Webcam STARTED - {datetime.now().strftime('%H:%M:%S')}")
            play_beep()
            notify_mobile('start')
        elif not in_use and was_in_use:
            print(f"⚪ Webcam STOPPED - {datetime.now().strftime('%H:%M:%S')}")
            notify_mobile('stop')
            
        was_in_use = in_use
        time.sleep(1)  # Poll every second

# ============================================================================
# MACOS WEBCAM MONITORING
# ============================================================================

def monitor_webcam_mac():
    """Monitor webcam access on macOS via system log stream."""
    command = [
        'log', 'stream', '--predicate',
        'eventMessage CONTAINS "AVCaptureSessionDidStartRunningNotification" OR '
        'eventMessage CONTAINS "AVCaptureSessionDidStopRunningNotification"'
    ]
    
    print("Streaming macOS system logs for camera events...\n")
    
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
    except Exception as e:
        print(f"❌ Failed to start log stream: {e}")
        print("   Make sure you have permission to access system logs.")
        sys.exit(1)
    
    was_in_use = False
    
    try:
        while True:
            line = process.stdout.readline()
            if not line:
                continue
                
            line = line.strip()
            
            # Filter for actual log entries (start with timestamp)
            if not re.match(r'^\d{4}-\d{2}-\d{2}', line):
                continue
            
            if "AVCaptureSessionDidStartRunningNotification" in line:
                if not was_in_use:
                    print(f"🔴 Webcam STARTED - {datetime.now().strftime('%H:%M:%S')}")
                    play_beep()
                    notify_mobile('start', line)
                was_in_use = True
                
            elif "AVCaptureSessionDidStopRunningNotification" in line:
                if was_in_use:
                    print(f"⚪ Webcam STOPPED - {datetime.now().strftime('%H:%M:%S')}")
                    notify_mobile('stop', line)
                was_in_use = False
                
    except KeyboardInterrupt:
        print("\n\nStopping monitor...")
        process.terminate()
        raise

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def print_banner():
    """Print startup banner with configuration status."""
    print()
    print("=" * 55)
    print("   📷  WEBCAM MONITOR  📷")
    print("=" * 55)
    print(f"   Platform:      {platform.system()} ({platform.release()})")
    print(f"   Device:        {platform.node()}")
    print(f"   Mobile Sync:   {'✅ Enabled' if FIREBASE_ENABLED else '❌ Disabled'}")
    print("=" * 55)
    print()
    print("Monitoring for webcam access... Press Ctrl+C to stop.")
    print()

def main():
    """Main entry point."""
    # Initialize Firebase (optional)
    _init_firebase()
    
    # Print startup info
    print_banner()
    
    # Start monitoring based on OS
    os_name = platform.system()
    
    try:
        if os_name == 'Windows':
            monitor_webcam_windows()
        elif os_name == 'Darwin':
            monitor_webcam_mac()
        else:
            print(f"❌ Unsupported operating system: {os_name}")
            print("   Supported: Windows, macOS (Darwin)")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()

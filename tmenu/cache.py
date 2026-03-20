import json
import os
from xdg_parser import load_apps

# Path in /tmp ensures it stays in RAM (tmpfs) and clears on reboot
CACHE_DIR = "/tmp/tmenu"
CACHE_FILE = os.path.join(CACHE_DIR, "apps.json")

# Standard Linux directories where .desktop files live
APP_DIRS = [
    "/usr/share/applications",
    os.path.expanduser("~/.local/share/applications")
]

def build_cache():
    """Scans system for apps using xdg_parser and saves to RAM."""
    print("[DEBUG] Building app cache...")
    apps = load_apps()
    
    # Ensure the /tmp/tmenu directory exists
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)
        
    with open(CACHE_FILE, "w") as f:
        json.dump(apps, f)
    return apps

def is_cache_stale():
    """
    Checks if the system application folders have been modified 
    since the cache file was last written.
    """
    if not os.path.exists(CACHE_FILE):
        return True
    
    try:
        cache_mtime = os.path.getmtime(CACHE_FILE)
        
        for d in APP_DIRS:
            if os.path.exists(d):
                # If the directory's modification time is newer than our cache
                if os.path.getmtime(d) > cache_mtime:
                    return True
        return False
    except OSError:
        # If there's an error accessing files, assume it's stale to be safe
        return True

def load_cache(force_refresh=False):
    """
    The main entry point: Returns the app list.
    Automatically rebuilds if the file is missing, stale, or forced.
    """
    if force_refresh or is_cache_stale():
        return build_cache()

    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        # If the file is corrupted or gone, rebuild it
        return build_cache()
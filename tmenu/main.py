#!/usr/bin/env python3
"""
TMenu - Application Menu Launcher
Main entry point
"""

import os
import sys
import signal

# 1. Hygiene Mode: Prevent Python from writing .pyc files to __pycache__
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

# 2. Path Setup: Ensure the local directory is in the path for module imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

PID_FILE = "/tmp/tmenu.pid"

# =========================================================================
# 🔥 ULTIMATE SPEED TRICK: DAEMON WAKE-UP
# We do this BEFORE importing GTK. If the daemon is running, this script
# just pings it and exits in 0.001 seconds. No heavy loading required!
# =========================================================================
if os.path.exists(PID_FILE):
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        
        # Check if the process is actually alive
        os.kill(pid, 0) 
        
        if "--quit" in sys.argv:
            os.kill(pid, signal.SIGTERM)
            print("TMenu Daemon killed.")
            sys.exit(0)
            
        elif "--refresh" in sys.argv or "--cache" in sys.argv:
            # Kill the old daemon so we can start a fresh one
            os.kill(pid, signal.SIGTERM)
            import time; time.sleep(0.2) 
            
        elif "--daemon" in sys.argv:
            print("TMenu Daemon is already running in the background.")
            sys.exit(0)
            
        else:
            # NORMAL HOTKEY PRESS: Wake up the window and exit!
            os.kill(pid, signal.SIGUSR1)
            sys.exit(0)
            
    except (ValueError, OSError):
        # The daemon crashed or isn't running. Clean up the dead file.
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

# =========================================================================
# NORMAL STARTUP (Only runs if the daemon isn't handling things)
# =========================================================================

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

# Local Imports
try:
    from tmenu.ui import TMenu
    from tmenu.daemon import run as run_daemon
    from tmenu.config import load as load_config
except ImportError:
    from ui import TMenu
    from daemon import run as run_daemon
    from config import load as load_config

def main():
    """
    Primary entry point for TMenu. 
    """
    
    # --- FLAG: --daemon (Background Service) ---
    if "--daemon" in sys.argv:
        run_daemon() # This now runs the combined UI/Cache daemon we made!
        return

    # --- FLAG: --refresh / --cache (Force Rebuild) ---
    refresh_requested = "--refresh" in sys.argv or "--cache" in sys.argv
    
    # Detect display type
    is_wayland = os.environ.get("WAYLAND_DISPLAY") is not None
    display_type = "wayland" if is_wayland else "x11"
    
    # Initialize the UI Class
    app = TMenu(force_refresh=refresh_requested)
    
    # Load config (auto-selects display-specific config)
    cfg = load_config(display_type=display_type)
    layout = cfg.get("layout", {})
    
    vertical_position = layout.get("vertical_position", "bottom")    
    horizontal_position = layout.get("horizontal_position", "left")  
    screen_margin = layout.get("screen_margin", 10)
    offset_x = layout.get("offset_x", 0)
    offset_y = layout.get("offset_y", 0)
    
    # Get primary monitor
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor()
    
    if not monitor:
        monitors = [display.get_monitor(i) for i in range(display.get_n_monitors())]
        monitor = monitors[0] if monitors else None
    
    if monitor:
        geom = monitor.get_geometry()
        
        # Calculate Y position (vertical)
        if vertical_position == "top":
            menu_y = geom.y + screen_margin + offset_y
        else:  # "bottom" (default)
            menu_y = geom.y + geom.height - app.HEIGHT - screen_margin + offset_y
        
        # Calculate X position (horizontal)
        if horizontal_position == "left":
            menu_x = geom.x + screen_margin + offset_x
        elif horizontal_position == "right":
            menu_x = geom.x + geom.width - app.WIDTH - screen_margin + offset_x
        else:  # "center" (default)
            menu_x = geom.x + (geom.width // 2) - (app.WIDTH // 2) + offset_x
        
        # Clamp to screen bounds
        menu_x = max(geom.x, min(int(menu_x), geom.x + geom.width - app.WIDTH))
        menu_y = max(geom.y, min(int(menu_y), geom.y + geom.height - app.HEIGHT))
        
        app.window.move(int(menu_x), int(menu_y))
        
        # Debug output
        print(f"DEBUG {display_type.upper()}: vertical={vertical_position} horizontal={horizontal_position} x={menu_x} y={menu_y} offset_x={offset_x} offset_y={offset_y}")
    else:
        print("DEBUG: Could not detect monitor, using default position")
        # Ultimate fallback: bottom-left
        app.window.move(screen_margin, app.HEIGHT)

    # Launch the GTK Main Loop
    app.run()

if __name__ == "__main__":
    main()

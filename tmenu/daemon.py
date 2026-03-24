import os
import sys
import signal
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

# Use relative import so main.py can find it when running as a module
try:
    from . import cache, ui
except ImportError:
    import cache
    import ui

PID_FILE = "/tmp/tmenu.pid"

def run():
    """
    Background daemon that holds the UI in memory for instant launch
    and refreshes the app cache periodically.
    Triggered by: tmenu --daemon
    """
    print("TMenu Daemon: Starting background UI and cache service...")
    
    # 1. Save PID so the hotkey script knows who to wake up
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # 2. Initial cache build
    try:
        cache.load_cache(force_refresh=True)
        print("TMenu Daemon: Initial cache build complete.")
    except Exception as e:
        print(f"TMenu Daemon Error: {e}")

    # 3. Load the UI silently into RAM (Instantly ready!)
    menu = ui.TMenu()
    menu.is_daemon = True
    menu.window.hide()

    # 4. Setup the Hotkey Trigger (Listens for SIGUSR1)
    def toggle_ui(*args):
        if menu.window.get_visible():
            menu.hide_menu()
        else:
            # Quickly grab the latest cache in case it updated in background
            menu.apps = cache.load_cache()
            menu.show_menu()
        return True

    def quit_daemon(*args):
        print("\nTMenu Daemon: Stopping...")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        menu.true_quit()

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, toggle_ui)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, quit_daemon)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, quit_daemon)

    # 5. Periodic Refresh Loop (Replaces the while True/time.sleep loop)
    def background_refresh():
        try:
            cache.load_cache(force_refresh=True)
        except Exception as e:
            print(f"TMenu Daemon Loop Error: {e}")
        return True # Returning True tells GTK to run this timer again in 5 mins

    # 300 seconds = 5 Minutes
    GLib.timeout_add_seconds(300, background_refresh)

    # 6. Start the GTK Event loop to keep everything alive
    try:
        Gtk.main()
    except KeyboardInterrupt:
        quit_daemon()

if __name__ == "__main__":
    run()

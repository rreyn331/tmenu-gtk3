import time
import sys

# Use relative import so main.py can find it when running as a module
try:
    from . import cache
except ImportError:
    import cache

def run():
    """
    Background daemon that refreshes the app cache periodically.
    Triggered by: tmenu --daemon
    """
    print("TMenu Daemon: Starting background cache service...")
    
    # 1. Initial build (happens immediately on startup)
    try:
        # Use cache.load_cache(True) to ensure it hits the rebuild logic
        cache.load_cache(force_refresh=True)
        print("TMenu Daemon: Initial cache build complete.")
    except Exception as e:
        print(f"TMenu Daemon Error: {e}")

    # 2. Periodic Refresh Loop
    # If the user ran this manually, they might want to see it's working
    # If it's in the background, it just stays silent.
    while True:
        try:
            time.sleep(300) # 5 Minutes
            cache.load_cache(force_refresh=True)
        except KeyboardInterrupt:
            print("\nTMenu Daemon: Stopping...")
            sys.exit(0)
        except Exception as e:
            print(f"TMenu Daemon Loop Error: {e}")
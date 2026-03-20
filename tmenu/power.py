import os
import subprocess
import getpass
import time

def run_cmd(cmd_list):
    """Joins commands with '||' and runs them detached."""
    full_cmd = " || ".join(cmd_list)
    # Using nohup and & so the shell stays alive to show the password prompt
    # even after the tmenu window has closed.
    os.system(f"nohup sh -c '{full_cmd}' >/dev/null 2>&1 &")

def run_logout_logic():
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    user = getpass.getuser()
    try:
        if "gnome" in de:
            subprocess.Popen(["gnome-session-quit", "--logout", "--no-prompt", "--force"])
        elif "kde" in de:
            subprocess.Popen(["qdbus", "org.kde.ksmserver", "/KSMServer", "logout", "0", "0", "0"])
        elif "xfce" in de:
            subprocess.Popen(["xfce4-session-logout", "--logout", "--fast"])
        else:
            pass
        time.sleep(2)
    except Exception:
        pass
    
    # Final logout sweep
    os.system(f"loginctl terminate-user {user} || pkill -KILL -u {user}")

def lock():
    run_cmd([
        "loginctl lock-session",
        "light-locker-command -l",
        "xdg-screensaver lock",
        "swaylock",
        "i3lock -c 000000"
    ])

def reboot():
    run_cmd([
        "systemctl reboot",
        "loginctl reboot",
        "openrc-shutdown -r now",
        "reboot",
        "pkexec reboot",      # Triggers GUI Password Prompt
        "pkexec telinit 6",   # Triggers GUI Password Prompt
        "pkexec init 6"       # The ultimate fallback
    ])

def shutdown():
    run_cmd([
        "systemctl poweroff",
        "loginctl poweroff",
        "openrc-shutdown -p now",
        "poweroff",
        "pkexec poweroff",    # Triggers GUI Password Prompt
        "pkexec telinit 0",   # Triggers GUI Password Prompt
        "pkexec init 0"       # The ultimate fallback
    ])

def hibernate():
    run_cmd([
        "systemctl hibernate",
        "loginctl hibernate",
        "pkexec pm-hibernate",
        "pkexec sh -c 'echo disk > /sys/power/state'"
    ])

def logout():
    run_logout_logic()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        action = sys.argv[1].lower()
        actions = {
            "lock": lock, 
            "reboot": reboot, 
            "shutdown": shutdown, 
            "hibernate": hibernate, 
            "logout": logout
        }
        if action in actions:
            actions[action]()

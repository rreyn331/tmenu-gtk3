#!/usr/bin/env python3
"""
TMenu Power Management
Handles system power actions (lock, shutdown, reboot, hibernate, logout)
with fallback chains for different desktop environments and init systems.
Includes safer logout progression with DE-specific termination before forceful kills.
"""

import os
import subprocess
import getpass
import time
import logging
import signal
import tempfile
import shutil
import re

logger = logging.getLogger(__name__)

# =========================================================================
# SAFE COMMAND EXECUTION
# =========================================================================

def _run_command_chain(cmd_list, use_shell=False, timeout=30, detach=False):
    """
    Execute first successful command from a list.
    
    Each command is tried in order until one succeeds (exit code 0).
    Uses subprocess (NOT os.system) for security.
    
    Args:
        cmd_list (list): List of command lists, e.g., [['cmd1'], ['cmd2']]
        use_shell (bool): If True, run through shell (required for some cmds)
        timeout (int): Max seconds to wait for command
        detach (bool): If True, run detached from parent process
        
    Returns:
        bool: True if any command succeeded
    """
    if not isinstance(cmd_list, list):
        logger.error(f"cmd_list must be list, got {type(cmd_list)}")
        return False
    
    for cmd in cmd_list:
        if not cmd:
            continue
        
        try:
            # Validate command
            if isinstance(cmd, str):
                if use_shell:
                    cmd_to_run = cmd
                else:
                    cmd_to_run = cmd.split()
            elif isinstance(cmd, list):
                if use_shell:
                    cmd_to_run = " ".join(cmd)
                else:
                    cmd_to_run = cmd
            else:
                logger.warning(f"Invalid command type: {type(cmd)}")
                continue
            
            logger.debug(f"Trying command: {cmd_to_run}")
            
            # Prepare subprocess arguments
            popen_kwargs = {
                "shell": use_shell,
                "stdin": None,
                "stdout": None,
                "stderr": None,
            }
            
            if detach:
                popen_kwargs["start_new_session"] = True
                popen_kwargs["preexec_fn"] = lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN)
            
            # Run command
            proc = subprocess.Popen(cmd_to_run, **popen_kwargs)
            
            # Wait for command with timeout
            try:
                returncode = proc.wait(timeout=timeout)
                if returncode == 0:
                    logger.info(f"Command succeeded: {cmd_to_run}")
                    return True
            except subprocess.TimeoutExpired:
                proc.kill()
                logger.warning(f"Command timeout: {cmd_to_run}")
        
        except FileNotFoundError:
            logger.debug(f"Command not found: {cmd}")
        except Exception as e:
            logger.warning(f"Error running command {cmd}: {e}")
    
    logger.error(f"All commands in chain failed: {cmd_list}")
    return False

def _run_command_detached(cmd_list, use_shell=False):
    """
    Run commands detached from parent (for logout/shutdown sequences).
    Returns immediately without waiting.
    """
    if not isinstance(cmd_list, list):
        logger.error(f"cmd_list must be list, got {type(cmd_list)}")
        return False
    
    try:
        for cmd in cmd_list:
            if not cmd:
                continue
            
            if isinstance(cmd, str):
                cmd_to_run = cmd if use_shell else cmd.split()
            elif isinstance(cmd, list):
                cmd_to_run = " ".join(cmd) if use_shell else cmd
            else:
                continue
            
            logger.debug(f"Running detached: {cmd_to_run}")
            
            subprocess.Popen(
                cmd_to_run,
                shell=use_shell,
                stdin=None,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                preexec_fn=lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN)
            )
            return True
    except Exception as e:
        logger.warning(f"Error running detached command: {e}")
    
    return False

def _validate_username(user):
    """Validate username for shell safety."""
    if not user or not isinstance(user, str):
        return False
    
    # Usernames should only contain alphanumeric, dash, underscore, dot
    if not re.match(r'^[a-zA-Z0-9._-]+$', user):
        logger.error(f"Invalid username: {user}")
        return False
    
    return True

def _command_exists(cmd):
    """Check if a command exists in PATH."""
    try:
        subprocess.run(["which", cmd], capture_output=True, timeout=2)
        return True
    except:
        return False

def _warn_and_delay(action, timeout=5):
    """
    Warn user about upcoming action with optional delay/cancellation.
    
    Args:
        action (str): Action being performed (e.g., "Reboot")
        timeout (int): Seconds before proceeding automatically
        
    Returns:
        bool: True if user confirmed, False if cancelled
    """
    msg = f"WARNING: {action} will occur in {timeout} seconds!\nPlease save your work."
    
    # Try GUI dialogs first
    if _command_exists("zenity"):
        try:
            result = subprocess.run(
                ["zenity", "--question", "--title=System Power",
                 f"--text={msg}", "--ok-label=Proceed", "--cancel-label=Cancel",
                 f"--timeout={timeout}"],
                timeout=timeout + 2,
                capture_output=True
            )
            return result.returncode == 0
        except:
            pass
    
    if _command_exists("kdialog"):
        try:
            result = subprocess.run(
                ["kdialog", "--warningcontinuecancel", msg,
                 "--title", "System Power"],
                timeout=timeout + 2,
                capture_output=True
            )
            return result.returncode == 0
        except:
            pass
    
    if _command_exists("yad"):
        try:
            result = subprocess.run(
                ["yad", "--question", "--title=System Power", f"--text={msg}",
                 "--button=Proceed:0", "--button=Cancel:1",
                 f"--timeout={timeout}", "--timeout-indicator=bottom"],
                timeout=timeout + 2,
                capture_output=True
            )
            return result.returncode == 0
        except:
            pass
    
    # Fallback: notify-send if available
    if _command_exists("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "-u", "critical", "System Power", msg],
                timeout=2,
                capture_output=True
            )
        except:
            pass
    
    logger.info(f"Waiting {timeout} seconds before {action.lower()}...")
    time.sleep(timeout)
    return True

# =========================================================================
# POWER ACTIONS
# =========================================================================

def lock():
    """
    Lock the screen with fallback methods.
    Tries: loginctl, light-locker, xdg-screensaver, swaylock, i3lock
    """
    logger.info("Locking screen...")
    
    # Check session type for optimized commands
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    
    commands = []
    
    if session_type == "wayland":
        commands.extend([
            ["swaylock"],
            ["loginctl", "lock-session"],
        ])
    elif session_type == "x11":
        commands.extend([
            ["xsecurelock"],
            ["light-locker-command", "-l"],
            ["loginctl", "lock-session"],
        ])
    
    # Generic fallbacks
    commands.extend([
        ["loginctl", "lock-session"],
        ["light-locker-command", "-l"],
        ["xdg-screensaver", "lock"],
        ["swaylock"],
        ["i3lock", "-c", "000000"],
        ["xlock"],
    ])
    
    if not _run_command_chain(commands):
        logger.error("Could not lock screen")

def reboot():
    """
    Reboot system with fallback methods and user warning.
    Tries: systemctl, loginctl, openrc, reboot, pkexec, doas, sudo
    """
    if not _warn_and_delay("Reboot", timeout=5):
        logger.info("Reboot cancelled by user")
        return
    
    logger.info("Initiating reboot...")
    
    commands = [
        ["systemctl", "reboot"],
        ["loginctl", "reboot"],
        ["openrc-shutdown", "-r", "now"],
        ["reboot"],
        ["pkexec", "systemctl", "reboot"],
        ["pkexec", "reboot"],
        ["pkexec", "telinit", "6"],
        ["pkexec", "init", "6"],
        ["doas", "reboot"],
        ["doas", "telinit", "6"],
        ["doas", "init", "6"],
        ["sudo", "reboot"],
        ["sudo", "telinit", "6"],
        ["sudo", "init", "6"],
    ]
    
    if not _run_command_chain(commands, detach=True):
        logger.error("Could not reboot")

def shutdown():
    """
    Shutdown system with fallback methods and user warning.
    Tries: systemctl, loginctl, openrc, poweroff, pkexec, doas, sudo
    """
    if not _warn_and_delay("Shutdown", timeout=5):
        logger.info("Shutdown cancelled by user")
        return
    
    logger.info("Initiating shutdown...")
    
    commands = [
        ["systemctl", "poweroff"],
        ["loginctl", "poweroff"],
        ["openrc-shutdown", "-p", "now"],
        ["poweroff"],
        ["pkexec", "systemctl", "poweroff"],
        ["pkexec", "poweroff"],
        ["pkexec", "telinit", "0"],
        ["pkexec", "init", "0"],
        ["doas", "poweroff"],
        ["doas", "telinit", "0"],
        ["doas", "init", "0"],
        ["sudo", "poweroff"],
        ["sudo", "telinit", "0"],
        ["sudo", "init", "0"],
    ]
    
    if not _run_command_chain(commands, detach=True):
        logger.error("Could not shutdown")

def suspend():
    """
    Suspend system with fallback methods and user warning.
    Tries: systemctl, loginctl, pm-utils, sysfs, doas, sudo
    """
    if not _warn_and_delay("Suspend", timeout=5):
        logger.info("Suspend cancelled by user")
        return
    
    logger.info("Initiating suspend...")
    
    commands = [
        ["systemctl", "suspend-then-hibernate"],
        ["systemctl", "hybrid-sleep"],
        ["systemctl", "suspend"],
        ["loginctl", "suspend"],
        ["loginctl", "hybrid-sleep"],
        ["pkexec", "systemctl", "suspend"],
        ["pkexec", "pm-suspend"],
        ["pkexec", "zzz"],
        ["doas", "pm-suspend"],
        ["doas", "zzz"],
        ["sudo", "pm-suspend"],
        ["sudo", "zzz"],
        ["pkexec", "sh", "-c", "echo mem > /sys/power/state"],
        ["doas", "sh", "-c", "echo mem > /sys/power/state"],
        ["sudo", "sh", "-c", "echo mem > /sys/power/state"],
    ]
    
    if not _run_command_chain(commands, detach=True):
        logger.error("Could not suspend")

def hibernate():
    """
    Hibernate system with fallback methods and user warning.
    Tries: systemctl, loginctl, pm-utils, sysfs, doas, sudo
    """
    if not _warn_and_delay("Hibernation", timeout=5):
        logger.info("Hibernation cancelled by user")
        return
    
    logger.info("Initiating hibernation...")
    
    commands = [
        ["systemctl", "hibernate"],
        ["loginctl", "hibernate"],
        ["pkexec", "systemctl", "hibernate"],
        ["pkexec", "pm-hibernate"],
        ["doas", "pm-hibernate"],
        ["sudo", "pm-hibernate"],
        ["pkexec", "sh", "-c", "echo disk > /sys/power/state"],
        ["doas", "sh", "-c", "echo disk > /sys/power/state"],
        ["sudo", "sh", "-c", "echo disk > /sys/power/state"],
    ]
    
    if not _run_command_chain(commands, detach=True, timeout=60):
        logger.error("Could not hibernate")

def logout():
    """
    Logout current user with multi-stage graceful termination.
    
    Stages:
    1. Desktop environment session logouts (GNOME, KDE, XFCE, etc.)
    2. Compositor and standalone window manager exits (Wayland/X11)
    3. Loginctl graceful session termination
    4. Last resort: kill all user processes
    """
    if not _warn_and_delay("Logout", timeout=5):
        logger.info("Logout cancelled by user")
        return
    
    logger.info("Terminating session (stage 1: DE-specific logouts)...")
    
    user = getpass.getuser()
    
    if not _validate_username(user):
        logger.error(f"Cannot logout: invalid username {user}")
        return
    
    # =====================================================================
    # STAGE 1: DESKTOP ENVIRONMENT SESSION LOGOUTS
    # =====================================================================
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    
    de_commands = []
    
    if "gnome" in de:
        de_commands.append(["gnome-session-quit", "--logout", "--no-prompt", "--force"])
    
    if "kde" in de:
        de_commands.extend([
            ["qdbus-qt6", "org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logout"],
            ["qdbus", "org.kde.ksmserver", "/KSMServer", "logout", "0", "0", "0"],
        ])
    
    if "xfce" in de:
        de_commands.append(["xfce4-session-logout", "--logout", "--fast"])
    
    if "lxqt" in de:
        de_commands.append(["lxqt-leave", "--logout"])
    
    if "lxde" in de:
        de_commands.append(["lxsession-logout"])
    
    if "cinnamon" in de:
        de_commands.append(["cinnamon-session-quit", "--logout", "--force"])
    
    if de_commands:
        _run_command_chain(de_commands, timeout=5)
    
    time.sleep(1)
    
    # =====================================================================
    # STAGE 2: COMPOSITOR & STANDALONE WM EXITS
    # =====================================================================
    logger.info("Terminating session (stage 2: compositors and window managers)...")
    
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    
    # Wayland compositors
    if session_type == "wayland":
        wayland_commands = [
            ["pkill", "-x", "sway", "-e"],
            ["swaymsg", "exit"],
            ["pkill", "-x", "wayfire", "-QUIT"],
            ["pkill", "-x", "labwc"],
            ["pkill", "-x", "kwin_wayland", "-TERM"],
        ]
        _run_command_chain(wayland_commands, timeout=3)
    
    # X11 window managers
    if session_type == "x11" or os.environ.get("DISPLAY"):
        x11_commands = [
            ["i3-msg", "exit"],
            ["openbox", "--exit"],
            ["pkill", "-x", "xfwm4", "-TERM"],
            ["pkill", "-x", "kwin", "-TERM"],
            ["pkill", "-x", "fluxbox", "-TERM"],
        ]
        _run_command_chain(x11_commands, timeout=3)
    
    time.sleep(1)
    
    # =====================================================================
    # STAGE 3: LOGINCTL GRACEFUL SESSION TERMINATION
    # =====================================================================
    logger.info("Terminating session (stage 3: loginctl graceful termination)...")
    
    loginctl_commands = [
        ["loginctl", "terminate-user", user],
        ["loginctl", "terminate-session", "auto"],
    ]
    _run_command_chain(loginctl_commands, timeout=3)
    
    time.sleep(1)
    
    # =====================================================================
    # STAGE 4: LAST RESORT - KILL ALL USER PROCESSES
    # =====================================================================
    logger.info("Terminating session (stage 4: forceful termination)...")
    
    # First, try SIGTERM (graceful)
    try:
        subprocess.run(
            ["pkill", "-u", user, "-TERM"],
            timeout=2,
            capture_output=True
        )
        time.sleep(1)
    except Exception as e:
        logger.warning(f"SIGTERM failed: {e}")
    
    # Then, if needed, use SIGKILL (forceful)
    try:
        subprocess.run(
            ["pkill", "-u", user, "-KILL"],
            timeout=2,
            capture_output=True
        )
    except Exception as e:
        logger.warning(f"SIGKILL failed: {e}")
    
    logger.info("Logout sequence complete")

# =========================================================================
# CLI INTERFACE
# =========================================================================

def show_menu():
    """Display interactive menu."""
    print("\n" + "-" * 30)
    print("     POWER MANAGEMENT")
    print("-" * 30)
    print("1) Lock")
    print("2) Logout")
    print("3) Suspend")
    print("4) Reboot")
    print("5) Shutdown")
    print("6) Hibernation")
    print("7) Cancel")
    print("-" * 30)

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    if len(sys.argv) > 1:
        action = sys.argv[1].lower()
        actions = {
            "lock": lock,
            "logout": logout,
            "suspend": suspend,
            "reboot": reboot,
            "shutdown": shutdown,
            "hibernation": hibernate,
            "hibernate": hibernate,
        }
        
        if action in actions:
            try:
                actions[action]()
            except Exception as e:
                logger.error(f"Error executing {action}: {e}")
                sys.exit(1)
        else:
            print(f"Unknown action: {action}")
            print(f"Available actions: {', '.join(sorted(actions.keys()))}")
            sys.exit(1)
    else:
        show_menu()
        try:
            choice = input("Select an action (1-7): ").strip()
        except KeyboardInterrupt:
            print("\n\nExiting...")
            sys.exit(0)
        
        actions_map = {
            "1": lock,
            "2": logout,
            "3": suspend,
            "4": reboot,
            "5": shutdown,
            "6": hibernate,
        }
        
        if choice in actions_map:
            try:
                actions_map[choice]()
            except Exception as e:
                logger.error(f"Error: {e}")
                sys.exit(1)
        else:
            print("Exiting...")
            sys.exit(0)

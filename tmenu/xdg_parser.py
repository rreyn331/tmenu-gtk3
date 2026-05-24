#!/usr/bin/env python3
"""
XDG Desktop File Parser
Safely parses .desktop files and extracts application information.
Complies with XDG Base Directory and Desktop Entry specifications.
"""

import os
import configparser
import shlex
import logging
import re

logger = logging.getLogger(__name__)

# XDG Desktop Categories
CATEGORY_MAP = {
    # Accessories
    "Utility": "Accessories",
    "TextEditor": "Accessories",
    "Archiver": "Accessories",
    "Calculator": "Accessories",
    
    # Development
    "Development": "Development",
    "IDE": "Development",
    "Debugger": "Development",
    "GUIDesigner": "Development",
    "Profiling": "Development",
    "RevisionControl": "Development",
    "Translation": "Development",
    
    # Education
    "Education": "Education",
    "Science": "Education",
    "Biology": "Education",
    "Chemistry": "Education",
    "ComputerScience": "Education",
    "DataVisualization": "Education",
    "Economics": "Education",
    "Geography": "Education",
    "Geology": "Education",
    "Geoscience": "Education",
    "History": "Education",
    "ImageProcessing": "Education",
    "Literature": "Education",
    "Maps": "Education",
    "Math": "Education",
    "MedicalSoftware": "Education",
    "Music": "Education",
    "Physics": "Education",
    "Spirituality": "Education",
    
    # Games
    "Game": "Games",
    "ActionGame": "Games",
    "AdventureGame": "Games",
    "ArcadeGame": "Games",
    "BoardGame": "Games",
    "BlocksGame": "Games",
    "CardGame": "Games",
    "KidsGame": "Games",
    "LogicGame": "Games",
    "RolePlaying": "Games",
    "Shooter": "Games",
    "Simulation": "Games",
    "SportsGame": "Games",
    "StrategyGame": "Games",
    
    # Graphics
    "Graphics": "Graphics",
    "Photography": "Graphics",
    "Scanning": "Graphics",
    "OCR": "Graphics",
    "VectorGraphics": "Graphics",
    "RasterGraphics": "Graphics",
    "3DGraphics": "Graphics",
    
    # Internet
    "Network": "Internet",
    "WebBrowser": "Internet",
    "WebDevelopment": "Internet",
    "Email": "Internet",
    "News": "Internet",
    "P2P": "Internet",
    "RemoteAccess": "Internet",
    "Telephony": "Internet",
    "TelephonyTools": "Internet",
    "VideoConference": "Internet",
    "IRCClient": "Internet",
    "Feed": "Internet",
    "FileTransfer": "Internet",
    "HamRadio": "Internet",
    "Talk": "Internet",
    
    # Multimedia
    "AudioVideo": "Multimedia",
    "Audio": "Multimedia",
    "Video": "Multimedia",
    "Midi": "Multimedia",
    "Mixer": "Multimedia",
    "Sequencer": "Multimedia",
    "TunerTV": "Multimedia",
    "AudioVideoEditing": "Multimedia",
    "Player": "Multimedia",
    "Recorder": "Multimedia",
    "DiscBurning": "Multimedia",
    
    # Office
    "Office": "Office",
    "WordProcessor": "Office",
    "Spreadsheet": "Office",
    "Presentation": "Office",
    "Publishing": "Office",
    "Database": "Office",
    "Calendar": "Office",
    "ContactManagement": "Office",
    "Dictionary": "Office",
    "Chart": "Office",
    "FlowChart": "Office",
    "Finance": "Office",
    "ProjectManagement": "Office",
    
    # Settings
    "Settings": "Settings",
    "DesktopSettings": "Settings",
    "HardwareSettings": "Settings",
    "Printing": "Settings",
    "PackageManager": "Settings",
    "Security": "Settings",
    
    # System
    "System": "System",
    "TerminalEmulator": "System",
    "FileManager": "System",
    "Monitor": "System",
    "SystemTools": "System",
    "Emulator": "System",
}

DEFAULT_CATEGORY = "Accessories"
DEFAULT_ICON = "application-x-executable"

# Core broad categories to deprioritize over specialized keys
GENERIC_CATEGORIES = {"Utility", "Development", "Education", "Game", "Graphics", "Network", "AudioVideo", "Office", "Settings", "System"}

def _resolve_app_dir(path):
    try:
        if not os.path.exists(path):
            return None
        real_path = os.path.realpath(path)
        if not os.path.isdir(real_path):
            return None
        st = os.stat(real_path)
        if st.st_mode & 0o002:  # World-writable
            logger.warning(f"Skipping world-writable dir: {real_path}")
            return None
        return real_path
    except OSError as e:
        logger.debug(f"Cannot resolve app dir {path}: {e}")
        return None

def _parse_exec_field(exec_str):
    if not exec_str:
        return ""
    try:
        cleaned = re.sub(r'\s+%[fFuUiIcCdDvVmk]', '', exec_str)
        parts = shlex.split(cleaned)
        if not parts:
            return ""
        return parts[0]
    except ValueError as e:
        logger.warning(f"Cannot parse Exec field '{exec_str}': {e}")
        return ""

def _validate_icon(icon_str):
    if not icon_str or not isinstance(icon_str, str):
        return DEFAULT_ICON
    
    icon_str = icon_str.strip()
    
    # Check if icon path is absolute or explicitly targeted
    if "/" in icon_str:
        expanded_path = os.path.expanduser(os.path.expandvars(icon_str))
        if os.path.exists(expanded_path):
            return expanded_path
        return DEFAULT_ICON
    
    if any(c in icon_str for c in ['$', '`', ';', '&', '|']):
        logger.warning(f"Icon has suspicious characters: {icon_str}")
        return DEFAULT_ICON
    
    return icon_str or DEFAULT_ICON

def _validate_name(name_str):
    if not name_str or not isinstance(name_str, str):
        return None
    name = name_str.strip()
    if not name:
        return None
    if len(name) > 256:
        logger.warning(f"App name too long: {name[:50]}...")
        return None
    if '\0' in name:
        logger.warning("App name contains null bytes")
        return None
    return name

def parse_desktop_file(path):
    if not path or not isinstance(path, str) or not path.endswith('.desktop'):
        return None
    
    if not os.path.isfile(path):
        return None

    content = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        logger.debug(f"Could not read desktop file content {path}: {e}")
        return None

    # Standardize headers to resolve duplicate or malformed [Desktop Entry] lines
    content = re.sub(r'(\[Desktop Entry\]\s*)+', '[Desktop Entry]\n', content, flags=re.IGNORECASE)

    try:
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        cp.read_string(content)
        
        if "Desktop Entry" not in cp:
            logger.debug(f"No [Desktop Entry] section in {path}")
            return None
        
        entry = cp["Desktop Entry"]
        
        if entry.get("NoDisplay", "").lower() == "true":
            logger.debug(f"App marked NoDisplay: {path}")
            return None
        
        if entry.get("Hidden", "").lower() == "true":
            logger.debug(f"App marked Hidden: {path}")
            return None
        
        name = _validate_name(entry.get("Name", ""))
        if not name:
            logger.warning(f"Invalid or missing Name in {path}")
            return None
        
        exec_raw = entry.get("Exec", "")
        exec_cmd = _parse_exec_field(exec_raw)
        if not exec_cmd:
            logger.warning(f"Invalid or missing Exec in {path}")
            return None
        
        raw_cats = entry.get("Categories", "").split(";")
        
        # Scrape categories to prioritize precision matching over rough umbrella terms
        candidate_cat = None
        for cat in raw_cats:
            cat = cat.strip()
            if cat in CATEGORY_MAP:
                candidate_cat = CATEGORY_MAP[cat]
                if cat not in GENERIC_CATEGORIES:
                    break
                    
        mapped_cat = candidate_cat if candidate_cat else DEFAULT_CATEGORY
        icon = _validate_icon(entry.get("Icon", ""))
        
        return {
            "Name": name,
            "Exec": exec_cmd,
            "Icon": icon,
            "Categories": mapped_cat,
            "Path": path,
        }
    
    except configparser.Error as e:
        logger.warning(f"Parse error in {path} managed via configparser: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing {path}: {e}", exc_info=True)
        return None

def _get_app_dirs():
    dirs = []
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        user_apps = os.path.join(xdg_data_home, "applications")
    else:
        user_apps = os.path.expanduser("~/.local/share/applications")
    
    xdg_data_dirs = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    system_apps = [os.path.join(d, "applications") for d in xdg_data_dirs.split(":")]
    
    for d in [user_apps] + system_apps:
        resolved = _resolve_app_dir(d)
        if resolved and resolved not in dirs:
            dirs.append(resolved)
            logger.debug(f"Using app dir: {resolved}")
    
    return dirs

def load_apps():
    apps = []
    seen = set()  # (Name, Exec) -> prevent duplicates
    dirs = _get_app_dirs()
    
    if not dirs:
        logger.warning("No application directories found")
        return apps
    
    for d in dirs:
        try:
            for f in os.listdir(d):
                if not f.endswith(".desktop"):
                    continue
                
                fpath = os.path.join(d, f)
                try:
                    app = parse_desktop_file(fpath)
                    if not app:
                        continue
                    
                    key = (app["Name"], app["Exec"])
                    if key not in seen:
                        apps.append(app)
                        seen.add(key)
                except Exception as e:
                    logger.debug(f"Error processing {fpath}: {e}")
        except OSError as e:
            logger.warning(f"Cannot read app dir {d}: {e}")
    
    apps.sort(key=lambda x: x["Name"].lower())
    logger.info(f"Loaded {len(apps)} applications from {len(dirs)} directories")
    return apps

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    apps = load_apps()
    print(f"\nLoaded {len(apps)} apps:\n")
    
    by_cat = {}
    for app in apps:
        cat = app["Categories"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(app["Name"])
    
    for cat in sorted(by_cat.keys()):
        print(f"{cat}: {len(by_cat[cat])} apps")
        for name in by_cat[cat][:3]:
            print(f"  - {name}")
        if len(by_cat[cat]) > 3:
            print(f"  ... and {len(by_cat[cat]) - 3} more")
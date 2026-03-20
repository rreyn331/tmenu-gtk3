import os
import configparser
import shlex

# This MUST match the keys in ui.py exactly
CATEGORY_MAP = {
    "Utility": "Accessories", "TextEditor": "Accessories", 
    "Development": "Development", "IDE": "Development",
    "Education": "Education", "Science": "Education",
    "Game": "Games",
    "Graphics": "Graphics", "Photography": "Graphics",
    "Network": "Internet", "WebBrowser": "Internet",
    "AudioVideo": "Multimedia", "Audio": "Multimedia", "Video": "Multimedia",
    "Office": "Office",
    "Settings": "Settings", "DesktopSettings": "Settings",
    "System": "System", "TerminalEmulator": "System"
}

def parse_desktop_file(path):
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(path)
        if "Desktop Entry" not in cp: return None
        entry = cp["Desktop Entry"]
        
        if entry.get("NoDisplay") == "true" or entry.get("Hidden") == "true":
            return None
        
        # Extract categories
        raw_cats = entry.get("Categories", "").split(";")
        mapped_cat = "Accessories" # Default fallback
        
        for c in raw_cats:
            c = c.strip()
            if c in CATEGORY_MAP:
                mapped_cat = CATEGORY_MAP[c]
                break
        
        return {
            "Name": entry.get("Name", "Unknown"),
            "Exec": entry.get("Exec", "").split(" %")[0],
            "Icon": entry.get("Icon", "application-x-executable"),
            "Categories": mapped_cat
        }
    except Exception as e:
        return None

def load_apps():
    apps = []
    seen = set()
    dirs = [
        os.path.expanduser("~/.local/share/applications"), 
        "/usr/share/applications",
        "/usr/local/share/applications"
    ]
    for d in dirs:
        if not os.path.exists(d): continue
        for f in os.listdir(d):
            if f.endswith(".desktop"):
                app = parse_desktop_file(os.path.join(d, f))
                if app and app["Name"] not in seen:
                    apps.append(app)
                    seen.add(app["Name"])
    
    print(f"DEBUG: Loaded {len(apps)} apps.")
    return sorted(apps, key=lambda x: x["Name"].lower())
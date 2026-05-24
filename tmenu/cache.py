#!/usr/bin/env python3
import json
import os
import logging

from xdg_parser import load_apps

logger = logging.getLogger(__name__)


def _get_cache_dir():
    xdg_cache_home = os.environ.get(
        "XDG_CACHE_HOME",
        os.path.expanduser("~/.cache"),
    )
    return os.path.join(xdg_cache_home, "tmenu")


CACHE_DIR = _get_cache_dir()
CACHE_FILE = os.path.join(CACHE_DIR, "apps.json")


def _desktop_search_dirs():
    dirs = []

    xdg_data_home = os.environ.get(
        "XDG_DATA_HOME",
        os.path.expanduser("~/.local/share"),
    )
    dirs.append(os.path.join(xdg_data_home, "applications"))

    xdg_data_dirs = os.environ.get(
        "XDG_DATA_DIRS",
        "/usr/local/share:/usr/share",
    )

    for base in xdg_data_dirs.split(":"):
        if base:
            dirs.append(os.path.join(base, "applications"))

    dirs.extend(
        [
            os.path.expanduser("~/.local/share/applications"),
            "/usr/local/share/applications",
            "/usr/share/applications",
        ]
    )

    result = []
    seen = set()

    for d in dirs:
        d = os.path.abspath(os.path.expanduser(os.path.expandvars(d)))

        if d not in seen:
            seen.add(d)
            result.append(d)

    return result


APP_DIRS = _desktop_search_dirs()


def _validate_cache_dir(path):
    if os.path.islink(path):
        raise RuntimeError(f"Cache directory is a symlink: {path}")

    if os.path.exists(path):
        st = os.stat(path)

        if st.st_uid != os.getuid():
            raise RuntimeError("Cache directory not owned by current user")

        if st.st_mode & 0o077:
            logger.warning("Cache directory has unsafe permissions, fixing...")
            os.chmod(path, 0o700)


def _ensure_cache_dir():
    try:
        os.makedirs(CACHE_DIR, mode=0o700, exist_ok=True)
        _validate_cache_dir(CACHE_DIR)
    except OSError as e:
        raise RuntimeError(f"Cannot create cache directory {CACHE_DIR}: {e}")


def _parse_desktop_file_simple(path):
    data = {}
    in_desktop_entry = False

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()

                if not line or line.startswith("#"):
                    continue

                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip()
                    if section == "Desktop Entry":
                        in_desktop_entry = True
                    else:
                        if data:  
                            continue
                        in_desktop_entry = False
                    continue

                if not in_desktop_entry:
                    continue

                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if key not in data:
                    data[key] = value

    except Exception as e:
        logger.debug(f"Could not parse desktop file {path}: {e}")
        return None

    if not data:
        return None

    data["_desktop_file_path"] = path
    data["_desktop_file_id"] = os.path.basename(path)

    return data


def _load_desktop_entries():
    entries = []
    seen_paths = set()

    for directory in APP_DIRS:
        if not os.path.isdir(directory):
            continue

        for root, dirs, files in os.walk(directory):
            for filename in files:
                if not filename.endswith(".desktop"):
                    continue

                path = os.path.join(root, filename)
                if path in seen_paths:
                    continue
                
                parsed = _parse_desktop_file_simple(path)

                if parsed:
                    entries.append(parsed)
                    seen_paths.add(path)

    return entries


def _possible_desktop_ids(app):
    ids = []

    for key in [
        "DesktopFile",
        "DesktopFileID",
        "desktop_file",
        "desktop_id",
        "Id",
        "ID",
        "File",
        "Filename",
        "filename",
        "_desktop_file_id",
        "_desktop_file_path",
    ]:
        value = app.get(key)

        if not value:
            continue

        value = str(value)
        ids.append(value)
        ids.append(os.path.basename(value))

        if not value.endswith(".desktop"):
            ids.append(value + ".desktop")

    return list(dict.fromkeys(ids))


def _desktop_entry_match_score(entry, app):
    score = 0

    app_name = str(app.get("Name", "")).strip()
    app_exec = str(app.get("Exec", "")).strip()

    entry_name = str(entry.get("Name", "")).strip()
    entry_exec = str(entry.get("Exec", "")).strip()

    entry_id = entry.get("_desktop_file_id", "")
    entry_path = entry.get("_desktop_file_path", "")

    possible_ids = _possible_desktop_ids(app)

    for item in possible_ids:
        if item == entry_path:
            score += 100

        if item == entry_id:
            score += 90

        if item == os.path.basename(entry_path):
            score += 90

    if app_name and entry_name and app_name == entry_name:
        score += 50

    if app_name and entry_name and app_name.lower() == entry_name.lower():
        score += 40

    if app_exec and entry_exec and app_exec == entry_exec:
        score += 50

    if app_name and entry_name and app_exec and entry_exec:
        if app_name == entry_name and app_exec == entry_exec:
            score += 100

    return score


def _find_matching_desktop_entry(app, entries):
    best_entry = None
    best_score = 0

    for entry in entries:
        score = _desktop_entry_match_score(entry, app)

        if score > best_score:
            best_score = score
            best_entry = entry

    if best_score >= 40:
        return best_entry

    return None


def _normalize_icon(icon):
    if not icon:
        return "application-x-executable"

    icon = str(icon).strip().strip('"').strip("'")

    if not icon:
        return "application-x-executable"

    expanded = os.path.expanduser(os.path.expandvars(icon))

    if os.path.isabs(expanded):
        if os.path.isfile(expanded):
            return expanded

        logger.warning(f"Icon path does not exist, using default: {expanded}")
        return "application-x-executable"

    return icon


def _normalize_categories(categories):
    """Ensures categories always format to a clean, well-tokenized array list."""
    if not categories:
        return ["Other"]

    # Explicit cross-translation from standard Linux XDG strings to valid ui.py keys
    translation_map = {
        "audiovideo": "Multimedia",
        "audio": "Multimedia",
        "video": "Multimedia",
        "utility": "Accessories",
        "utilities": "Accessories",
        "development": "Development",
        "building": "Development",
        "ide": "Development",
        "education": "Education",
        "game": "Games",
        "games": "Games",
        "graphics": "Graphics",
        "network": "Internet",
        "internet": "Internet",
        "webbrowser": "Internet",
        "office": "Office",
        "settings": "Settings",
        "preferences": "Settings",
        "system": "System",
        "monitor": "System",
    }

    # Strict UI alignment tracking list 
    valid_ui_categories = {
        "Accessories", "Development", "Education", "Games", 
        "Graphics", "Internet", "Multimedia", "Office", "Settings", "System"
    }

    raw_list = []
    if isinstance(categories, list):
        raw_list = [str(c) for c in categories if c]
    elif isinstance(categories, str):
        delimiters = [';', ',']
        work_str = categories
        for d in delimiters:
            work_str = work_str.replace(d, ';')
        raw_list = [c.strip() for c in work_str.split(';') if c.strip()]

    processed = []
    for cat in raw_list:
        clean = cat.strip()
        lowered = clean.lower()
        
        if lowered in translation_map:
            processed.append(translation_map[lowered])
        else:
            capitalized = clean.capitalize() if len(clean) > 1 else clean
            if capitalized in valid_ui_categories:
                processed.append(capitalized)

    # Clean and deduplicate parsed elements
    final_categories = list(dict.fromkeys(processed))
    
    # Fallback to "Other" if categories list parsed down into nothing valid
    return final_categories if final_categories else ["Other"]


def _enrich_apps_from_desktop_files(apps):
    entries = _load_desktop_entries()

    if not entries:
        return apps

    enriched = []
    seen_unique_apps = set()

    for app in apps:
        if not isinstance(app, dict):
            enriched.append(app)
            continue

        match = _find_matching_desktop_entry(app, entries)

        if match:
            if match.get("Exec"):
                app["Exec"] = match.get("Exec")

            if "Icon" in match:
                app["Icon"] = _normalize_icon(match.get("Icon"))
            else:
                app["Icon"] = _normalize_icon(app.get("Icon"))

            if "Terminal" in match:
                app["Terminal"] = match.get("Terminal")

            if "Path" in match:
                app["Path"] = match.get("Path")

            if "Categories" in match:
                app["Categories"] = _normalize_categories(match.get("Categories"))
            else:
                app["Categories"] = _normalize_categories(app.get("Categories"))

            app["_desktop_file_path"] = match.get("_desktop_file_path")
            app["_desktop_file_id"] = match.get("_desktop_file_id")

        else:
            app["Icon"] = _normalize_icon(app.get("Icon"))
            app["Categories"] = _normalize_categories(app.get("Categories"))

        app_signature = f"{app.get('Name')}||{app.get('Exec')}"
        if app_signature not in seen_unique_apps:
            seen_unique_apps.add(app_signature)
            enriched.append(app)

    for entry in entries:
        entry_signature = f"{entry.get('Name')}||{entry.get('Exec')}"
        if entry_signature not in seen_unique_apps and entry.get("Name") and entry.get("Exec"):
            if entry.get("NoDisplay") == "true" or entry.get("Hidden") == "true":
                continue
            
            seen_unique_apps.add(entry_signature)
            standalone_app = {
                "Name": entry.get("Name"),
                "Exec": entry.get("Exec"),
                "Icon": _normalize_icon(entry.get("Icon")),
                "Categories": _normalize_categories(entry.get("Categories")),
                "_desktop_file_path": entry.get("_desktop_file_path"),
                "_desktop_file_id": entry.get("_desktop_file_id")
            }
            enriched.append(standalone_app)

    return enriched


def build_cache():
    logger.debug("Building app cache...")

    try:
        apps = load_apps()

        if not isinstance(apps, list):
            logger.warning(f"load_apps() returned an invalid type: {type(apps)}. Creating manual list.")
            apps = []

        apps = _enrich_apps_from_desktop_files(apps)

        _ensure_cache_dir()

        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(apps, f, indent=2, ensure_ascii=False)

        logger.debug(f"Cached {len(apps)} apps to {CACHE_FILE}")
        return apps

    except Exception as e:
        logger.error(f"Failed to build cache: {e}")
        raise


def _latest_desktop_mtime():
    latest = 0

    for directory in APP_DIRS:
        if not os.path.isdir(directory):
            continue

        try:
            for root, dirs, files in os.walk(directory):
                for filename in files:
                    if not filename.endswith(".desktop"):
                        continue

                    path = os.path.join(root, filename)

                    try:
                        latest = max(latest, os.path.getmtime(path))
                    except OSError:
                        continue

        except OSError:
            continue

    return latest


def is_cache_stale():
    if not os.path.exists(CACHE_FILE):
        logger.debug("Cache file not found, marking as stale")
        return True

    try:
        cache_mtime = os.path.getmtime(CACHE_FILE)
        desktop_mtime = _latest_desktop_mtime()

        if desktop_mtime > cache_mtime:
            logger.debug("Desktop files modified after cache, marking as stale")
            return True

        logger.debug("Cache is fresh")
        return False

    except OSError as e:
        logger.warning(f"Error checking cache staleness: {e}, marking as stale")
        return True


def load_cache(force_refresh=False):
    if force_refresh:
        logger.info("Force refresh requested, rebuilding cache...")
        return build_cache()

    if is_cache_stale():
        logger.info("Cache is stale, rebuilding...")
        return build_cache()

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            apps = json.load(f)

        if not isinstance(apps, list):
            raise ValueError(f"Cache must contain a list, got {type(apps)}")

        logger.debug(f"Loaded {len(apps)} apps from cache")
        return apps

    except FileNotFoundError:
        logger.info("Cache file not found, rebuilding...")
        return build_cache()

    except json.JSONDecodeError as e:
        logger.error(f"Cache file corrupted: {e}")
        logger.info("Rebuilding cache...")
        return build_cache()

    except (IOError, OSError) as e:
        logger.error(f"Failed to read cache: {e}")
        logger.info("Rebuilding cache...")
        return build_cache()
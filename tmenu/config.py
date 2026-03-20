#!/usr/bin/env python3
"""
TMenu Configuration Loader
Handles loading and validation of user config files with detailed comments
"""

import os
import json
from pathlib import Path

# Default configuration with detailed explanations
DEFAULT_CONFIG = {
    "layout": {
        "vertical_position": "bottom",      # "top" or "bottom" - where menu appears vertically
        "horizontal_position": "left",      # "left", "center", or "right" - where menu appears horizontally
        "screen_margin": 10,                # Pixels from screen edge to menu edge
        "offset_x": 0,                      # HORIZONTAL fine-tuning: positive = RIGHT, negative = LEFT
        "offset_y": 0,                      # VERTICAL fine-tuning: positive = DOWN, negative = UP
    },
    "theme": {
        "icon_size": 48,                    # Icon size in pixels
        "font_size": 10,                    # Font size
        "dark_mode": True,                  # Use dark theme
    },
    "sidebar_width": 180,                   # Width of sidebar in pixels
    "search": {
        "enabled": True,
        "placeholder": "Search applications...",
    },
    "power_buttons": [
        {
            "label": "Shutdown",
            "command": "systemctl poweroff",
            "icon": "system-shutdown"
        },
        {
            "label": "Reboot",
            "command": "systemctl reboot",
            "icon": "system-reboot"
        },
        {
            "label": "Lock",
            "command": "loginctl lock-session",
            "icon": "system-lock-screen"
        }
    ]
}

def get_config_dir():
    """Get the config directory path"""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if not config_home:
        config_home = os.path.expanduser("~/.config")
    
    config_dir = os.path.join(config_home, "tmenu")
    return config_dir

def ensure_config_exists():
    """Create config directory and default config if they don't exist"""
    config_dir = get_config_dir()
    
    # Create directory if it doesn't exist
    os.makedirs(config_dir, exist_ok=True)
    
    # Create default config file if it doesn't exist
    config_file = os.path.join(config_dir, "config.json")
    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"✓ Created default config at: {config_file}")
        print_config_help()
    
    return config_dir

def load(display_type="x11"):
    """
    Load configuration from user's config directory
    
    Priority order:
    1. ~/.config/tmenu/config-{display_type}.json (e.g., config-x11.json)
    2. ~/.config/tmenu/config.json (universal config)
    3. Default config (hardcoded fallback)
    
    Args:
        display_type (str): "x11" or "wayland"
    
    Returns:
        dict: Merged configuration
    """
    
    config_dir = ensure_config_exists()
    config = DEFAULT_CONFIG.copy()
    
    # Load universal config
    universal_config_file = os.path.join(config_dir, "config.json")
    if os.path.exists(universal_config_file):
        try:
            with open(universal_config_file, 'r') as f:
                user_config = json.load(f)
                config.update(user_config)
                print(f"✓ Loaded universal config: {universal_config_file}")
        except json.JSONDecodeError as e:
            print(f"⚠ Error parsing {universal_config_file}: {e}")
    
    # Load display-specific config (overrides universal)
    display_config_file = os.path.join(config_dir, f"config-{display_type}.json")
    if os.path.exists(display_config_file):
        try:
            with open(display_config_file, 'r') as f:
                display_config = json.load(f)
                # Deep merge layout settings
                if "layout" in display_config:
                    config["layout"].update(display_config["layout"])
                # Update other settings
                for key in display_config:
                    if key != "layout":
                        config[key] = display_config[key]
                print(f"✓ Loaded {display_type.upper()} config: {display_config_file}")
        except json.JSONDecodeError as e:
            print(f"⚠ Error parsing {display_config_file}: {e}")
    
    return config

def print_config_help():
    """Print helpful information about config file structure"""
    help_text = """
╔════════════════════════════════════════════════════════════════════════════╗
║                        TMenu Configuration Guide                           ║
╚════════════════════════════════════════════════════════════════════════════╝

📁 CONFIG LOCATION:
   ~/.config/tmenu/config.json              (Universal settings)
   ~/.config/tmenu/config-x11.json          (X11-specific overrides)
   ~/.config/tmenu/config-wayland.json      (Wayland-specific overrides)

📐 LAYOUT POSITIONING GUIDE:

   VERTICAL POSITION (vertical_position):
   ┌─────────────────────────────────────┐
   │ "top"                               │  ← Menu appears here
   │                                     │
   │                                     │
   │                                     │
   │                                     │
   │ "bottom"                            │
   └─────────────────────────────────────┘
                                            ↑ Menu appears here

   HORIZONTAL POSITION (horizontal_position):
   ┌──────────────────────────────────────┐
   │ "left"  "center"  "right"            │
   │  ↑       ↑         ↑                  │
   │  │       │         │                  │
   │  └───────┼─────────┘                  │
   └──────────────────────────────────────┘

   OFFSET VALUES (Fine-tuning adjustments):
   offset_x:  positive (+) = move RIGHT
              negative (-) = move LEFT
              Example: offset_x: 50   (move 50px to the right)
              Example: offset_x: -30  (move 30px to the left)
   
   offset_y:  positive (+) = move DOWN
              negative (-) = move UP
              Example: offset_y: 100  (move 100px down)
              Example: offset_y: -50  (move 50px up)

📝 EXAMPLE CONFIG (config-x11.json):

{
  "layout": {
    "vertical_position": "bottom",
    "horizontal_position": "left",
    "screen_margin": 10,
    "offset_x": 0,
    "offset_y": -100
  },
  "theme": {
    "icon_size": 48,
    "font_size": 10,
    "dark_mode": true
  },
  "sidebar_width": 180,
  "search": {
    "enabled": true,
    "placeholder": "Search applications..."
  },
  "power_buttons": [
    {
      "label": "Shutdown",
      "command": "systemctl poweroff",
      "icon": "system-shutdown"
    },
    {
      "label": "Reboot",
      "command": "systemctl reboot",
      "icon": "system-reboot"
    }
  ]
}

🎯 POSITIONING EXAMPLES:

1. Bottom-left corner, 50px from edges:
   {
     "layout": {
       "vertical_position": "bottom",
       "horizontal_position": "left",
       "screen_margin": 50,
       "offset_x": 0,
       "offset_y": 0
     }
   }

2. Top-right corner, 100px up from top:
   {
     "layout": {
       "vertical_position": "top",
       "horizontal_position": "right",
       "screen_margin": 10,
       "offset_x": 0,
       "offset_y": 0
     }
   }

3. Center-bottom, but move up 150px:
   {
     "layout": {
       "vertical_position": "bottom",
       "horizontal_position": "center",
       "screen_margin": 10,
       "offset_x": 0,
       "offset_y": -150
     }
   }

4. Bottom-left, shifted 100px right and 50px up:
   {
     "layout": {
       "vertical_position": "bottom",
       "horizontal_position": "left",
       "screen_margin": 10,
       "offset_x": 100,
       "offset_y": -50
     }
   }

💡 TIPS:
   • After editing config, restart TMenu to apply changes
   • Use --refresh flag to clear cache: tmenu --refresh
   • Check debug output: shows actual x, y coordinates
   • screen_margin applies FIRST, then offsets adjust from there
   • Display-specific configs override universal settings

"""
    print(help_text)

if __name__ == "__main__":
    print_config_help()
    config = load(display_type="x11")
    print("\nLoaded config:")
    print(json.dumps(config, indent=2))

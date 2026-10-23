"""Settings storage in ~/.config/legion-control (migrated from the old config.json next to the script)."""
import json
import logging
import os
import shutil

log = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "legion-control")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "legion-control")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
SYSINFO_CACHE = os.path.join(CACHE_DIR, "sys_info.json")

DEFAULT_PROFILE = {"effect": "static", "brightness": "Low", "speed": 2, "wave_direction": "LTR",
                   "colors": ["39c5bb"] * 4}

DEFAULTS = {
    "theme": "Miku",
    "live_preview": True,
    "current_profile": "Default",
    "color_history": [],
    "pref_blink_opposite": False,
    "pref_solo_mode": False,
    "pref_batt_low": 15,
    "pref_batt_green": 75,
    "pref_batt_full": 95,
    "profiles": {"Default": dict(DEFAULT_PROFILE)},
    "home_assistant": {
        "enabled": False,
        "url": "",            # e.g. http://100.64.167.103:8123
        "token": "",          # long-lived access token
        "listen": "",         # address for commands from HA, e.g. the Tailscale IP; empty = no commands
        "port": 47125,
        "command_token": "",  # HA sends this as a Bearer token
    },
}


def load(app_dir):
    """Load settings, migrating <app_dir>/config.json and sys_info_cache.json the first time."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    legacy = os.path.join(app_dir, "config.json")
    if not os.path.exists(CONFIG_PATH) and os.path.exists(legacy):
        shutil.copy2(legacy, CONFIG_PATH)
        log.info("Migrated settings from %s", legacy)
    legacy_cache = os.path.join(app_dir, "sys_info_cache.json")
    if not os.path.exists(SYSINFO_CACHE) and os.path.exists(legacy_cache):
        shutil.copy2(legacy_cache, SYSINFO_CACHE)

    data = {}
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError) as e:
        log.error("Could not read %s (%s); starting from defaults", CONFIG_PATH, e)

    merged = json.loads(json.dumps(DEFAULTS))
    merged.update({k: v for k, v in data.items() if k in DEFAULTS and k != "home_assistant"})
    merged["home_assistant"].update(data.get("home_assistant", {}))
    # The old app padded history with "#333333" placeholders
    merged["color_history"] = [c for c in merged["color_history"] if c.lower() not in ("#333333", "#000000")][:12]
    if not merged["profiles"]:
        merged["profiles"] = {"Default": dict(DEFAULT_PROFILE)}
    return merged


def save(data):
    """Write atomically, so a crash mid-write can't corrupt the file. The file may hold an HA token: 0600."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, CONFIG_PATH)


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=1)
    except OSError as e:
        log.warning("Could not write %s: %s", path, e)

from pathlib import Path
from platformdirs import user_config_path, user_data_path
import json

APP_NAME = "tui-rhythm-game"

# bundled songs live inside the package, user songs mirror the same beatmaps/ + assets/ layout
PACKAGE_DIR = Path(__file__).parent
USER_DIR = user_data_path(APP_NAME, appauthor=False)
SETTINGS_PATH = user_config_path(APP_NAME, appauthor=False) / "settings.json"

SPEED_MIN = 5.0
SPEED_MAX = 15.0
SPEED_STEP = 0.5

DEFAULTS = {
    "theme": "nord",
    "speed": 12.0,
    "lane_keys": ["d", "f", "j", "k"],
}

def ensure_user_dirs() -> None:
    (USER_DIR / "beatmaps").mkdir(parents=True, exist_ok=True)
    (USER_DIR / "assets").mkdir(parents=True, exist_ok=True)

def load_settings() -> dict:
    settings = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, 'r') as file:
            saved = json.load(file)
    except (OSError, ValueError):
        return settings

    # only keep saved values that are still valid
    if isinstance(saved.get("theme"), str):
        settings["theme"] = saved["theme"]
    if isinstance(saved.get("speed"), (int, float)):
        settings["speed"] = min(max(float(saved["speed"]), SPEED_MIN), SPEED_MAX)
    keys = saved.get("lane_keys")
    if isinstance(keys, list) and len(keys) == 4 and len(set(keys)) == 4 and all(isinstance(k, str) for k in keys):
        settings["lane_keys"] = keys
    return settings

def save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, 'w') as file:
        json.dump(settings, file, indent=1)

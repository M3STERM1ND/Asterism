"""Settings saved between runs in settings.json: difficulty, assisted learning, and battles won
(which unlocks spells). A missing or damaged file just means the defaults."""
import json
from dataclasses import asdict, dataclass

from game.difficulty import NORMAL, by_name

SETTINGS_PATH = "settings.json"


@dataclass
class Settings:
    difficulty: str = NORMAL.name
    assisted: bool = True
    battles_won: int = 0


def load_settings(path=SETTINGS_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return Settings(difficulty=by_name(data.get("difficulty")).name,
                        assisted=bool(data.get("assisted", True)),
                        battles_won=max(0, int(data.get("battles_won", 0))))
    except (OSError, ValueError, TypeError, AttributeError):
        return Settings()


def save_settings(settings, path=SETTINGS_PATH):
    """Write the settings; a file that can't be written must not stop the game."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, indent=2)
        return True
    except OSError as error:
        print(f"Settings: could not write {path}: {error}")
        return False

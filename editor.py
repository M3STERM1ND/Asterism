"""Editor: the therapist crafts a constellation by clicking stars onto the sky (start screen key E).

Click to place 4 to 8 stars in the order the player will draw them (right-click or Backspace removes
the last one, X clears). N names it: type, Enter to keep, Esc to cancel. S saves it as JSON in
constellations/, in the same form as the built-in files: positions scaled so the longer side spans
0 to 1, keeping their shape, so the game can fit it to any player's reach. Saved constellations join
the practice list after the zodiac.
"""
import json
import os
import re

MIN_STARS, MAX_STARS = 4, 8
MIN_GAP_PX = 40         # a click this close to a placed star is ignored, so two stars never sit on top of each other
MAX_NAME = 24
NAME_CHARS = re.compile(r"[A-Za-z0-9 '\-]")
MESSAGE_SECONDS = 3.0
FOLDER = "constellations"
ENTER, ESCAPE, BACKSPACE = 13, 27, 8


def normalize(points):
    """Pixel positions to the file's 0-to-1 form: shifted to the top-left and scaled by the longer side."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    return [[round((x - min(xs)) / span, 3), round((y - min(ys)) / span, 3)] for x, y in points]


def slug(name):
    """A safe file name for a constellation name: 'Little Bear' -> 'little_bear'."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class Editor:
    def __init__(self, canvas, protected=(), folder=FOLDER):
        """canvas: (left, top, right, bottom) in pixels where stars can go.
        protected: file names (without .json) that must never be overwritten, the built-in constellations."""
        self.canvas = canvas
        self.protected = set(protected)
        self.folder = folder
        self.stars = []         # placed stars in pixels, in drawing order
        self.name = ""
        self.typing = None      # the name being typed, or None when not naming
        self.message = ("", None, 0.0)  # (text, ok?, time shown)

    def say(self, text, ok, now):
        self.message = (text, ok, now)

    def click(self, x, y, now):
        """Place a star at a left click, if there is room and it is inside the canvas."""
        left, top, right, bottom = self.canvas
        if not (left <= x <= right and top <= y <= bottom):
            return
        if len(self.stars) >= MAX_STARS:
            self.say(f"{MAX_STARS} stars is the most: Backspace removes the last one", False, now)
            return
        if any(abs(x - sx) < MIN_GAP_PX and abs(y - sy) < MIN_GAP_PX for sx, sy in self.stars):
            self.say("Too close to another star", False, now)
            return
        self.stars = self.stars + [(x, y)]

    def undo(self):
        self.stars = self.stars[:-1]

    def handle_key(self, key, now):
        """Typing a name, or the editor keys N, S, X and Backspace."""
        if self.typing is not None:
            self.type_key(key)
        elif key == ord("n"):
            self.typing = self.name
        elif key == ord("s"):
            self.save(now)
        elif key == ord("x"):
            self.stars = []
        elif key == BACKSPACE:
            self.undo()

    def type_key(self, key):
        """One key while naming: letters and digits add, Backspace deletes, Enter keeps, Esc cancels."""
        if key == ENTER:
            self.name, self.typing = " ".join(self.typing.split()), None
        elif key == ESCAPE:
            self.typing = None
        elif key == BACKSPACE:
            self.typing = self.typing[:-1]
        elif 32 <= key < 127 and NAME_CHARS.fullmatch(chr(key)) and len(self.typing) < MAX_NAME:
            self.typing += chr(key)

    def problem(self):
        """Why the constellation can't be saved yet, or None if it can."""
        if len(self.stars) < MIN_STARS:
            return f"Place at least {MIN_STARS} stars ({len(self.stars)} so far)"
        if not slug(self.name):
            return "Press N to give it a name"
        if slug(self.name) in self.protected:
            return f"{self.name} is a built-in constellation: choose another name"
        return None

    def save(self, now):
        """Write constellations/<name>.json; returns the path, or None if it couldn't be saved."""
        problem = self.problem()
        if problem:
            self.say(problem, False, now)
            return None
        path = os.path.join(self.folder, f"{slug(self.name)}.json")
        data = {"name": self.name, "order": "sequential", "stars": normalize(self.stars)}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as error:
            print(f"Editor: could not save {path}: {error}")
            self.say(f"Could not save {path}", False, now)
            return None
        print(f"Editor: saved {path} with {len(self.stars)} stars")
        self.say(f"Saved {path.replace(os.sep, '/')}", True, now)
        return path

    def current_message(self, now):
        """The latest message while it is still showing: (text, ok?), or None."""
        text, ok, shown = self.message
        return (text, ok) if text and now - shown < MESSAGE_SECONDS else None

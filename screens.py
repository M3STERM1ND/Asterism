"""Screens: text panels drawn on top of the sky, after render.py has drawn the frame.

  start screen - title and the menu (P play, R practice, E editor; T lean test in the key bar)
  editor       - the stars being placed, their order, the name, and save messages
  lean test    - each step's instruction, countdown and progress, then the results table
  tuning bars  - the lean guard's live readings (key D, and always during the lean test)
"""
import cv2
import numpy as np

from editor import MAX_STARS, MIN_STARS
from lean_test import STEPS
from render import CYAN, GLOW_SCALE, GOLD, H, MARGIN, MUTED, RED, W, add_glow, scale, small
from text import draw_text


MENU = (("P", "Play", "Battles: win back the sky from Scorpius, turn by turn"),
        ("R", "Practice", "Reach only: draw the zodiac, one constellation at a time"),
        ("E", "Editor", "Craft a constellation: click to place 4 to 8 stars"))


def draw_start(frame, now):
    """The start menu: the title, a one-line idea, and the three choices with their keys."""
    glow = 0.85 + 0.15 * np.sin(now * 1.5)
    draw_text(frame, "Asterism", (W // 2, 150), 72, GOLD, 600, glow, "center")
    draw_text(frame, "Reach to draw the stars", (W // 2, 245), 24, MUTED, 400, 1.0, "center")
    for i, (key, label, note) in enumerate(MENU):
        y = 315 + i * 80
        cv2.circle(frame, (W // 2 - 190, y + 18), 24, scale(CYAN, 0.9), 2, cv2.LINE_AA)
        draw_text(frame, key, (W // 2 - 190, y + 6), 24, CYAN, 600, 1.0, "center")
        draw_text(frame, label, (W // 2 - 140, y - 2), 30, GOLD, 600, 1.0)
        draw_text(frame, note, (W // 2 - 140, y + 38), 18, MUTED, 400, 1.0)
    draw_text(frame, "Sit 3 to 4 feet from the laptop, facing the camera", (W // 2, H - 130), 18, MUTED, 400, 0.9, "center")


def draw_canvas(frame, canvas):
    """Faint corner marks around the area where stars can be placed."""
    left, top, right, bottom = canvas
    tick, color = 22, scale(MUTED, 0.45)
    for x, dx in ((left, tick), (right, -tick)):
        for y, dy in ((top, tick), (bottom, -tick)):
            cv2.line(frame, (x, y), (x + dx, y), color, 1, cv2.LINE_AA)
            cv2.line(frame, (x, y), (x, y + dy), color, 1, cv2.LINE_AA)


def draw_editor_stars(frame, stars):
    """The placed stars joined in drawing order, each with its number."""
    glow = np.zeros((H // GLOW_SCALE, W // GLOW_SCALE, 3), np.uint8)
    points = [(int(x), int(y)) for x, y in stars]
    for a, b in zip(points, points[1:]):
        cv2.line(frame, a, b, scale(GOLD, 0.6), 2, cv2.LINE_AA)
        cv2.line(glow, small(a), small(b), scale(GOLD, 0.35), 1, cv2.LINE_AA)
    for i, p in enumerate(points):
        cv2.circle(frame, p, 7, (235, 250, 255), -1, cv2.LINE_AA)
        cv2.circle(glow, small(p), 4, GOLD, -1, cv2.LINE_AA)
        draw_text(frame, str(i + 1), (p[0] + 14, p[1] - 26), 16, MUTED, 500, 1.0)
    add_glow(frame, glow)


def draw_editor(frame, editor, now):
    """The editor: the name (or the name being typed), how many stars, the stars, and the latest message."""
    draw_canvas(frame, editor.canvas)
    draw_editor_stars(frame, editor.stars)
    draw_text(frame, "Editor", (W // 2, MARGIN - 6), 18, MUTED, 500, 0.9, "center")
    if editor.typing is not None:
        caret = "|" if int(now * 2) % 2 == 0 else " "
        draw_text(frame, editor.typing + caret, (W // 2, MARGIN + 20), 30, CYAN, 500, 1.0, "center")
        draw_text(frame, "Type a name  ·  Enter keep  ·  Esc cancel", (W // 2, MARGIN + 62), 16, MUTED, 400, 1.0, "center")
    else:
        name, color = (editor.name, GOLD) if editor.name else ("Untitled  ·  N to name it", MUTED)
        draw_text(frame, name, (W // 2, MARGIN + 20), 30, color, 500, 1.0, "center")
        count = len(editor.stars)
        draw_text(frame, f"{count} stars  ·  {MIN_STARS} to {MAX_STARS}", (W // 2, MARGIN + 62), 16,
                  CYAN if MIN_STARS <= count <= MAX_STARS else MUTED, 500, 1.0, "center")
    if not editor.stars:
        draw_text(frame, "Click to place the first star, in the order the player will draw them",
                  (W // 2, H // 2 - 12), 22, MUTED, 400, 0.9, "center")
    message = editor.current_message(now)
    if message:
        text, ok = message
        draw_text(frame, text, (W // 2, H - 110), 22, CYAN if ok else RED, 500, 1.0, "center")


def draw_tuning(frame, guard, label):
    """A bar per lean check, with a gold line at its threshold (1.0); red once past it."""
    if guard is None or not guard.ratios:
        return
    left, top, full = MARGIN, 190, 160  # full = bar length for 2x the threshold
    draw_text(frame, f"Lean checks  ·  {label}", (left, top - 34), 16, MUTED, 500, 1.0)
    for i, (name, ratio) in enumerate(guard.ratios.items()):
        y = top + i * 30
        length = int(min(ratio, 2.0) / 2.0 * full)
        color = RED if ratio >= 1.0 else CYAN
        draw_text(frame, name, (left, y - 2), 16, MUTED, 400, 1.0)
        cv2.line(frame, (left + 60, y + 8), (left + 60 + full, y + 8), scale(MUTED, 0.3), 6)
        cv2.line(frame, (left + 60, y + 8), (left + 60 + length, y + 8), color, 6)
        cv2.line(frame, (left + 60 + full // 2, y), (left + 60 + full // 2, y + 16), GOLD, 1)
        draw_text(frame, f"{ratio:.1f}", (left + 70 + full, y - 2), 16, color, 500, 1.0)


def draw_test_step(frame, test, now):
    """The current step: which one, what to do, a get-ready countdown, then a progress bar."""
    name, text = test.instruction()
    draw_text(frame, f"Lean test  ·  step {test.step + 1} of {len(STEPS)}", (W // 2, MARGIN), 18, MUTED, 500, 0.9, "center")
    draw_text(frame, text, (W // 2, MARGIN + 34), 30, GOLD, 500, 1.0, "center")
    ready, progress = test.timing(now)
    if ready > 0:
        draw_text(frame, f"Get ready  {int(np.ceil(ready))}", (W // 2, MARGIN + 84), 22, CYAN, 500, 1.0, "center")
        return
    left, right, y = W // 2 - 140, W // 2 + 140, MARGIN + 96
    cv2.line(frame, (left, y), (right, y), scale(MUTED, 0.4), 2, cv2.LINE_AA)
    cv2.line(frame, (left, y), (int(left + (right - left) * progress), y), CYAN, 3, cv2.LINE_AA)


def draw_test_results(frame, test):
    """The results: the highest reading of each check per step (red if it crossed), warnings, verdict."""
    rows = test.summary()
    checks = sorted({key for row in rows.values() for key in row["max"]})
    panel = frame[110:540, 220:W - 220]
    panel[:] = (panel * 0.35).astype(np.uint8)  # darken behind the table so it reads clearly
    draw_text(frame, "Lean test results", (W // 2, 140), 34, GOLD, 600, 1.0, "center")
    draw_text(frame, "Highest reading of each check (1.0 = its threshold)", (W // 2, 190), 18, MUTED, 400, 1.0, "center")
    columns = [300] + [430 + i * 110 for i in range(len(checks))] + [430 + len(checks) * 110]
    for x, title in zip(columns, ["step"] + checks + ["warnings"]):
        draw_text(frame, title, (x, 240), 18, MUTED, 500, 1.0)
    for r, (name, row) in enumerate(rows.items()):
        y = 285 + r * 46
        draw_text(frame, name, (columns[0], y), 22, GOLD, 500, 1.0)
        for x, key in zip(columns[1:], checks):
            value = row["max"].get(key, 0.0)
            draw_text(frame, f"{value:.2f}", (x, y), 22, RED if value >= 1.0 else CYAN, 500, 1.0)
        bad = row["warnings"] > 0 if name != "lean" else row["warnings"] == 0
        draw_text(frame, str(row["warnings"]), (columns[-1], y), 22, RED if bad else CYAN, 600, 1.0)
    verdict = test.verdict()
    draw_text(frame, verdict, (W // 2, 450), 22, CYAN if verdict.startswith("Pass") else RED, 600, 1.0, "center")
    draw_text(frame, "T  test again   ·   M  start screen", (W // 2, 500),
              18, MUTED, 400, 1.0, "center")


def draw_screens(frame, play, tuning, now):
    """Draw whichever screen the current mode needs on top of the frame."""
    if play.mode == "start":
        draw_start(frame, now)
        return
    if play.mode == "editor":
        draw_editor(frame, play.editor, now)
        return
    if play.mode == "test" and play.test is not None:
        if play.test.done:
            draw_test_results(frame, play.test)
            return
        draw_test_step(frame, play.test, now)
        draw_tuning(frame, play.guard, play.test.instruction()[0])
    elif tuning:
        draw_tuning(frame, play.guard, "live")

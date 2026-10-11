"""Lobby screen: log in or create an account, then pick a run (save file) or start a new one."""
import cv2
import numpy as np

from lobby import FORMS
from render import CYAN, GOLD, H, MUTED, RED, W, scale
from text import draw_text

PORTAL_HINT = "Coaches: open the coach portal, python -m portal, then http://localhost:8765"


def draw_key(frame, key, x, y):
    cv2.circle(frame, (x, y + 14), 20, scale(CYAN, 0.9), 2, cv2.LINE_AA)
    draw_text(frame, key, (x, y + 3), 20, CYAN, 600, 1.0, "center")


def draw_lobby(frame, lobby, now):
    glow = 0.85 + 0.15 * np.sin(now * 1.5)
    draw_text(frame, "Asterism", (W // 2, 70), 64, GOLD, 600, glow, "center")
    if lobby.state == "welcome":
        draw_text(frame, "Home rehab, one star at a time", (W // 2, 160), 22, MUTED, 400, 1.0, "center")
        for i, (key, label, note) in enumerate((("L", "Log in", "Continue with your account"),
                                                 ("N", "New patient", "Create an account to save your runs"))):
            y = 240 + i * 80
            draw_key(frame, key, W // 2 - 170, y)
            draw_text(frame, label, (W // 2 - 120, y - 4), 30, GOLD, 600, 1.0)
            draw_text(frame, note, (W // 2 - 120, y + 34), 16, MUTED, 400, 1.0)
        draw_text(frame, PORTAL_HINT, (W // 2, 470), 16, MUTED, 400, 0.9, "center")
    elif lobby.state in FORMS:
        draw_form(frame, lobby, now)
    elif lobby.state == "runs":
        draw_runs(frame, lobby)
    if lobby.message:
        draw_text(frame, lobby.message, (W // 2, H - 120), 20, CYAN if lobby.ok else RED, 500, 1.0, "center")


def draw_form(frame, lobby, now):
    title = {"login": "Log in", "register": "New patient account", "new_run": "Start a new run"}[lobby.state]
    draw_text(frame, title, (W // 2, 170), 30, GOLD, 600, 1.0, "center")
    for i, (name, label, secret) in enumerate(FORMS[lobby.state]):
        y = 240 + i * 80
        value = lobby.values.get(name, "")
        shown = "*" * len(value) if secret else value
        active = i == lobby.field
        caret = "|" if active and int(now * 2) % 2 == 0 else ""
        draw_text(frame, label, (W // 2 - 220, y), 16, CYAN if active else MUTED, 500, 1.0)
        cv2.line(frame, (W // 2 - 220, y + 62), (W // 2 + 220, y + 62), scale(CYAN if active else MUTED, 0.6), 1, cv2.LINE_AA)
        draw_text(frame, shown + caret, (W // 2 - 220, y + 24), 26, GOLD, 500, 1.0)
    hint = "Enter or Tab next field  ·  Enter on the last one to finish  ·  Esc back"
    if lobby.state == "new_run":
        hint = "A run is like a new world: fresh progress, its own sessions and videos  ·  Enter to start  ·  Esc back"
    draw_text(frame, hint, (W // 2, 500), 16, MUTED, 400, 1.0, "center")


def draw_runs(frame, lobby):
    draw_text(frame, f"{lobby.user.display_name}'s runs", (W // 2, 160), 30, GOLD, 600, 1.0, "center")
    runs = lobby.runs()
    if not runs:
        draw_text(frame, "No runs yet. Press N to start your first one.", (W // 2, 260), 22, MUTED, 400, 1.0, "center")
    for i, run in enumerate(runs):
        y = 215 + i * 44
        draw_key(frame, str(i + 1), W // 2 - 300, y - 6)
        draw_text(frame, run.name, (W // 2 - 260, y - 6), 24, GOLD, 600, 1.0)
        played = f"last played {run.last_played[:16]}" if run.last_played else "not played yet"
        draw_text(frame, played, (W // 2 + 300, y - 2), 16, MUTED, 400, 1.0, "right")
    draw_text(frame, "1-9 continue a run  ·  N new run  ·  O log out", (W // 2, H - 170), 18, CYAN, 500, 1.0, "center")

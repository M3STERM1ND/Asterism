"""Progress screen (key G on the start screen): sessions.csv drawn as a night sky, for the overall trend.

Six panels, each a little constellation: every session is a star, joined in order, so the trend reads as
the shape of the sky. Each says whether that measure is improving, steady or getting worse (progress.trend,
which knows which way is better). R writes the therapist's report (therapy_report.py) and opens it.
"""
import cv2
import numpy as np

import progress
from render import CYAN, GLOW_SCALE, GOLD, H, MARGIN, MUTED, RED, W, add_glow, scale, small
from text import draw_text

PANELS = ("max_reach", "error_sw", "straightness", "lean_per_10", "open_s", "pain")
PANEL_W, PANEL_H, PANEL_GAP = 372, 200, 22
TOPS = (148, 400)
PLOT_PAD = 26
TREND_TEXT = {"better": ("improving", CYAN), "worse": ("getting worse", RED), "same": ("steady", MUTED),
              None: ("needs 3 sessions", MUTED)}


def plot_points(values, rect, top):
    """Pixel positions for a series: evenly spaced left to right, higher value = higher on screen.
    top is the value at the top of the plot (never 0, so an all-zero series sits on the baseline)."""
    left, y0, right, bottom = rect
    n = len(values)
    xs = [(left + right) / 2] if n == 1 else list(np.linspace(left, right, n))
    return [(int(x), int(bottom - (bottom - y0) * min(1.0, v / top))) for x, v in zip(xs, values)]


def draw_series(frame, glow, rect, values, fmt, color=GOLD, mark_last=True):
    """One chart: a faint baseline, the sessions joined as a constellation, and the latest value labelled."""
    left, top, right, bottom = rect
    cv2.line(frame, (left, bottom), (right, bottom), scale(MUTED, 0.3), 1, cv2.LINE_AA)
    if not values:
        draw_text(frame, "No sessions yet", ((left + right) // 2, (top + bottom) // 2 - 10), 16, MUTED, 400, 0.8, "center")
        return
    peak = max(max(values) * 1.15, 1e-6)
    pts = plot_points(values, rect, peak)
    for a, b in zip(pts, pts[1:]):
        cv2.line(frame, a, b, scale(color, 0.55), 1, cv2.LINE_AA)
        cv2.line(glow, small(a), small(b), scale(color, 0.3), 1, cv2.LINE_AA)
    for i, p in enumerate(pts):
        last = mark_last and i == len(pts) - 1
        cv2.circle(frame, p, 6 if last else 4, CYAN if last else (235, 250, 255), -1, cv2.LINE_AA)
        cv2.circle(glow, small(p), 3 if last else 2, CYAN if last else color, -1, cv2.LINE_AA)
    draw_text(frame, fmt(values[-1]), (pts[-1][0], pts[-1][1] - 30), 16, CYAN, 600, 1.0, "center")


def draw_panel(frame, glow, x, y, key, sessions):
    metric = progress.BY_KEY[key]
    values = progress.series(sessions, key)
    word, color = TREND_TEXT[progress.trend(values, metric.better)]
    draw_text(frame, metric.label, (x, y), 22, GOLD, 600, 1.0)
    draw_text(frame, word, (x + PANEL_W, y + 4), 16, color, 600, 1.0, "right")
    draw_text(frame, f"{metric.unit}  ·  {metric.better} is better", (x, y + 30), 13, MUTED, 400, 1.0)
    rect = (x + PLOT_PAD, y + 82, x + PANEL_W - PLOT_PAD, y + PANEL_H)
    draw_series(frame, glow, rect, values, lambda v: metric.fmt.format(v), RED if key in ("lean_per_10", "pain") else GOLD)


def draw_progress(frame, sessions, now, message=""):
    """The whole screen: title, six trend panels, and the report key."""
    glow = np.zeros((H // GLOW_SCALE, W // GLOW_SCALE, 3), np.uint8)
    draw_text(frame, "Progress", (W // 2, MARGIN - 10), 38, GOLD, 600, 1.0, "center")
    count = len(sessions)
    draw_text(frame, f"{count} session{'s' if count != 1 else ''}  ·  oldest to latest, left to right  ·  "
                     "R  report for your therapist", (W // 2, MARGIN + 38), 16, MUTED, 400, 1.0, "center")
    left0 = (W - (3 * PANEL_W + 2 * PANEL_GAP)) // 2
    for i, key in enumerate(PANELS):
        x = left0 + (i % 3) * (PANEL_W + PANEL_GAP)
        draw_panel(frame, glow, x, TOPS[i // 3], key, sessions)
    if message:
        draw_text(frame, message, (W // 2, H - 96), 16, CYAN, 500, 1.0, "center")
    add_glow(frame, glow)

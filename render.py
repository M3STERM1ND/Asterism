"""Render: draws the night sky, the player's stars, event effects and text.

The camera feed is hidden; the player only sees themselves as stars.
All shapes are light: they are drawn on a black "light" layer that is added onto the sky,
so a fading star only ever gets dimmer, never darker than the sky behind it.
Glow: bright shapes are also drawn on a small separate layer, blurred, and added on top.
"""
import time

import cv2
import numpy as np

import events
from fingers import backup_tips
from sessions.reach import HIT_RADIUS
from text import draw_text

W, H = 1280, 720
MARGIN = 48
GLOW_SCALE = 4  # the glow layer is 4x smaller: blurring it is cheap and looks just as soft

# Colors are BGR, as OpenCV expects.
GOLD = (176, 232, 255)        # #FFE8B0 white-gold stars
CYAN = (255, 219, 127)        # #7FDBFF the active target only
RED = (107, 107, 255)         # #FF6B6B warnings and Scorpius only
SHIELD_BLUE = (255, 190, 120)  # #78BEFF
MUTED = (184, 150, 138)       # #8A96B8 quiet interface text
SKY_TOP = (26, 11, 7)         # #070B1A
SKY_BOTTOM = (58, 26, 15)     # #0F1A3A

HAND_LINES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
              (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
              (17, 18), (18, 19), (19, 20)]
WRIST, MIDDLE_BASE, INDEX_TIP = 0, 9, 8
FULL_HAND_PX = 90  # a hand this big on screen (wrist to middle-finger base) gets full-size stars and glow
BRIGHTEST = ("Betelgeuse", "Rigel")  # Orion's two brightest stars get drawn a little bigger
LEFT_LABELS = ("Betelgeuse", "Alnitak", "Saiph")  # names on the left side sit left of their star
ORION_DIM = 0.4  # the player's Orion fades to this brightness while a constellation is being drawn
LINE_GROW_SECONDS = 0.6
CALIBRATED_MESSAGE_SECONDS = 3.0  # how long "Reach measured" stays up after calibration
LEAN_MESSAGE = "Reach with your arm, not your body"  # a new constellation line grows from the previous star over this long


def scale(color, k):
    """Dim a color by k (0 to 1); on a dark sky this reads as fading out."""
    return tuple(int(c * k) for c in color)


def soft_blob(cx, cy, radius):
    """A 0-to-1 Gaussian blob over the whole screen, centered at (cx, cy)."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    return np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * radius ** 2))


def make_background(rng):
    """Navy gradient with two faint nebula clouds and fine grain (the grain also hides color banding)."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (0.8 * ys / H + 0.2 * xs / W)[..., None]
    sky = np.array(SKY_TOP, np.float32) * (1 - t) + np.array(SKY_BOTTOM, np.float32) * t
    sky += soft_blob(W * 0.78, H * 0.25, 260)[..., None] * np.array([40, 14, 22], np.float32)  # violet
    sky += soft_blob(W * 0.18, H * 0.85, 300)[..., None] * np.array([34, 24, 6], np.float32)   # deep teal
    sky += rng.normal(0, 1.4, (H, W, 1))
    return np.clip(sky, 0, 255).astype(np.uint8)


def make_stars(rng, count=150):
    """Random background stars: position, brightness, size, twinkle speed and phase, color."""
    bright = rng.random(count) < 0.12
    return {
        "pos": np.column_stack([rng.integers(0, W, count), rng.integers(0, H, count)]),
        "level": np.where(bright, rng.uniform(0.6, 0.9, count), rng.uniform(0.18, 0.5, count)),
        "bright": bright,
        "speed": rng.uniform(0.5, 2.0, count),
        "phase": rng.uniform(0, 2 * np.pi, count),
        "color": np.array([GOLD if rng.random() < 0.6 else (255, 240, 228) for _ in range(count)], np.float32),
    }


def make_vignette(color):
    """Color in a soft oval around the screen edges, clear in the middle."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xs - W / 2) / (W / 2)) ** 2 + ((ys - H / 2) / (H / 2)) ** 2)  # 0 center, 1 at edge middles
    strength = np.clip((r - 0.7) / 0.6, 0, 1) ** 1.5
    return (strength[..., None] * np.array(color, np.float32)).astype(np.uint8)


_rng = np.random.default_rng(7)  # fixed seed: the same sky every time
BACKGROUND = make_background(_rng)
STARS = make_stars(_rng)
RED_EDGES = make_vignette((40, 40, 210))  # a deeper red than the text, so the edges glow red, not pink
GOLD_WASH = (soft_blob(W / 2, H / 2, 300)[..., None] * np.array(GOLD, np.float32)).astype(np.uint8)


def to_px(landmark):
    """Convert a normalized landmark (0 to 1) into screen pixels."""
    return int(landmark.x * W), int(landmark.y * H)


def small(point):
    """Map a screen point onto the smaller glow layer."""
    return int(point[0] / GLOW_SCALE), int(point[1] / GLOW_SCALE)


def draw_sky(frame, glow, now):
    """Twinkle each background star; faint ones are a pixel plus a dim cross, bright ones are glowing circles."""
    twinkle = STARS["level"] * (0.6 + 0.4 * np.sin(now * STARS["speed"] + STARS["phase"]))
    colors = STARS["color"] * twinkle[:, None]
    faint = ~STARS["bright"]
    xs, ys = np.clip(STARS["pos"][faint, 0], 1, W - 2), np.clip(STARS["pos"][faint, 1], 1, H - 2)
    for dx, dy, k in [(0, 0, 1.0), (1, 0, 0.3), (-1, 0, 0.3), (0, 1, 0.3), (0, -1, 0.3)]:
        frame[ys + dy, xs + dx] = colors[faint] * k  # all faint stars at once, no Python loop
    for (x, y), color in zip(STARS["pos"][~faint], colors[~faint]):
        cv2.circle(frame, (int(x), int(y)), 2, color.tolist(), -1, cv2.LINE_AA)
        cv2.circle(glow, small((x, y)), 1, color.tolist(), -1, cv2.LINE_AA)


def draw_hand(frame, glow, hand):
    """Draw one hand as small stars joined by faint lines; the index fingertip is the brightest star.
    Stars and glow shrink when the hand looks small (far away or sideways), so bunched joints don't blur into a blob."""
    points = [to_px(lm) for lm in hand]
    size = min(1.0, np.hypot(points[WRIST][0] - points[MIDDLE_BASE][0],
                             points[WRIST][1] - points[MIDDLE_BASE][1]) / FULL_HAND_PX)
    for a, b in HAND_LINES:
        cv2.line(frame, points[a], points[b], scale(GOLD, 0.3), 1, cv2.LINE_AA)
    joint_radius = 1 if size < 0.5 else 2 if size < 0.8 else 3
    for i, p in enumerate(points):
        if i != INDEX_TIP:
            cv2.circle(frame, p, joint_radius, scale(GOLD, 0.85), -1, cv2.LINE_AA)
            if size >= 0.8:  # only a big, open hand gets glow on every joint
                cv2.circle(glow, small(p), 1, scale(GOLD, 0.5), -1, cv2.LINE_AA)
    tip = points[INDEX_TIP]
    cv2.circle(glow, small(tip), 2, scale(GOLD, 0.5 + 0.4 * size), -1, cv2.LINE_AA)
    cv2.circle(frame, tip, 3 + round(2 * size), (235, 250, 255), -1, cv2.LINE_AA)


def draw_backup_tips(light, glow, hands, pose):
    """Fingertips Hands has lost but Pose still sees: a bright star, so reaching never goes blank."""
    for x, y in backup_tips(hands, pose, np.array([W, H])):
        p = (int(x), int(y))
        cv2.circle(glow, small(p), 2, scale(GOLD, 0.7), -1, cv2.LINE_AA)
        cv2.circle(light, p, 5, (235, 250, 255), -1, cv2.LINE_AA)


def norm_px(point):
    """Convert a normalized (x, y) pair into screen pixels."""
    return int(point[0] * W), int(point[1] * H)


def gapped_line(img, a, b, color, gap):
    """A line from a to b that stops short of both ends, like lines on a star chart."""
    length = np.hypot(b[0] - a[0], b[1] - a[1])
    if length <= 2 * gap:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    start = (int(a[0] + ux * gap), int(a[1] + uy * gap))
    end = (int(b[0] - ux * gap), int(b[1] - uy * gap))
    cv2.line(img, start, end, color, 1, cv2.LINE_AA)


def draw_orion(light, glow, figure, k=1.0):
    """Draw the player's Orion: faint chart lines, named stars with a small sparkle, and an arm to each hand.
    k dims the whole figure (1 = full brightness), so a constellation being drawn stands out."""
    points = {name: norm_px(p) for name, p in figure.stars.items()}
    for a, b in figure.lines:
        gapped_line(light, points[a], points[b], scale(GOLD, 0.35 * k), 12)
        gapped_line(glow, small(points[a]), small(points[b]), scale(GOLD, 0.12 * k), 1)
    for shoulder, wrist in figure.arms:
        gapped_line(light, points[shoulder], norm_px(wrist), scale(GOLD, 0.25 * k), 12)
    for name, (x, y) in points.items():
        size = 7 if name in BRIGHTEST else 5
        cv2.circle(light, (x, y), size, scale(GOLD, k), -1, cv2.LINE_AA)
        cv2.line(light, (x - size * 3, y), (x + size * 3, y), scale(GOLD, 0.35 * k), 1, cv2.LINE_AA)
        cv2.line(light, (x, y - size * 3), (x, y + size * 3), scale(GOLD, 0.35 * k), 1, cv2.LINE_AA)
        cv2.circle(glow, small((x, y)), size // 2, scale(GOLD, 0.9 * k), -1, cv2.LINE_AA)


def draw_orion_names(frame, figure):
    """Write each star's name beside it, faded by the figure's names_alpha."""
    if figure.names_alpha <= 0:
        return
    for name, p in figure.stars.items():
        x, y = norm_px(p)
        if name == "Alnilam":  # the middle belt star: name goes above, in the empty space inside the torso
            draw_text(frame, name, (x, y - 40), 18, GOLD, 500, figure.names_alpha * 0.85, "center")
        elif name in LEFT_LABELS:
            draw_text(frame, name, (x - 22, y - 11), 18, GOLD, 500, figure.names_alpha * 0.85, "right")
        else:
            draw_text(frame, name, (x + 22, y - 11), 18, GOLD, 500, figure.names_alpha * 0.85)


def add_glow(frame, glow):
    """Blur the glow layer at two sizes (tight and wide), scale it up, and add it onto the frame."""
    tight = cv2.GaussianBlur(glow, (0, 0), 1.5)
    wide = cv2.pyrUp(cv2.GaussianBlur(cv2.pyrDown(glow), (0, 0), 3))  # blur at half size: same look, 4x cheaper
    bloom = cv2.addWeighted(tight, 1.2, wide, 1.6, 0)
    cv2.add(frame, cv2.resize(bloom, (W, H), interpolation=cv2.INTER_LINEAR), dst=frame)


def star_burst(frame, fx, glow, center, n, p):
    """Gold burst for STAR: a flash, an expanding ring and eight rays, fading as p goes 0 to 1.
    Ring and rays go on the fx light layer (added on top), so a fading burst never darkens what's under it."""
    fade = 1 - p
    radius = int(18 + 120 * (1 - (1 - p) ** 3))  # fast at first, then slows
    flash = max(0.0, 1 - p * 3)  # the flash is over in the first third
    if flash > 0:
        cv2.circle(glow, small(center), int(2 + 5 * (1 - flash)), scale(GOLD, flash * 0.8), -1, cv2.LINE_AA)
    cv2.circle(glow, small(center), radius // GLOW_SCALE, scale(GOLD, fade * 0.7), 1, cv2.LINE_AA)
    cv2.circle(fx, center, radius, scale(GOLD, fade * 0.8), 1, cv2.LINE_AA)
    for k in range(8):
        angle = k * np.pi / 4 + p
        reach = 0.85 if k % 2 == 0 else 0.7
        a = (int(center[0] + np.cos(angle) * radius * 0.5), int(center[1] + np.sin(angle) * radius * 0.5))
        b = (int(center[0] + np.cos(angle) * radius * reach), int(center[1] + np.sin(angle) * radius * reach))
        cv2.line(fx, a, b, scale(GOLD, fade * 0.9), 1, cv2.LINE_AA)
    draw_text(frame, f"Star {n}", (center[0], center[1] - radius - 44), 22, GOLD, 500, fade, "center")


def fade_in_out(p, fade_in=0.15, fade_out=0.3):
    """Opacity that rises quickly at the start and falls at the end of an effect (p goes 0 to 1)."""
    return min(1.0, p / fade_in, (1 - p) / fade_out)


def draw_effects(frame, glow, anchor):
    """Draw the screen effect for each recent event; p is how far through the effect it is (0 to 1).
    Effects with a position (like the star that was hit) appear there; others use the anchor."""
    effects = events.active_effects()
    fx = np.zeros_like(frame) if any(e[0] in ("STAR", "SHIELD") for e in effects) else None
    for event, n, pos, age in effects:
        p = min(age / events.EFFECT_SECONDS, 1.0)
        if event == "STAR":
            star_burst(frame, fx, glow, (int(pos[0]), int(pos[1])) if pos else anchor, n, p)
        elif event == "WIN":  # the session draws the constellation's name; this is the warm wash
            cv2.addWeighted(frame, 1, GOLD_WASH, 0.16 * (1 - p), 0, dst=frame)
        elif event == "WARN LEAN":  # the message itself is drawn by draw_lean_message
            cv2.addWeighted(frame, 1, RED_EDGES, 1 - p, 0, dst=frame)
        elif event == "ATTACK":
            pulse = 0.5 - 0.5 * np.cos(p * 3 * 2 * np.pi)  # three pulses
            cv2.addWeighted(frame, 1, RED_EDGES, pulse * (1 - p * 0.5), 0, dst=frame)  # the battle names the attacker
        elif event == "SHIELD":  # a blue ring around the player (pos), or the middle of the screen
            center = (int(pos[0]), int(pos[1])) if pos else (W // 2, H // 2)
            radius = int(150 + 40 * (1 - (1 - p) ** 3))
            cv2.circle(glow, small(center), radius // GLOW_SCALE, scale(SHIELD_BLUE, 0.7 * (1 - p)), 1, cv2.LINE_AA)
            cv2.circle(fx, center, radius, scale(SHIELD_BLUE, 1 - p), 3, cv2.LINE_AA)
            draw_text(frame, "Shield up", (center[0], center[1] + radius + 18), 26, SHIELD_BLUE, 500, fade_in_out(p), "center")
    if fx is not None:
        cv2.add(frame, fx, dst=frame)


def draw_reach(light, glow, reach, now):
    """Draw the Reach session: lit stars in gold, lines growing in, the pulsing cyan target with a
    ring that fills while the fingertip holds on it, and a glowing shape once it is complete."""
    if reach is None or reach.points is None:
        return
    pts = [(int(x), int(y)) for x, y in reach.points]
    draw_unlit(light, glow, reach, pts, now)
    won = reach.won_at is not None
    shine = 0.75 + 0.25 * np.sin((now - reach.won_at) * 3) if won else 0.6  # the finished shape breathes
    for i in range(1, len(reach.lit_at)):
        grow = min(1.0, (now - reach.lit_at[i]) / LINE_GROW_SECONDS)
        end = (int(pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * grow), int(pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * grow))
        cv2.line(light, pts[i - 1], end, scale(GOLD, shine * grow), 2, cv2.LINE_AA)
        cv2.line(glow, small(pts[i - 1]), small(end), scale(GOLD, (0.9 if won else 0.35) * shine * grow), 1, cv2.LINE_AA)
    for p in pts[:len(reach.lit_at)]:
        cv2.circle(light, p, 5, GOLD, -1, cv2.LINE_AA)
        cv2.circle(glow, small(p), 2, scale(GOLD, 0.8 * shine), -1, cv2.LINE_AA)
    i = reach.target_index()
    if i is not None:
        target = pts[i]
        color = RED if reach.blocked else CYAN  # red while leaning: this star can't be lit right now
        pulse = 0.5 + 0.5 * np.sin(now * 4)
        ring = int(HIT_RADIUS * (0.55 + 0.15 * pulse))
        cv2.circle(light, target, ring, scale(color, 0.5 + 0.3 * pulse), 1, cv2.LINE_AA)
        cv2.circle(light, target, 6, color, -1, cv2.LINE_AA)
        cv2.circle(glow, small(target), 2 + int(2 * pulse), scale(color, 0.6 + 0.4 * pulse), -1, cv2.LINE_AA)
        if reach.dwell > 0:  # the hold: a ring fills clockwise from the top
            cv2.ellipse(light, target, (ring + 8, ring + 8), -90, 0, 360 * reach.dwell, CYAN, 3, cv2.LINE_AA)


def draw_unlit(light, glow, reach, pts, now):
    """Stars not yet lit, in the reach's unlit color (Scorpius waits in red until each star is taken back)."""
    if reach.unlit_color is None:
        return
    first = len(reach.lit_at)
    breathe = 0.45 + 0.15 * np.sin(now * 2)
    for a, b in zip(pts[max(first - 1, 0):], pts[max(first - 1, 0) + 1:]):
        cv2.line(light, a, b, scale(reach.unlit_color, 0.35 * breathe), 1, cv2.LINE_AA)
    for p in pts[first:]:
        cv2.circle(light, p, 5, scale(reach.unlit_color, breathe + 0.2), -1, cv2.LINE_AA)
        cv2.circle(glow, small(p), 2, scale(reach.unlit_color, breathe), -1, cv2.LINE_AA)


def draw_sky_constellations(light, glow, sky):
    """Constellations won this session, faint gold in the background: the sky being won back."""
    for _, points in sky:
        pts = [(int(x), int(y)) for x, y in points]
        for a, b in zip(pts, pts[1:]):
            cv2.line(light, a, b, scale(GOLD, 0.16), 1, cv2.LINE_AA)
        for p in pts:
            cv2.circle(light, p, 2, scale(GOLD, 0.45), -1, cv2.LINE_AA)
            cv2.circle(glow, small(p), 1, scale(GOLD, 0.25), -1, cv2.LINE_AA)


def draw_reach_text(frame, reach, now):
    """Progress label at the top, and (when it celebrates) the constellation's name fading in when complete."""
    if reach is None or reach.points is None:
        return
    total, lit = len(reach.points), len(reach.lit_at)
    if not reach.celebrate:  # in a battle, the battle's headline shows the progress
        return
    if reach.won_at is None:
        draw_text(frame, f"{reach.name}  ·  {lit} of {total}", (W // 2, MARGIN), 20, MUTED, 500, 0.9, "center")
        return
    fade = min(1.0, (now - reach.won_at) / 1.0)
    top = min(y for _, y in reach.points)
    name_y = max(MARGIN + 30, int(top) - 90)
    draw_text(frame, reach.name, (W // 2, name_y), 48, GOLD, 600, fade, "center")
    draw_text(frame, "Constellation complete", (W // 2, name_y + 62), 20, MUTED, 400, fade, "center")


def draw_lean_message(frame, reach):
    """While the player leans (or just after a WARN LEAN), say how to fix it."""
    warned = any(event == "WARN LEAN" for event, *_ in events.active_effects())
    if warned or (reach is not None and reach.blocked):
        draw_text(frame, LEAN_MESSAGE, (W // 2, H - 150), 30, RED, 500, 1.0, "center")


def draw_calibration(light, glow, cal, now):
    """During the sweep: the fingertip's trail, and a ring showing the farthest reach so far."""
    if cal is None or cal.phase != "sweep" or cal.result is not None:
        return
    for x, y in cal.trail[-240:]:
        cv2.circle(light, (int(x), int(y)), 2, scale(GOLD, 0.45), -1, cv2.LINE_AA)
    side = cal.reaching_side()
    rest = cal.resting_shoulders()
    center = rest["left"] if side == "Betelgeuse" else rest["right"]
    radius = int(cal.best[side] * rest["width"])
    if radius > 0:
        c = (int(center[0]), int(center[1]))
        cv2.circle(light, c, radius, scale(CYAN, 0.55), 1, cv2.LINE_AA)
        cv2.circle(glow, small(c), radius // GLOW_SCALE, scale(CYAN, 0.3), 1, cv2.LINE_AA)


def draw_calibration_text(frame, cal, now):
    """Instructions for each calibration phase, a progress ring, then the measured reach."""
    if cal is None:
        return
    if cal.result is not None:
        if now - cal.done_at < CALIBRATED_MESSAGE_SECONDS:
            draw_text(frame, f"Reach measured: {cal.result.reach:.1f} shoulder widths", (W // 2, MARGIN + 34),
                      20, CYAN, 500, 1.0, "center")
        return
    steps = {"settle": "Sit comfortably and raise your reaching hand",
             "rest": "Sit tall and still",
             "sweep": "Slowly sweep your arm as far as is comfortable"}
    draw_text(frame, "Calibration", (W // 2, MARGIN), 18, MUTED, 500, 0.9, "center")
    draw_text(frame, steps[cal.phase], (W // 2, MARGIN + 34), 30, GOLD, 500, 1.0, "center")
    if cal.phase != "settle":  # a thin progress bar under the instruction
        left, right, y = W // 2 - 140, W // 2 + 140, MARGIN + 84
        cv2.line(frame, (left, y), (right, y), scale(MUTED, 0.4), 2, cv2.LINE_AA)
        cv2.line(frame, (left, y), (int(left + (right - left) * cal.progress(now)), y), CYAN, 3, cv2.LINE_AA)


KEYS = {"start": "P play  ·  R practice  ·  E editor  ·  T lean test  ·  F full screen  ·  Q quit",
        "battle": "M start screen  ·  C calibrate  ·  L lean guard  ·  Space take the hit  ·  R retry  ·  N skip  ·  Q quit",
        "practice": "M start screen  ·  C calibrate  ·  L lean guard  ·  N next  ·  R restart  ·  D lean bars  ·  Q quit",
        "editor": "Click place a star  ·  Right-click or Backspace undo  ·  X clear  ·  N name  ·  S save  ·  M start screen",
        "test": "M start screen  ·  C calibrate  ·  F full screen  ·  Q quit"}


def draw_hud(frame, fps, track_fps, has_hand, figure, now, show_hint=True, guard=None, mode="practice"):
    """Title, frame rate, keys, the lean guard's state, and one gentle prompt: raise a hand, or sit back."""
    draw_text(frame, "Asterism", (MARGIN, MARGIN - 8), 28, GOLD, 600, 0.95)
    draw_text(frame, f"{fps:.0f} fps  ·  tracking {track_fps:.0f}", (W - MARGIN, MARGIN), 16, MUTED, 400, 0.8, "right")
    if guard is not None and not guard.enabled:
        draw_text(frame, "Lean guard off", (W - MARGIN, MARGIN + 26), 16, RED, 500, 0.9, "right")
    draw_text(frame, KEYS[mode], (MARGIN, H - MARGIN - 16), 16, MUTED, 400, 0.8)
    if not show_hint:
        return
    if not has_hand:
        breathe = 0.55 + 0.35 * np.sin(now * 2)
        draw_text(frame, "Raise your hand to begin", (W // 2, MARGIN + 34), 22, GOLD, 400, breathe, "center")
    elif figure and figure.cramped:
        draw_text(frame, "Sit back a little so all of Orion fits", (W // 2, MARGIN + 34), 18, MUTED, 400, 0.85, "center")


def draw(hands, pose, figure, fps, track_fps, play):
    """Draw one full frame of the game (sky, Orion, hands, session, effects, HUD) and return it.
    screens.py draws the start screen and the lean test on top of this."""
    now = time.monotonic()
    reach, calibrator, guard = play.reach, play.calibrator, play.guard
    light = np.zeros((H, W, 3), np.uint8)
    glow = np.zeros((H // GLOW_SCALE, W // GLOW_SCALE, 3), np.uint8)
    draw_sky(light, glow, now)
    if figure:
        drawing = reach is not None and reach.points is not None and reach.won_at is None
        draw_orion(light, glow, figure, ORION_DIM if drawing or play.mode in ("start", "editor") else 1.0)
    draw_sky_constellations(light, glow, play.sky)
    draw_reach(light, glow, reach, now)
    draw_calibration(light, glow, calibrator, now)
    for hand in hands:
        draw_hand(light, glow, hand)
    draw_backup_tips(light, glow, hands, pose)
    frame = cv2.add(BACKGROUND, light)
    anchor = to_px(hands[0][INDEX_TIP]) if hands else (W // 2, H // 2)
    draw_effects(frame, glow, anchor)
    add_glow(frame, glow)
    if figure and play.mode == "practice":  # names would collide with the start screen and test text
        draw_orion_names(frame, figure)
    draw_reach_text(frame, reach, now)
    draw_lean_message(frame, reach)
    calibrating = calibrator is not None and calibrator.result is None
    draw_calibration_text(frame, calibrator, now)
    won = reach is not None and reach.won_at is not None
    busy = won or calibrating or play.mode != "practice"  # these screens use the hint space themselves
    draw_hud(frame, fps, track_fps, bool(hands), figure, now, show_hint=not busy, guard=guard, mode=play.mode)
    return frame

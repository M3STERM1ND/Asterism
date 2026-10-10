"""Battle screen: everything a battle adds on top of the sky.

Health bars for Orion and the enemy, the shadow (battle 1) or Scorpius's red heart (battle 2),
the enemy's strike streaking at Orion, floating damage numbers, the turn prompts, and the Grip
ring that fills while the fist is held.
"""
import cv2
import numpy as np

from game.battle import PLAYER_HEALTH, STRIKE_SECONDS
from render import CYAN, GLOW_SCALE, GOLD, H, MARGIN, MUTED, RED, W, add_glow, scale, small
from sessions.grip import HOLD_SECONDS
from text import draw_text

BAR_WIDTH = 260
POPUP_SECONDS = 1.4
SCORPIUS_HEART = 2  # Antares, the third star drawn in scorpius.json


def draw_bar(frame, glow, x, y, fraction, color, label, value, align="left"):
    """A thin night-sky health bar: a faint track, a glowing fill and a bright end star."""
    left = x if align == "left" else x - BAR_WIDTH
    draw_text(frame, label, (x, y - 32), 18, color, 600, 1.0, align)
    draw_text(frame, value, (x + (BAR_WIDTH if align == "left" else -BAR_WIDTH), y - 30), 16, MUTED, 500, 1.0,
              "right" if align == "left" else "left")
    cv2.line(frame, (left, y), (left + BAR_WIDTH, y), scale(MUTED, 0.35), 3, cv2.LINE_AA)
    filled = int(BAR_WIDTH * max(0.0, min(1.0, fraction)))
    start, end = (left, y), (left + filled, y)
    if align == "right":  # the enemy's bar empties toward the right edge
        start, end = (left + BAR_WIDTH - filled, y), (left + BAR_WIDTH, y)
    if filled > 0:
        cv2.line(frame, start, end, color, 3, cv2.LINE_AA)
        cv2.line(glow, small(start), small(end), scale(color, 0.6), 1, cv2.LINE_AA)
        tip = start if align == "right" else end
        cv2.circle(frame, tip, 4, (235, 250, 255), -1, cv2.LINE_AA)
        cv2.circle(glow, small(tip), 2, color, -1, cv2.LINE_AA)


def enemy_point(battle, cal):
    """Where the enemy is: Scorpius's heart (Antares), or the shadow on the side away from the reaching arm."""
    points = battle.reach.points
    if battle.config["enemy_stars"] is not None and points:
        return points[SCORPIUS_HEART]
    left_side = cal is not None and cal.side == "Bellatrix"
    return (W * 0.17 if left_side else W * 0.83, H * 0.34)


def draw_shadow(frame, glow, center, health, now):
    """The warm-up enemy: a dark smudge with two red eyes that shrinks as it loses health."""
    size = int(40 + 50 * health)
    cx, cy = int(center[0]), int(center[1])
    mask = np.zeros(frame.shape[:2], np.float32)
    cv2.circle(mask, (cx, cy), size, 1.0, -1, cv2.LINE_AA)
    mask = cv2.GaussianBlur(mask, (0, 0), size / 2.5)[..., None]
    frame[:] = (frame * (1 - 0.75 * mask)).astype(np.uint8)  # it swallows the starlight behind it
    blink = 0.7 + 0.3 * np.sin(now * 3)
    for dx in (-size // 4, size // 4):
        eye = (cx + dx, cy - size // 6)
        cv2.circle(frame, eye, 4, scale(RED, blink), -1, cv2.LINE_AA)
        cv2.circle(glow, small(eye), 2, scale(RED, blink), -1, cv2.LINE_AA)


def draw_strike(frame, glow, battle, start, end, now):
    """The enemy's attack: a red comet from the enemy to Orion, then a red burst where it lands."""
    p = min(1.0, (now - battle.phase_at) / STRIKE_SECONDS)
    travel = min(1.0, p / 0.7)
    head = (int(start[0] + (end[0] - start[0]) * travel), int(start[1] + (end[1] - start[1]) * travel))
    tail = (int(start[0] + (end[0] - start[0]) * max(0.0, travel - 0.25)),
            int(start[1] + (end[1] - start[1]) * max(0.0, travel - 0.25)))
    cv2.line(frame, tail, head, RED, 3, cv2.LINE_AA)
    cv2.line(glow, small(tail), small(head), RED, 2, cv2.LINE_AA)
    cv2.circle(glow, small(head), 4, RED, -1, cv2.LINE_AA)
    if p > 0.7:
        burst = (p - 0.7) / 0.3
        cv2.circle(frame, (int(end[0]), int(end[1])), int(30 + 90 * burst), scale(RED, 1 - burst), 2, cv2.LINE_AA)


def draw_popups(frame, battle, now):
    """Damage numbers that float up and fade (gold for hits on the enemy, red for hits on Orion)."""
    battle.popups[:] = [p for p in battle.popups if now - p[3] < POPUP_SECONDS]
    for (x, y), text, color, born in battle.popups:
        age = (now - born) / POPUP_SECONDS
        draw_text(frame, text, (int(x), int(y) - 30 - int(50 * age)), 26, color or GOLD, 600, 1 - age, "center")


def draw_grip(frame, glow, battle, hands, now):
    """The block: a ring around the hand that fills while the fist is held, then asks to open wide."""
    grip = battle.grip
    if not hands:
        draw_text(frame, "Show your hand to the camera", (W // 2, H // 2), 24, MUTED, 500, 1.0, "center")
        return
    palm = hands[0][9]
    center = (int(palm.x * W), int(palm.y * H))
    cv2.circle(frame, center, 64, scale(MUTED, 0.4), 2, cv2.LINE_AA)
    if grip.state == "holding":
        cv2.ellipse(frame, center, (64, 64), -90, 0, 360 * grip.progress, CYAN, 4, cv2.LINE_AA)
        cv2.ellipse(glow, small(center), (64 // GLOW_SCALE, 64 // GLOW_SCALE), -90, 0, 360 * grip.progress, CYAN, 1)
    elif grip.state == "open":
        pulse = 0.6 + 0.4 * np.sin(now * 6)
        cv2.circle(frame, center, 64, scale(GOLD, pulse), 4, cv2.LINE_AA)
        cv2.circle(glow, small(center), 64 // GLOW_SCALE, scale(GOLD, pulse), 1, cv2.LINE_AA)
    if grip.value is not None:  # the openness reading, to help tune the fist and open thresholds
        draw_text(frame, f"grip {grip.value:.2f}", (center[0], center[1] + 76), 14, MUTED, 400, 0.8, "center")


def prompt(battle, now):
    """The headline and the line under it for the current phase."""
    enemy, name = battle.config["enemy"], battle.reach.name
    if battle.phase == "player":
        lit, total = len(battle.reach.lit_at), len(battle.reach.points)
        return f"Your turn: draw {name}  ·  {lit} of {total}", (GOLD, "Reach far for more damage"), MUTED
    if battle.phase == "strike":
        return f"{enemy} strikes!", (RED, ""), MUTED
    if battle.phase == "block":
        grip = battle.grip
        if grip.state == "holding":
            return f"Hold your fist... {max(0.0, HOLD_SECONDS * (1 - grip.progress)):.1f}", (CYAN, "Keep it closed"), MUTED
        if grip.state == "open":
            return "Now open your hand wide", (GOLD, "Spread your fingers to raise the shield"), MUTED
        return "Block! Make a fist and hold it", (CYAN, "Take your time. Space to take the hit"), MUTED
    if battle.phase == "pause":
        good = battle.message == "Blocked!"
        return battle.message, (CYAN if good else RED, ""), MUTED
    if battle.phase == "won":
        loser = "The shadow fades" if battle.config["enemy_stars"] is None else "Scorpius is defeated"
        return f"{name} joins the sky", (GOLD, loser), MUTED
    return "Orion is knocked down", (RED, "Rest a moment, then press R to try again"), MUTED


def draw_battle(frame, play, figure, hands, now):
    """Draw the battle layer on top of the finished frame."""
    if play.victory:
        draw_text(frame, "The sky is yours", (W // 2, H // 2 - 60), 56, GOLD, 600, 1.0, "center")
        draw_text(frame, "Every battle won. M for the start screen", (W // 2, H // 2 + 20), 22, MUTED, 400, 1.0, "center")
        return
    battle = play.battle
    if battle is None or battle.reach.points is None:
        return
    glow = np.zeros((H // GLOW_SCALE, W // GLOW_SCALE, 3), np.uint8)
    enemy = enemy_point(battle, play.calibration)
    health = battle.enemy_health / battle.enemy_max
    if battle.config["enemy_stars"] is None and battle.phase != "won":
        draw_shadow(frame, glow, enemy, health, now)
    elif battle.config["enemy_stars"] is not None and battle.phase != "won":  # Scorpius's heart beats
        beat = 0.5 + 0.5 * np.sin(now * 5)
        cv2.circle(frame, (int(enemy[0]), int(enemy[1])), int(14 + 6 * beat), scale(RED, 0.4 + 0.4 * beat), 2, cv2.LINE_AA)
    if battle.phase == "strike":
        draw_strike(frame, glow, battle, enemy, battle.player_point(figure), now)
    if battle.phase == "block":
        draw_grip(frame, glow, battle, hands, now)
    add_glow(frame, glow)
    draw_bar(frame, glow, MARGIN, 128, battle.player_health / PLAYER_HEALTH, GOLD, "Orion",
             f"{battle.player_health} / {PLAYER_HEALTH}")
    draw_bar(frame, glow, W - MARGIN, 128, health, RED, battle.config["enemy"],
             f"{battle.enemy_health} / {battle.enemy_max}", align="right")
    headline, (color, detail), detail_color = prompt(battle, now)
    draw_text(frame, headline, (W // 2, MARGIN - 6), 28, color, 600, 1.0, "center")
    if detail:
        draw_text(frame, detail, (W // 2, MARGIN + 34), 17, detail_color, 400, 0.9, "center")
    draw_popups(frame, battle, now)

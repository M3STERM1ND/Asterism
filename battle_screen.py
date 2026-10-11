"""Battle screen: everything a battle adds on top of the sky.

Drawn in two steps so the whole frame needs only one glow pass:
  draw_battle_world - before the glow: the enemy, its strike, the Grip ring and the bar shapes
  draw_battle_hud   - after it: text (the turn banner, headline, bars), the spell picker, mana and popups
The turn banner is always on screen: YOUR TURN while the player attacks or blocks, ENEMY'S TURN while
the enemy attacks, guards or heals. After a battle: the check-in (how do you feel?), then the report.
"""
from functools import lru_cache

import cv2
import numpy as np

from game import spells as magic
from game import report
from game.battle import CAST_SECONDS, FLIGHT_SECONDS, HEAL_SECONDS, PLAYER_HEALTH
from render import (CYAN, GLOW_SCALE, GOLD, H, MARGIN, MUTED, RED, SHIELD_BLUE, W, memory_prompt, scale, small)
from sessions.grip import HOLD_SECONDS
from text import draw_text, text_size

BAR_WIDTH = 260
POPUP_SECONDS = 1.4
SHADOW_STRENGTH = 0.75     # how much of the starlight behind the enemy it swallows
ENEMY_SPELL_W, ENEMY_SPELL_H = 260, 170  # the box the enemy's constellation is drawn in
ROUND_ROWS = 8
ENEMY_GUARD_RADIUS = 100  # the ring around an enemy with its guard up
CARD_W, CARD_H, CARD_GAP = 360, 60, 12
CARDS_TOP = 216
BANNER = {"player": ("YOUR TURN", GOLD), "enemy": ("ENEMY'S TURN", RED)}


def bar_geometry(x, fraction, align):
    left = x if align == "left" else x - BAR_WIDTH
    filled = int(BAR_WIDTH * max(0.0, min(1.0, fraction)))
    return left, filled


def draw_bar_shape(frame, glow, x, y, fraction, color, align="left"):
    """A thin night-sky bar: a faint track, a glowing fill and a bright end star."""
    left, filled = bar_geometry(x, fraction, align)
    cv2.line(frame, (left, y), (left + BAR_WIDTH, y), scale(MUTED, 0.35), 3, cv2.LINE_AA)
    start, end = (left, y), (left + filled, y)
    if align == "right":  # the enemy's bar empties toward the right edge
        start, end = (left + BAR_WIDTH - filled, y), (left + BAR_WIDTH, y)
    if filled > 0:
        cv2.line(frame, start, end, color, 3, cv2.LINE_AA)
        cv2.line(glow, small(start), small(end), scale(color, 0.6), 1, cv2.LINE_AA)
        tip = start if align == "right" else end
        cv2.circle(frame, tip, 4, (235, 250, 255), -1, cv2.LINE_AA)
        cv2.circle(glow, small(tip), 2, color, -1, cv2.LINE_AA)


def draw_bar_text(frame, x, y, color, label, value, align="left"):
    draw_text(frame, label, (x, y - 32), 18, color, 600, 1.0, align)
    draw_text(frame, value, (x + (BAR_WIDTH if align == "left" else -BAR_WIDTH), y - 30), 16, MUTED, 500, 1.0,
              "right" if align == "left" else "left")


def enemy_point(cal):
    """Where the enemy is: on the side away from the reaching arm."""
    left_side = cal is not None and cal.side == "Bellatrix"
    return (W * 0.17 if left_side else W * 0.83, H * 0.42)


@lru_cache(maxsize=128)
def shadow_profile(size):
    """How strongly the enemy swallows the light at each pixel around its centre (0 to 1): a disc of
    radius `size` with soft edges. Computed once per size on a small patch, not on the whole screen."""
    pad = int(size * 2.4)
    patch = np.zeros((2 * pad + 1, 2 * pad + 1), np.float32)
    cv2.circle(patch, (pad, pad), size, 1.0, -1, cv2.LINE_AA)
    return cv2.GaussianBlur(patch, (0, 0), size / 2.5), pad


def darken_around(frame, center, size):
    """The enemy swallows the starlight behind it: darken a patch of the frame (only that patch)."""
    profile, pad = shadow_profile(size)
    cx, cy = center
    x0, y0, x1, y1 = max(cx - pad, 0), max(cy - pad, 0), min(cx + pad + 1, W), min(cy + pad + 1, H)
    if x0 >= x1 or y0 >= y1:
        return
    mask = profile[y0 - (cy - pad):y1 - (cy - pad), x0 - (cx - pad):x1 - (cx - pad), None]
    roi = frame[y0:y1, x0:x1]
    roi[:] = (roi * (1 - SHADOW_STRENGTH * mask)).astype(np.uint8)


def draw_enemy(frame, glow, config, center, health, now):
    """The enemy: a dark smudge that shrinks as it loses health, with glowing eyes in its colour;
    Scorpius also has a beating red heart."""
    size = int(40 + 50 * health)
    cx, cy = int(center[0]), int(center[1])
    darken_around(frame, (cx, cy), size)
    color = config["color"]
    blink = 0.7 + 0.3 * np.sin(now * 3)
    eyes = config["eyes"]
    for k in range(eyes):
        dx = int((k - (eyes - 1) / 2) * size / 2.5)
        eye = (cx + dx, cy - size // 6)
        cv2.circle(frame, eye, 4, scale(color, blink), -1, cv2.LINE_AA)
        cv2.circle(glow, small(eye), 2, scale(color, blink), -1, cv2.LINE_AA)
    if config.get("heart"):
        beat = 0.5 + 0.5 * np.sin(now * 5)
        cv2.circle(frame, (cx, cy), int(14 + 6 * beat), scale(color, 0.4 + 0.4 * beat), 2, cv2.LINE_AA)
        cv2.circle(glow, small((cx, cy)), 4, scale(color, 0.4 + 0.4 * beat), -1, cv2.LINE_AA)


def wrap(text, size, weight, width):
    """Split text into lines that fit in `width` pixels."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and text_size(trial, size, weight)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def draw_text_block(frame, text, x, y, size, color, weight, width, step, opacity=1.0, align="left"):
    """Wrapped text; returns the y below it."""
    for line in wrap(text, size, weight, width):
        draw_text(frame, line, (x, y), size, color, weight, opacity, align)
        y += step
    return y


def enemy_spell_points(attack, center):
    """The enemy's constellation as pixels, small, centred on the enemy."""
    pts = np.array(attack["stars"], dtype=float)
    lo, span = pts.min(axis=0), np.maximum(pts.max(axis=0) - pts.min(axis=0), 1e-6)
    k = min(ENEMY_SPELL_W / span[0], ENEMY_SPELL_H / span[1])
    return [(int(center[0] + (p[0] - lo[0] - span[0] / 2) * k), int(center[1] + (p[1] - lo[1] - span[1] / 2) * k + 20))
            for p in pts]


def draw_strike(frame, glow, battle, start, end, now):
    """The enemy's attack: it traces its constellation star by star (the same kind of spell the player casts),
    then the finished shape flies at Orion as a red comet, ending in a red burst where it lands."""
    age = now - battle.phase_at
    color = battle.config["color"]
    pts = enemy_spell_points(battle.attack, start)
    shown = min(len(pts), int(len(pts) * min(1.0, age / CAST_SECONDS)) + 1)
    for a, b in zip(pts[:shown], pts[1:shown]):
        cv2.line(frame, a, b, scale(color, 0.7), 2, cv2.LINE_AA)
        cv2.line(glow, small(a), small(b), scale(color, 0.4), 1, cv2.LINE_AA)
    for p in pts[:shown]:
        cv2.circle(frame, p, 5, color, -1, cv2.LINE_AA)
        cv2.circle(glow, small(p), 2, color, -1, cv2.LINE_AA)
    if age < CAST_SECONDS:
        return
    p = min(1.0, (age - CAST_SECONDS) / FLIGHT_SECONDS)
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


def draw_heal(frame, glow, battle, center, now):
    """The enemy heals: a cyan ring gathers in toward it."""
    p = min(1.0, (now - battle.phase_at) / HEAL_SECONDS)
    radius = int(120 * (1 - p) + 20)
    cv2.circle(frame, (int(center[0]), int(center[1])), radius, scale(CYAN, 0.8 * (1 - p * 0.5)), 2, cv2.LINE_AA)
    cv2.circle(glow, small(center), radius // GLOW_SCALE, scale(CYAN, 0.6), 1, cv2.LINE_AA)


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


def grip_prompt(grip):
    """The Block move's instructions as the Grip rep goes."""
    if grip.state == "holding":
        return f"Hold your fist... {max(0.0, HOLD_SECONDS * (1 - grip.progress)):.1f}", (CYAN, "Keep it closed")
    if grip.state == "open":
        return "Now open your hand wide", (GOLD, "Spread all five fingers to raise the shield")
    return "Block: make a fist and hold it", (CYAN, "Take your time  ·  Space gives up the block")


def prompt(battle, now):
    """The headline and the line under it for the current phase."""
    enemy = battle.config["enemy"]
    if battle.phase in ("checkin", "report"):
        return ("Victory" if battle.outcome == "won" else "Defeated"), (GOLD, ""), MUTED
    if battle.phase == "select":
        if battle.fist_since is not None:
            return "Attack or block?", (CYAN, f"Holding a fist chooses Block  ·  {int(100 * battle.fist_progress)}%"), MUTED
        guard = f"{enemy} has its guard up: spells do half  ·  " if battle.enemy_guarding else ""
        return "Attack or block?", (GOLD, battle.message or guard + "1-8 attack  ·  B or hold a fist to block"), MUTED
    if battle.phase == "player":
        reach = battle.reach
        lit, total = len(reach.lit_at), len(reach.points or reach.stars)
        detail = memory_prompt(reach, now) or f"Reach far for more power  ·  power {battle.power}  ·  it lands when you finish"
        return f"Cast {battle.spell.name}  ·  {lit} of {total}", (GOLD, detail), CYAN if reach.assisted is False else MUTED
    if battle.phase == "guard":
        headline, detail = grip_prompt(battle.grip)
        return headline, detail, MUTED
    if battle.phase == "result":
        if battle.round.move == "block":
            return battle.message, (CYAN if battle.shield else RED, "The enemy attacks next"), MUTED
        return battle.message, (GOLD, f"{battle.round.damage} damage"), MUTED
    if battle.phase == "strike":
        shield = {"full": "Your shield is up", "cracked": "Your cracked shield will take half"}.get(battle.shield, "No shield")
        return f"{enemy} casts {battle.attack['name']}!", (RED, f"{battle.attack['damage']} damage  ·  {shield}"), MUTED
    if battle.phase in ("heal", "brace"):
        return battle.message, (CYAN, ""), MUTED
    if battle.phase == "pause":
        good = battle.message == "Blocked!"
        return battle.message, (CYAN if good else RED, ""), MUTED
    if battle.phase == "won":
        unlocked = ("Unlocked: " + ", ".join(s.name for s in battle.new_spells)) if battle.new_spells else ""
        return f"{enemy} is defeated", (GOLD, unlocked), CYAN
    return "Orion is knocked down", (RED, "Rest a moment. Every reach still counted"), MUTED


def spell_card(frame, glow, x, y, number, spell, book, wins, now):
    """One spell in the picker: its key, name, cost, damage range and cooldown, dimmed if it can't be cast."""
    reason = book.reason_unavailable(spell)
    if reason == "Locked":
        reason = f"Win {spell.unlock_wins} battle{'s' if spell.unlock_wins != 1 else ''}"
    ok = reason is None
    k = 1.0 if ok else 0.45
    cv2.rectangle(frame, (x, y), (x + CARD_W, y + CARD_H), scale(MUTED, 0.45 * k), 1, cv2.LINE_AA)
    cv2.circle(frame, (x + 30, y + CARD_H // 2), 18, scale(CYAN, k), 2, cv2.LINE_AA)
    draw_text(frame, str(number), (x + 30, y + CARD_H // 2 - 13), 20, CYAN, 600, k, "center")
    draw_text(frame, spell.name, (x + 62, y + 6), 22, GOLD, 600, k)
    low, high = spell.damage
    draw_text(frame, f"cost {spell.cost}  ·  dmg {low}-{high}  ·  cooldown {spell.cooldown}", (x + 62, y + 36), 15,
              SHIELD_BLUE if ok else MUTED, 400, k)
    if not ok:
        draw_text(frame, reason, (x + CARD_W - 12, y + 8), 15, RED, 500, 0.9, "right")


def draw_picker(frame, glow, battle, now):
    """The spell picker: every spell as a card in two columns, then the rest option."""
    left = W // 2 - CARD_W - CARD_GAP // 2
    rows = (len(magic.SPELLS) + 1) // 2
    panel = frame[CARDS_TOP - 14:CARDS_TOP + rows * (CARD_H + CARD_GAP) + 22, left - 20:left + 2 * CARD_W + CARD_GAP + 20]
    panel[:] = (panel * 0.4).astype(np.uint8)
    for i, spell in enumerate(magic.SPELLS):
        x = left + (i % 2) * (CARD_W + CARD_GAP)
        y = CARDS_TOP + (i // 2) * (CARD_H + CARD_GAP)
        spell_card(frame, glow, x, y, i + 1, spell, battle.book, battle.wins, now)
    y = CARDS_TOP + rows * (CARD_H + CARD_GAP)
    draw_text(frame, f"B  Block: one fist hold raises a shield    ·    0  Rest: +{magic.REST_MANA} mana", (W // 2, y), 17,
              CYAN, 500, 1.0, "center")


def draw_turn_banner(frame, battle):
    """Whose turn it is, at all times."""
    turn = battle.turn
    text, color = BANNER[turn] if turn else (("VICTORY", GOLD) if battle.outcome == "won" else ("DEFEATED", RED))
    draw_text(frame, text, (W // 2, 8), 20, color, 600, 1.0, "center")


TIP_PHASES = ("result", "pause", "heal", "brace")  # after each move, a tip for the patient
WHITE = (235, 245, 255)
VERDICT_COLORS = {"better": CYAN, "worse": RED, "same": MUTED}
VERDICT_WORDS = {"better": "better", "worse": "not as good", "same": "about the same"}


def draw_tip(frame, battle):
    """After each move: one tip for getting better at the movement."""
    if battle.phase not in TIP_PHASES or battle.round is None:
        return
    tip = report.round_tip(battle.round)
    draw_text(frame, "TIP", (W // 2, MARGIN + 66), 14, CYAN, 600, 0.9, "center")
    draw_text_block(frame, tip, W // 2, MARGIN + 86, 16, CYAN, 400, 600, 21, 0.95, "center")


def draw_shields(frame, glow, battle, figure, enemy, now):
    """The player's shield around Orion through the enemy's turn, and the enemy's guard around it."""
    if battle.shield and battle.turn == "enemy":
        center = tuple(int(v) for v in battle.player_point(figure))
        k = 0.8 if battle.shield == "full" else 0.4
        cv2.circle(frame, center, 150, scale(SHIELD_BLUE, k), 3 if battle.shield == "full" else 1, cv2.LINE_AA)
        cv2.circle(glow, small(center), 150 // GLOW_SCALE, scale(SHIELD_BLUE, 0.5 * k), 1, cv2.LINE_AA)
    if battle.enemy_guarding:
        pulse = 0.6 + 0.2 * np.sin(now * 3)
        c = (int(enemy[0]), int(enemy[1]))
        cv2.circle(frame, c, ENEMY_GUARD_RADIUS, scale(battle.config["color"], pulse), 2, cv2.LINE_AA)
        cv2.circle(glow, small(c), ENEMY_GUARD_RADIUS // GLOW_SCALE, scale(battle.config["color"], 0.4), 1, cv2.LINE_AA)


def draw_checkin(frame, battle):
    """After the battle: how does the patient feel? Three questions, answered with 1 to 5."""
    q = battle.question
    if q is None:
        return
    key, question, answers = q
    number = [c[0] for c in report.CHECKIN].index(key) + 1
    panel = frame[150:560, 190:W - 190]
    panel[:] = (panel * 0.25).astype(np.uint8)
    draw_text(frame, f"How are you feeling?  ·  question {number} of {len(report.CHECKIN)}", (W // 2, 176), 18, MUTED, 500, 1.0, "center")
    draw_text(frame, question, (W // 2, 214), 32, GOLD, 600, 1.0, "center")
    width = 170
    left = W // 2 - (5 * width) // 2
    for i, answer in enumerate(answers):
        x = left + i * width + width // 2
        cv2.circle(frame, (x, 336), 30, scale(CYAN, 0.9), 2, cv2.LINE_AA)
        draw_text(frame, str(i + 1), (x, 320), 28, CYAN, 600, 1.0, "center")
        draw_text(frame, answer, (x, 384), 18, WHITE, 500, 1.0, "center")
    draw_text(frame, "Press a number  ·  S to skip", (W // 2, 450), 17, MUTED, 400, 1.0, "center")
    draw_text(frame, "Your answers go to your therapist with today's results.", (W // 2, 490), 15, MUTED, 400, 0.9, "center")


def draw_report(frame, battle):
    """After a battle: page 1 the rehab measures, how you felt and round by round; page 2 how to improve."""
    won = battle.outcome == "won"
    stats = report.battle_stats(battle.rounds)
    panel = frame[40:690, 70:W - 70]
    panel[:] = (panel * 0.25).astype(np.uint8)  # darken behind the report so it reads clearly
    title = f"Victory over {battle.config['enemy']}" if won else f"Defeated by {battle.config['enemy']}"
    draw_text(frame, title, (W // 2, 52), 34, GOLD if won else RED, 600, 1.0, "center")
    if battle.report_page == 0:
        draw_report_results(frame, battle, stats, won)
        footer = "Enter  how to improve"
    else:
        draw_report_tips(frame, battle, stats, won)
        footer = "Enter  next battle" if won else "Enter  try again  ·  M start screen"
    draw_text(frame, footer, (W // 2, 656), 17, CYAN, 500, 1.0, "center")


def draw_report_results(frame, battle, stats, won):
    """Rehab measures with today against the recent average, the check-in, rounds, and the conclusion."""
    session, earlier = battle.session, battle.history or []
    draw_text(frame, "Today's therapy measures", (110, 104), 20, GOLD, 600, 1.0)
    draw_text(frame, "today", (380, 108), 13, MUTED, 500, 1.0)
    draw_text(frame, f"vs last {min(len(earlier), 5) or 0}", (470, 108), 13, MUTED, 500, 1.0)
    y = 134
    rows = report.findings(session, earlier) if session is not None else []
    for metric, value, before, verdict in rows:
        draw_text(frame, metric.label, (110, y), 16, MUTED, 400, 1.0)
        draw_text(frame, metric.fmt.format(value), (380, y), 16, GOLD, 600, 1.0)
        if before is not None:
            draw_text(frame, f"{VERDICT_WORDS[verdict]} ({metric.fmt.format(before)})", (470, y), 14,
                      VERDICT_COLORS[verdict], 500, 1.0)
        y += 25
    draw_text(frame, f"Reaches {stats['stars hit']}  ·  grip reps {stats['blocks made']}  ·  lean warnings {session.lean_warnings if session else 0}",
              (110, y + 6), 15, WHITE, 500, 1.0)
    if battle.checkin:
        answers = []
        for key, _, options in report.CHECKIN:
            if key in battle.checkin:
                answers.append(f"{key} {options[battle.checkin[key] - 1].lower()}")
        draw_text(frame, "You felt: " + "  ·  ".join(answers), (110, y + 32), 15,
                  RED if battle.checkin.get("pain", 0) >= report.PAIN_ALERT else CYAN, 500, 1.0)
    draw_text(frame, "Round by round", (720, 104), 20, GOLD, 600, 1.0)
    for i, r in enumerate(battle.rounds[-ROUND_ROWS:]):
        ry = 134 + i * 38
        outcome = report.enemy_outcome(r)
        label = {"attack": r.spell, "block": "Block", "rest": "Rest"}.get(r.move, "-")
        draw_text(frame, f"{r.number}", (720, ry), 15, MUTED, 600, 1.0)
        draw_text(frame, label, (742, ry), 15, SHIELD_BLUE if r.move == "block" else GOLD, 600, 1.0)
        if r.damage:
            draw_text(frame, f"-{r.damage}", (840, ry), 15, GOLD, 500, 1.0)
        draw_text(frame, report.round_conclusion(r, with_block=False), (890, ry), 13, MUTED, 400, 1.0)
        draw_text(frame, "Enemy: " + outcome, (890, ry + 16), 12, RED if "hit you" in outcome else CYAN, 400, 0.9)
    draw_text(frame, "Conclusion", (110, 470), 20, GOLD, 600, 1.0)
    cy = 502
    for line in report.general_conclusion(stats, session, won, battle.checkin, earlier):
        cy = draw_text_block(frame, line, 110, cy, 16, WHITE, 400, W - 240, 22)
    if battle.new_spells:
        draw_text(frame, "Unlocked: " + ", ".join(s.name for s in battle.new_spells), (W - 110, 470), 16, CYAN, 600, 1.0, "right")


def draw_report_tips(frame, battle, stats, won):
    draw_text(frame, "How to improve", (110, 104), 22, GOLD, 600, 1.0)
    y = 142
    for tip in report.rehab_tips(battle.session, battle.checkin, won, stats):
        draw_text(frame, "•", (110, y), 17, CYAN, 600, 1.0)
        y = draw_text_block(frame, tip, 134, y, 17, WHITE, 400, W - 300, 24) + 8
    draw_text(frame, "Move by move", (110, y + 12), 20, GOLD, 600, 1.0)
    y += 46
    seen = set()
    for r in battle.rounds:
        tip = report.round_tip(r)
        if tip in seen or y > 615:
            continue
        seen.add(tip)
        draw_text(frame, f"Round {r.number}", (110, y), 14, MUTED, 600, 1.0)
        y = draw_text_block(frame, tip, 190, y, 14, MUTED, 400, W - 360, 19) + 4


def draw_battle_world(frame, glow, play, figure, hands, now):
    """The battle's light: the enemy, strike, heal, shields and Grip ring, plus the bar shapes. Goes before the glow pass."""
    battle = play.battle
    if play.victory or battle is None:
        return
    enemy = enemy_point(play.calibration)
    health = battle.enemy_health / battle.enemy_max
    if battle.outcome != "won":
        draw_enemy(frame, glow, battle.config, enemy, health, now)
    if battle.phase == "strike":
        draw_strike(frame, glow, battle, enemy, battle.player_point(figure), now)
    if battle.phase == "heal":
        draw_heal(frame, glow, battle, enemy, now)
    if battle.phase == "guard":
        draw_grip(frame, glow, battle, hands, now)
    draw_shields(frame, glow, battle, figure, enemy, now)
    if battle.phase in ("checkin", "report"):  # those screens cover the battle
        return
    draw_bar_shape(frame, glow, MARGIN, 128, battle.player_health / PLAYER_HEALTH, GOLD)
    draw_bar_shape(frame, glow, W - MARGIN, 128, health, RED, "right")
    draw_bar_shape(frame, glow, MARGIN, 176, battle.book.mana / magic.MAX_MANA, SHIELD_BLUE)


def draw_battle_hud(frame, play, now):
    """The battle's text and menus, drawn after the glow so they stay crisp."""
    if play.victory:
        draw_text(frame, "The sky is yours", (W // 2, H // 2 - 60), 56, GOLD, 600, 1.0, "center")
        draw_text(frame, "Every battle won. M for the start screen", (W // 2, H // 2 + 20), 22, MUTED, 400, 1.0, "center")
        return
    battle = play.battle
    if battle is None:
        return
    health = battle.enemy_health / battle.enemy_max
    if battle.phase in ("checkin", "report"):  # these have the screen to themselves
        draw_turn_banner(frame, battle)
        (draw_checkin if battle.phase == "checkin" else draw_report)(frame, battle)
        return
    draw_bar_text(frame, MARGIN, 128, GOLD, "Orion", f"{battle.player_health} / {PLAYER_HEALTH}")
    draw_bar_text(frame, W - MARGIN, 128, RED, battle.config["enemy"], f"{battle.enemy_health} / {battle.enemy_max}", "right")
    draw_bar_text(frame, MARGIN, 176, SHIELD_BLUE, "Mana", f"{battle.book.mana} / {magic.MAX_MANA}")
    if battle.enemy_guarding:
        draw_text(frame, "Guard up: your spells do half", (W - MARGIN, 140), 14, battle.config["color"], 500, 1.0, "right")
    draw_turn_banner(frame, battle)
    headline, (color, detail), detail_color = prompt(battle, now)
    draw_text(frame, headline, (W // 2, MARGIN - 4), 28, color, 600, 1.0, "center")
    if detail:
        draw_text(frame, detail, (W // 2, MARGIN + 36), 17, detail_color, 400, 0.9, "center")
    if battle.phase == "select":
        draw_picker(frame, None, battle, now)
    draw_tip(frame, battle)
    draw_popups(frame, battle, now)

"""Battle: Orion against an enemy, turn by turn. Nothing is ever timed; every turn waits for the player.

  player  - draw the battle's constellation with Reach; each star lit deals damage
  strike  - the enemy attacks (ATTACK and a short animation)
  block   - the player answers with one Grip rep: a full rep blocks (SHIELD), opening early takes the hit
  won     - the constellation joins the sky (WIN); lost - Orion is knocked down (R tries again)

Damage per star = BASE_DAMAGE x reach quality x form:
  reach quality: 0.5 for stars within 80% of the calibrated reach, rising to 1.5 at the full reach
                 and beyond, so the far stars do the most damage
  form:          0.5 if a lean warning fired since the previous star, otherwise 1
"""
import numpy as np

import events
from sessions.grip import Grip
from sessions.reach import Reach, load_constellation

BASE_DAMAGE = 12
QUALITY_FROM = 0.8        # stars past this share of the calibrated reach start to do extra damage
LEAN_PENALTY = 0.5        # damage multiplier when the player leaned on that star
PLAYER_HEALTH = 100
STRIKE_SECONDS = 1.6      # length of the enemy's attack animation
PAUSE_SECONDS = 1.5       # a beat to read "Blocked!" or the damage before the next turn
WON_SECONDS = 6.0         # how long the win is shown before moving on
RED = (107, 107, 255)     # #FF6B6B in BGR: Scorpius is drawn in the warning red

BATTLES = [
    {"title": "Warm-up", "enemy": "The shadow", "health": 50, "strike": 10,
     "constellation": "orion", "enemy_stars": None},
    {"title": "Scorpius", "enemy": "Scorpius", "health": 180, "strike": 25,
     "constellation": "scorpius", "enemy_stars": RED},
]


def reach_quality(star, cal):
    """0.5 within 80% of the calibrated reach, rising to 1.5 at the full reach and beyond."""
    ratio = np.hypot(*(np.array(star) - np.array(cal.shoulder))) / (cal.reach * cal.width)
    return 0.5 + float(np.clip((ratio - QUALITY_FROM) / (1 - QUALITY_FROM), 0.0, 1.0))


def star_damage(star, cal, leaned):
    """Damage for one star: base x reach quality x form."""
    return round(BASE_DAMAGE * reach_quality(star, cal) * (LEAN_PENALTY if leaned else 1.0))


class Battle:
    def __init__(self, config, size):
        self.config = config
        self.size = size
        self.constellation = load_constellation(f"constellations/{config['constellation']}.json")
        self.enemy_health = self.enemy_max = config["health"]
        self.player_health = PLAYER_HEALTH
        self.popups = []       # floating numbers: (pixel position, text, color, time)
        self.message = ""      # the latest outcome, e.g. "Blocked!"
        self.start_turn(None)

    def start_turn(self, now):
        """The player's turn: a fresh drawing of the constellation."""
        self.phase, self.phase_at = "player", now
        self.reach = Reach(self.constellation, self.size, celebrate=False, unlit_color=self.config["enemy_stars"])
        self.grip = None
        self.lit = 0
        self.star_started = now  # lean warnings after this time count against the next star

    def update(self, hands, pose, figure, camera_rect, now, cal, guard, blocked):
        """Advance the battle by one frame."""
        if self.star_started is None:
            self.star_started = now
        if self.phase == "player":
            self.player_turn(hands, pose, figure, camera_rect, now, cal, guard, blocked)
        elif self.phase == "strike" and now - self.phase_at >= STRIKE_SECONDS:
            self.phase, self.phase_at, self.grip = "block", now, Grip()
        elif self.phase == "block":
            self.block_turn(hands, now, figure)
        elif self.phase == "pause" and now - self.phase_at >= PAUSE_SECONDS:
            self.start_turn(now)

    def player_turn(self, hands, pose, figure, camera_rect, now, cal, guard, blocked):
        """Draw with Reach; every newly lit star hurts the enemy. When the drawing is done, win or the enemy strikes."""
        self.reach.update(hands, pose, figure, camera_rect, now, cal, blocked)
        while self.lit < len(self.reach.lit_at):
            star = self.reach.points[self.lit]
            leaned = guard.last_warn >= self.star_started
            damage = star_damage(star, cal, leaned)
            self.enemy_health = max(0, self.enemy_health - damage)
            self.popups.append((star, f"-{damage}" + ("  leaned" if leaned else ""), RED if leaned else None, now))
            self.lit += 1
            self.star_started = now
        if self.reach.won_at is None:
            return
        if self.enemy_health <= 0:
            self.phase, self.phase_at = "won", now
            events.emit("WIN")
        else:
            self.phase, self.phase_at = "strike", now
            events.emit("ATTACK")

    def block_turn(self, hands, now, figure):
        """Wait for one Grip rep: a full rep blocks the strike, opening early lets it land."""
        self.grip.update(hands, now)
        if self.grip.result == "block":
            events.emit("SHIELD", pos=self.player_point(figure))
            self.message = "Blocked!"
            self.phase, self.phase_at = "pause", now
        elif self.grip.result == "early":
            self.take_hit(now, figure, "Opened too soon: the strike lands")

    def take_hit(self, now, figure, message):
        """The enemy's strike lands: lose health, and either continue or be knocked down."""
        self.player_health = max(0, self.player_health - self.config["strike"])
        self.popups.append((self.player_point(figure), f"-{self.config['strike']}", RED, now))
        self.message = message
        self.phase, self.phase_at = ("lost" if self.player_health <= 0 else "pause"), now

    def skip_block(self, now, figure):
        """Space during the block: take the hit without doing a Grip rep."""
        if self.phase == "block":
            self.take_hit(now, figure, "You took the hit")

    def player_point(self, figure):
        """Middle of Orion's shoulders on screen (where the shield and hits appear), in pixels."""
        if figure is None:
            return (self.size[0] / 2, self.size[1] / 2)
        (lx, ly), (rx, ry) = figure.stars["Betelgeuse"], figure.stars["Bellatrix"]
        return ((lx + rx) / 2 * self.size[0], (ly + ry) / 2 * self.size[1])

    def finished(self, now):
        """True once a win has been shown long enough to move on."""
        return self.phase == "won" and now - self.phase_at >= WON_SECONDS

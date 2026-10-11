"""Difficulty: Easy, Normal or Hard. Pure data and small functions, nothing drawn here.

Safety rule for a rehab game: the stars never sit beyond what the patient showed they can reach.
Easy sits at 80% of the calibrated reach, Normal at 95%, Hard at up to 110% (MAX_REACH_FRACTION is
the absolute ceiling; no setting can go past it). The player also gets a bigger target on Easy.
"""
from dataclasses import dataclass

MAX_REACH_FRACTION = 1.10   # no difficulty may place a star farther than this share of the calibrated reach


@dataclass(frozen=True)
class Difficulty:
    name: str
    reach_edge: float            # how far the outer stars sit, as a share of the calibrated reach
    hit_radius: int              # pixels: how close the fingertip must be to a star
    health_scale: float          # multiplies enemy health
    strike_scale: float          # multiplies the damage of an enemy strike
    mana_refill: int             # mana regained at the start of each player turn
    double_strike_chance: float  # chance an enemy turn is two strikes in a row
    heal_chance: float           # chance an enemy turn is a heal instead of a strike
    enemy_guard_chance: float = 0.2   # chance an enemy turn is a guard (halves the player's next spell)


EASY = Difficulty("Easy", 0.80, 60, 0.7, 0.7, 35, 0.0, 0.0, 0.10)
NORMAL = Difficulty("Normal", 0.95, 48, 1.0, 1.0, 25, 0.0, 0.0, 0.20)
HARD = Difficulty("Hard", 1.10, 40, 1.3, 1.3, 15, 0.25, 0.20, 0.30)
DIFFICULTIES = (EASY, NORMAL, HARD)
HEAL_FRACTION = 0.12        # a heal restores this share of the enemy's maximum health


def by_name(name):
    """The difficulty with this name; unknown names fall back to Normal."""
    return next((d for d in DIFFICULTIES if d.name == name), NORMAL)


def next_difficulty(difficulty):
    """The next one in the cycle Easy, Normal, Hard, Easy..."""
    return DIFFICULTIES[(DIFFICULTIES.index(difficulty) + 1) % len(DIFFICULTIES)]


def reach_fraction(difficulty):
    """The share of the calibrated reach the outer stars may use, never above the ceiling."""
    return min(difficulty.reach_edge, MAX_REACH_FRACTION)


def reach_limit(cal, difficulty):
    """The farthest a star may sit from the reaching shoulder, in pixels."""
    return cal.reach * cal.width * reach_fraction(difficulty)


def enemy_health(base, difficulty):
    return max(1, round(base * difficulty.health_scale))


def strike_damage(base, difficulty):
    return max(1, round(base * difficulty.strike_scale))


def choose_enemy_action(roll, difficulty):
    """What the enemy does this turn, from one random number in [0, 1): heal, a double attack, guard, or
    attack. Like the player, the enemy either attacks or blocks; only Hard enemies heal or attack twice."""
    edges = (("heal", difficulty.heal_chance), ("double", difficulty.double_strike_chance),
             ("guard", difficulty.enemy_guard_chance))
    total = 0.0
    for action, chance in edges:
        total += chance
        if roll < total:
            return action
    return "strike"

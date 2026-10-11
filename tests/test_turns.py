"""Turns, like a Pokemon fight: each turn a side attacks or blocks. Damage lands only when the whole
constellation is drawn; Block is a Grip rep on your own turn that shields you from the enemy's next attack;
the enemy also attacks, guards (halving your next spell), or on Hard heals or attacks twice.
Run: .venv/bin/python -m unittest"""
import unittest

import events
from game import battle as battle_module
from game import turns
from game.battle import (BATTLES, FIST_CHOOSES_BLOCK, GUARD_FACTOR, RESULT_SECONDS, STRIKE_SECONDS, BRACE_SECONDS,
                         PAUSE_SECONDS, Battle)
from game.difficulty import EASY, HARD, NORMAL
from sessions import grip as grip_module
from tests.helpers import CAL, FIGURE, QuietGuard, SIZE, WHOLE_VIEW, hand_at

ATTACK, GUARD, HEAL, DOUBLE = 0.99, None, 0.05, 0.30   # rolls for the enemy's action (see roll_for)


class ScriptedRng:
    """random() answers from a list (repeating the last one); choice() takes the first item."""

    def __init__(self, rolls):
        self.rolls = list(rolls)

    def random(self):
        return self.rolls.pop(0) if len(self.rolls) > 1 else self.rolls[0]

    def choice(self, items):
        return items[0]


def guard_roll(d):
    """A roll that makes this difficulty's enemy guard."""
    return d.heal_chance + d.double_strike_chance + d.enemy_guard_chance / 2


def new_battle(difficulty=NORMAL, rolls=(ATTACK,), index=1, **kwargs):
    return Battle(BATTLES[index], SIZE, difficulty, rng=ScriptedRng(rolls), **kwargs)


def step(battle, now, hands=(), blocked=False):
    battle.update(list(hands), None, FIGURE, WHOLE_VIEW, now, CAL, QuietGuard(), blocked)


def touch(battle, point, now):
    for t in (0.0, 0.2, 0.4):
        step(battle, now + t, hand_at(*point))


def draw_all_but_last(battle, spell_index, now=0.0):
    battle.choose(spell_index, now)
    step(battle, now)  # places the stars
    for point in battle.reach.points[:-1]:
        touch(battle, point, now)
        now += 1.0
    return now


def finish_drawing(battle, now):
    touch(battle, battle.reach.points[-1], now)
    return now + 1.0


def cast_and_finish(battle, spell_index, now=0.0):
    return finish_drawing(battle, draw_all_but_last(battle, spell_index, now))


def to_enemy_turn(battle, now):
    now += RESULT_SECONDS + 0.1
    step(battle, now)
    return now


def hand_with_openness(value):
    """A hand whose openness (see grip.py) is about `value`."""
    hand = hand_at(640, 360)[0]
    for lm in hand:
        lm.x, lm.y = 0.5, 0.5
    hand[9].y = 0.45                        # palm length 0.05
    for tip in grip_module.FINGERTIPS:
        hand[tip].x, hand[tip].y = 0.5, 0.5 - 0.05 * value
    return [hand]


FIST, OPEN = hand_with_openness(0.9), hand_with_openness(1.9)


def full_grip(battle, now):
    """Do one complete Grip rep: fist, hold, open wide. Returns the time after it."""
    for t in range(0, int((grip_module.HOLD_SECONDS + 0.2) * 10) + 1):
        step(battle, now + t / 10, FIST)
    now += grip_module.HOLD_SECONDS + 0.4
    step(battle, now, OPEN)
    return now


class TurnRulesTest(unittest.TestCase):
    def test_whose_turn_each_phase_is(self):
        self.assertEqual([turns.whose_turn(p) for p in ("select", "player", "guard", "result")], ["player"] * 4)
        self.assertEqual([turns.whose_turn(p) for p in ("strike", "brace", "heal", "pause")], ["enemy"] * 4)
        for phase in ("won", "lost", "checkin", "report"):
            self.assertIsNone(turns.whose_turn(phase))
        phases = ("select", "player", "guard", "result", "strike", "brace", "heal", "pause")
        self.assertEqual([p for p in phases if turns.can_attack(p)], ["player"])
        self.assertEqual([p for p in phases if turns.can_block(p)], ["guard"])

    def test_nothing_can_be_attacked_before_a_spell_is_chosen(self):
        battle = new_battle()
        self.assertEqual((battle.phase, battle.turn, battle.reach), ("select", "player", None))
        step(battle, 0.0, hand_at(640, 360))
        self.assertEqual(battle.enemy_health, battle.enemy_max)

    def test_stars_do_nothing_on_the_enemys_turn(self):
        battle = new_battle()
        end = to_enemy_turn(battle, cast_and_finish(battle, 0))
        self.assertEqual(battle.turn, "enemy")
        health = battle.enemy_health
        for point in battle.reach.points:
            touch(battle, point, end)
        self.assertEqual(battle.enemy_health, health)
        self.assertIsNone(battle.reach.target_index())

    def test_you_attack_or_block_not_both(self):
        battle = new_battle()
        battle.choose(0, 0.0)
        battle.block(0.1)  # already attacking: Block is refused
        self.assertEqual((battle.phase, battle.round.move), ("player", "attack"))
        other = new_battle()
        other.block(0.0)
        other.choose(0, 0.1)  # already blocking: no spell
        self.assertEqual((other.phase, other.round.move, other.spell), ("guard", "block", None))

    def test_a_grip_on_the_enemys_turn_does_nothing(self):
        battle = new_battle()
        end = to_enemy_turn(battle, cast_and_finish(battle, 0))
        battle.block(end)
        battle.lower_guard(end, FIGURE)
        self.assertEqual((battle.phase, battle.shield), ("strike", None))

    def test_last_turns_effects_are_cleared_when_the_next_turn_starts(self):
        events.emit("SHIELD")
        battle = new_battle()
        self.assertEqual(events.active_effects(), [])
        events.emit("ATTACK")
        battle.start_turn(1.0)
        self.assertEqual(events.active_effects(), [])


class AttackTest(unittest.TestCase):
    def test_no_damage_while_the_constellation_is_unfinished(self):
        battle = new_battle()
        draw_all_but_last(battle, 0)
        self.assertEqual(battle.enemy_health, battle.enemy_max)
        self.assertGreater(battle.power, 0)
        self.assertEqual(battle.popups, [])

    def test_the_whole_damage_lands_at_once_when_the_last_star_is_lit(self):
        battle = new_battle()
        now = draw_all_but_last(battle, 0)
        before = battle.power
        finish_drawing(battle, now)
        self.assertEqual(battle.phase, "result")
        self.assertGreater(battle.power, before)
        self.assertEqual(battle.enemy_health, battle.enemy_max - battle.power)
        self.assertEqual(battle.round.damage, battle.power)

    def test_an_attack_with_no_shield_takes_the_enemys_full_hit(self):
        battle = new_battle()
        end = to_enemy_turn(battle, cast_and_finish(battle, 0))
        step(battle, end + STRIKE_SECONDS + 0.1)
        self.assertEqual(battle.player_health, 100 - battle.attack["damage"])
        self.assertEqual(battle.round.results, ["hit"])

    def test_a_finished_spell_that_kills_the_enemy_wins_after_the_result(self):
        battle = new_battle(index=0)
        battle.enemy_health = 1
        end = cast_and_finish(battle, 0)
        self.assertEqual(battle.phase, "result")
        step(battle, end + RESULT_SECONDS + 0.1)
        self.assertEqual((battle.phase, battle.outcome, battle.turn), ("won", "won", None))

    def test_movement_quality_is_copied_into_the_round(self):
        battle = new_battle()
        cast_and_finish(battle, 0)
        r = battle.round
        self.assertEqual(len(r.straightness), r.stars)
        self.assertEqual(len(r.move_seconds), r.stars)
        self.assertTrue(all(0 <= s <= 1 for s in r.straightness))


class BlockTest(unittest.TestCase):
    def test_a_full_grip_raises_a_full_shield_that_stops_the_attack(self):
        battle = new_battle()
        battle.block(0.0)
        end = full_grip(battle, 0.0)
        self.assertEqual((battle.phase, battle.shield, battle.round.grip_held), ("result", "full", True))
        self.assertIsNotNone(battle.round.open_seconds)
        end = to_enemy_turn(battle, end)
        self.assertEqual(battle.phase, "strike")
        step(battle, end + STRIKE_SECONDS + 0.1)
        self.assertEqual((battle.player_health, battle.round.results, battle.message), (100, ["blocked"], "Blocked!"))

    def test_opening_early_gives_a_cracked_shield_that_takes_half(self):
        battle = new_battle()
        battle.block(0.0)
        step(battle, 0.0, FIST)
        step(battle, 0.5, FIST)
        step(battle, 1.0, OPEN)  # opened before the 3-second hold
        self.assertEqual((battle.phase, battle.shield), ("result", "cracked"))
        end = to_enemy_turn(battle, 1.0)
        step(battle, end + STRIKE_SECONDS + 0.1)
        self.assertEqual(battle.player_health, 100 - round(battle.attack["damage"] * GUARD_FACTOR))
        self.assertEqual(battle.round.results, ["half"])

    def test_the_shield_lasts_only_through_the_enemys_next_turn(self):
        battle = new_battle()
        battle.block(0.0)
        end = to_enemy_turn(battle, full_grip(battle, 0.0))
        step(battle, end + STRIKE_SECONDS + 0.1)
        step(battle, end + STRIKE_SECONDS + PAUSE_SECONDS + 0.2)
        self.assertEqual((battle.phase, battle.shield), ("select", None))

    def test_holding_a_fist_on_the_select_screen_chooses_block(self):
        battle = new_battle()
        step(battle, 0.0, FIST)
        self.assertGreater(battle.fist_since, -1)
        step(battle, FIST_CHOOSES_BLOCK + 0.05, FIST)
        self.assertEqual((battle.phase, battle.round.move), ("guard", "block"))

    def test_opening_the_hand_on_the_select_screen_resets_the_fist(self):
        battle = new_battle()
        step(battle, 0.0, FIST)
        step(battle, 0.5, OPEN)
        self.assertIsNone(battle.fist_since)
        step(battle, FIST_CHOOSES_BLOCK + 1, [])
        self.assertEqual(battle.phase, "select")

    def test_each_block_keeps_its_grip_for_the_session_log(self):
        battle = new_battle()
        battle.block(0.0)
        full_grip(battle, 0.0)
        self.assertEqual(len(battle.grips), 1)
        self.assertEqual(battle.grips[0].result, "block")


class EnemyTurnTest(unittest.TestCase):
    def test_the_enemy_casts_one_of_its_own_constellations(self):
        battle = new_battle(index=1)
        to_enemy_turn(battle, cast_and_finish(battle, 0))
        self.assertEqual(battle.attack["name"], "Scorpius")
        self.assertEqual(len(battle.attack["stars"]), 10)
        self.assertEqual(battle.round.attacks, ["Scorpius"])

    def test_the_enemy_can_guard_and_halve_your_next_spell(self):
        battle = new_battle(rolls=(guard_roll(NORMAL), ATTACK))
        end = to_enemy_turn(battle, cast_and_finish(battle, 0))
        self.assertEqual((battle.phase, battle.turn, battle.enemy_guarding), ("brace", "enemy", True))
        step(battle, end + BRACE_SECONDS + 0.1)
        step(battle, end + BRACE_SECONDS + PAUSE_SECONDS + 0.2)
        self.assertEqual(battle.phase, "select")
        health = battle.enemy_health
        cast_and_finish(battle, 1, end + 10)
        self.assertTrue(battle.round.enemy_blocked)
        self.assertEqual(battle.round.damage, round(battle.power * GUARD_FACTOR))
        self.assertEqual(battle.enemy_health, health - battle.round.damage)
        self.assertFalse(battle.enemy_guarding)  # used up

    def test_bigger_enemy_constellations_hit_harder(self):
        self.assertEqual(battle_module.attack_damage(25, 4), 11)
        self.assertEqual(battle_module.attack_damage(25, 10), 21)
        self.assertLess(battle_module.attack_damage(25, 4), battle_module.attack_damage(25, 10))

    def test_every_battles_attacks_exist(self):
        for config in BATTLES:
            self.assertTrue(config["attacks"])
            Battle(config, SIZE)

    def test_resting_skips_the_move_and_hands_the_turn_over(self):
        battle = new_battle()
        battle.book.mana = 40
        battle.rest(0.0)
        self.assertEqual((battle.turn, battle.phase), ("enemy", "strike"))
        self.assertEqual(battle.book.mana, 55)
        self.assertEqual(battle.round.move, "rest")


class SpellChoiceTest(unittest.TestCase):
    def test_choosing_pays_mana_and_starts_the_players_drawing(self):
        battle = new_battle()
        self.assertIsNone(battle.choose(0, 0.0))
        self.assertEqual((battle.phase, battle.spell.name, battle.book.mana), ("player", "Aries", 90))

    def test_a_locked_spell_or_a_repeat_is_refused_with_a_reason(self):
        battle = new_battle()
        self.assertEqual(battle.choose(7, 0.0), "Scorpius: Locked")
        battle.book.cooldowns["Aries"] = 1
        self.assertEqual(battle.choose(0, 0.0), "Aries: Cooldown 1")

    def test_wins_unlock_more_spells(self):
        self.assertEqual(new_battle(wins=0).choose(7, 0.0), "Scorpius: Locked")
        self.assertIsNone(new_battle(wins=6).choose(7, 0.0))

    def test_mana_refills_by_difficulty_between_turns(self):
        for d in (EASY, NORMAL, HARD):
            battle = new_battle(d)
            battle.book.mana = 20
            battle.start_turn(1.0)
            self.assertEqual(battle.book.mana, 20 + d.mana_refill)


class HardEnemyTest(unittest.TestCase):
    def test_a_hard_enemy_can_attack_twice(self):
        battle = new_battle(HARD, rolls=(DOUBLE,))
        end = to_enemy_turn(battle, cast_and_finish(battle, 0))
        self.assertEqual(battle.strikes_left, 1)
        step(battle, end + STRIKE_SECONDS + 0.1)
        step(battle, end + STRIKE_SECONDS + PAUSE_SECONDS + 0.2)
        self.assertEqual((battle.phase, battle.turn, battle.strikes_left), ("strike", "enemy", 0))

    def test_a_full_shield_stops_both_attacks(self):
        battle = new_battle(HARD, rolls=(DOUBLE,))
        battle.block(0.0)
        end = to_enemy_turn(battle, full_grip(battle, 0.0))
        for _ in range(2):
            end += STRIKE_SECONDS + 0.1
            step(battle, end)
            end += PAUSE_SECONDS + 0.1
            step(battle, end)
        self.assertEqual((battle.player_health, battle.rounds[0].results), (100, ["blocked", "blocked"]))

    def test_a_hard_enemy_can_heal(self):
        battle = new_battle(HARD, rolls=(HEAL,))
        to_enemy_turn(battle, cast_and_finish(battle, 0))
        self.assertEqual(battle.phase, "heal")
        self.assertGreater(battle.round.healed, 0)

    def test_healing_never_goes_past_full_health(self):
        battle = new_battle(HARD, rolls=(HEAL,))
        battle.enemy_health = battle.enemy_max - 1
        battle.choose(0, 0.0)
        battle.begin_enemy_turn(1.0)
        self.assertEqual(battle.enemy_health, battle.enemy_max)


class AfterTheBattleTest(unittest.TestCase):
    def test_win_then_checkin_then_a_two_page_report(self):
        battle = new_battle()
        battle.end("won", 0.0)
        step(battle, 1.0)
        self.assertEqual(battle.phase, "won")
        step(battle, battle_module.REPORT_DELAY + 0.1)
        self.assertEqual((battle.phase, battle.question[0]), ("checkin", "pain"))
        battle.answer(2)
        battle.answer(9)  # not 1 to 5: ignored
        self.assertEqual(battle.question[0], "tiredness")
        battle.answer(3)
        battle.answer(4)
        self.assertEqual((battle.phase, battle.checkin), ("report", {"pain": 2, "tiredness": 3, "mood": 4}))
        battle.dismiss()
        battle.dismiss()
        self.assertTrue(battle.finished(9.0))

    def test_the_checkin_can_be_skipped(self):
        battle = new_battle()
        battle.end("lost", 0.0)
        step(battle, battle_module.REPORT_DELAY + 0.1)
        battle.skip_checkin()
        self.assertEqual((battle.phase, battle.checkin), ("report", {}))
        battle.dismiss()
        battle.dismiss()
        self.assertFalse(battle.finished(9.0))  # a fall: play.py restarts it

    def test_dismiss_and_answers_do_nothing_mid_battle(self):
        battle = new_battle()
        battle.dismiss()
        battle.answer(3)
        self.assertEqual((battle.report_page, battle.checkin, battle.phase), (0, {}, "select"))

    def test_every_player_turn_is_a_round(self):
        battle = new_battle()
        end = to_enemy_turn(battle, cast_and_finish(battle, 0))
        step(battle, end + STRIKE_SECONDS + 0.1)
        step(battle, end + STRIKE_SECONDS + PAUSE_SECONDS + 0.2)
        self.assertEqual((len(battle.rounds), battle.phase), (2, "select"))
        self.assertEqual((battle.rounds[0].move, battle.rounds[0].spell), ("attack", "Aries"))


if __name__ == "__main__":
    unittest.main()

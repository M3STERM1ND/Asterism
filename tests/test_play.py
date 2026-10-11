"""Play: the start menu keys, the editor's key routing, and logging each finished session once.
Run: .venv\\Scripts\\python -m unittest"""
import os
import tempfile
import unittest
from unittest import mock

import play
from tests.helpers import CAL
from play import PRACTICE, Play, practice_list


class FakeView:
    frozen = False

    def camera_rect(self):
        return (0.0, 0.0, 1.0, 1.0)


def new_play():
    folder = tempfile.mkdtemp()
    return Play((1280, 720), FakeView(), settings_path=os.path.join(folder, "settings.json"),
                log_path=os.path.join(folder, "sessions.csv"))


class MenuTest(unittest.TestCase):
    def test_menu_keys(self):
        for key, mode in (("p", "battle"), ("r", "practice"), ("e", "editor"), ("t", "test"), ("g", "progress")):
            p = new_play()
            p.handle_key(ord(key))
            self.assertEqual(p.mode, mode)

    def test_editor_skips_calibration_and_m_returns_to_the_menu(self):
        p = new_play()
        p.handle_key(ord("e"))
        self.assertIsNone(p.calibrator)
        p.handle_key(ord("m"))
        self.assertEqual(p.mode, "start")

    def test_m_while_naming_is_a_letter(self):
        p = new_play()
        p.handle_key(ord("e"))
        p.handle_key(ord("n"))
        self.assertTrue(p.typing())
        p.handle_key(ord("m"))
        self.assertEqual((p.mode, p.editor.typing), ("editor", "m"))

    def test_clicks_place_stars_only_in_the_editor(self):
        p = new_play()
        p.handle_click(400, 300, 0.0)
        p.handle_key(ord("e"))
        p.handle_click(400, 300, 0.0)
        p.handle_click(600, 300, 0.0)
        p.handle_click(0, 0, 0.0, right=True)  # right-click removes the last star
        p.handle_click(700, 300, 0.0)
        self.assertEqual(p.editor.stars, [(400, 300), (700, 300)])

    def test_crafted_constellations_follow_the_zodiac(self):
        with mock.patch("play.os.listdir", return_value=["orion.json", "lyra.json", "notes.txt", "draco.json"]):
            self.assertEqual(practice_list(), PRACTICE + ["draco", "lyra"])


class SettingsMenuTest(unittest.TestCase):
    def test_d_cycles_the_difficulty_and_a_toggles_assisted_learning(self):
        p = new_play()
        self.assertEqual((p.difficulty.name, p.assisted), ("Normal", True))
        for expected in ("Hard", "Easy", "Normal"):
            p.handle_key(ord("d"))
            self.assertEqual(p.difficulty.name, expected)
        p.handle_key(ord("a"))
        self.assertFalse(p.assisted)
        self.assertEqual(p.mode, "start")

    def test_settings_are_saved_and_come_back(self):
        p = new_play()
        p.handle_key(ord("d"))
        p.handle_key(ord("a"))
        again = Play((1280, 720), FakeView(), settings_path=p.settings_path)
        self.assertEqual((again.difficulty.name, again.assisted), ("Hard", False))

    def test_d_and_a_do_nothing_outside_the_start_screen(self):
        p = new_play()
        p.handle_key(ord("e"))
        p.handle_key(ord("d"))
        p.handle_key(ord("a"))
        self.assertEqual((p.difficulty.name, p.assisted), ("Normal", True))

    def test_the_progress_screen_reads_the_log_and_m_leaves_it(self):
        p = new_play()
        with mock.patch.object(play.progress, "load_sessions", return_value=[1, 2, 3]):
            p.handle_key(ord("g"))
        self.assertEqual((p.mode, p.sessions), ("progress", [1, 2, 3]))
        p.handle_key(ord("m"))
        self.assertEqual(p.mode, "start")


class BattleFlowTest(unittest.TestCase):
    def test_the_chosen_settings_reach_the_battle_and_the_log(self):
        p = new_play()
        p.handle_key(ord("d"))  # Hard
        p.handle_key(ord("a"))  # assisted off
        p.mode = "battle"
        p.start_battle()
        self.assertEqual((p.battle.difficulty.name, p.battle.assisted), ("Hard", False))
        self.assertEqual((p.record.difficulty, p.record.assisted), ("Hard", False))

    def test_winning_a_battle_unlocks_the_next_spell_and_is_remembered(self):
        p = new_play()
        p.mode = "battle"
        p.start_battle()
        p.battle.update = lambda *args: None
        p.battle.phase, p.battle.phase_at = "won", 0.0
        with mock.patch.object(play, "append_row"):
            p.update_battle([], None, None, 1.0, False)
            p.update_battle([], None, None, 1.1, False)  # a second frame must not count the win again
        self.assertEqual(p.settings.battles_won, 1)
        self.assertEqual([s.name for s in p.battle.new_spells], ["Pisces"])
        self.assertEqual(Play((1280, 720), FakeView(), settings_path=p.settings_path).settings.battles_won, 1)

    def test_number_keys_pick_spells_only_on_the_players_turn(self):
        p = new_play()
        p.mode = "battle"
        p.calibration = CAL
        p.start_battle()
        p.handle_key(ord("1"), 0.0)
        self.assertEqual((p.battle.phase, p.battle.spell.name), ("player", "Aries"))
        p.handle_key(ord("2"), 1.0)
        self.assertEqual(p.battle.spell.name, "Aries")  # already drawing: a second pick does nothing

    def test_b_chooses_block_and_space_gives_it_up(self):
        p = new_play()
        p.mode = "battle"
        p.calibration = CAL
        p.start_battle()
        p.handle_key(ord("b"), 0.0)
        self.assertEqual((p.battle.phase, p.battle.turn, p.battle.round.move), ("guard", "player", "block"))
        p.handle_key(ord(" "), 0.5)
        self.assertEqual((p.battle.phase, p.battle.shield), ("result", None))

    def test_checkin_keys_then_enter_walks_through_the_report(self):
        p = new_play()
        p.mode = "battle"
        p.calibration = CAL
        p.start_battle()
        p.battle.end("won", 1.0)
        p.battle.phase = "checkin"
        for key in "214":  # pain, tiredness, mood
            p.handle_key(ord(key), 2.0)
        self.assertEqual(p.battle.checkin, {"pain": 2, "tiredness": 1, "mood": 4})
        self.assertEqual(p.battle.phase, "report")
        p.handle_key(13, 2.0)  # Enter: the tips page
        self.assertEqual((p.battle.report_page, p.battle.dismissed), (1, False))
        p.handle_key(ord(" "), 2.1)  # Space works too
        self.assertTrue(p.battle.dismissed)

    def test_s_skips_the_checkin_and_number_keys_do_not_cast_then(self):
        p = new_play()
        p.mode = "battle"
        p.calibration = CAL
        p.start_battle()
        p.battle.end("lost", 1.0)
        p.battle.phase = "checkin"
        p.handle_key(ord("6"), 2.0)  # out of range: ignored
        self.assertEqual(p.battle.checkin, {})
        p.handle_key(ord("s"), 2.0)
        self.assertEqual((p.battle.phase, p.battle.spell), ("report", None))

    def test_the_checkin_is_saved_on_the_battles_row(self):
        p = new_play()
        p.mode = "battle"
        p.calibration = CAL
        p.start_battle()
        p.battle.update = lambda *args: None
        p.battle.end("won", 1.0)
        p.update_battle([], None, None, 1.0, False)  # logs the row
        p.battle.phase = "checkin"
        for key in "325":
            p.handle_key(ord(key), 2.0)
        p.update_battle([], None, None, 2.0, False)  # the report: the answers are saved
        rows = play.progress.load_sessions(p.log_path)
        self.assertEqual((rows[-1].pain, rows[-1].tiredness, rows[-1].mood), (3.0, 2.0, 5.0))
        self.assertEqual(p.battle.session.pain, 3.0)

    def test_after_the_report_a_win_moves_on_and_a_fall_retries(self):
        for outcome, expected_index in (("won", 1), ("lost", 0)):
            p = new_play()
            p.mode = "battle"
            p.calibration = CAL
            p.start_battle()
            first = p.battle
            first.update = lambda *args: None
            first.counted = True
            first.reach = type("R", (), {"name": "Aries", "points": []})()
            first.outcome, first.phase, first.dismissed, first.report_page = outcome, "report", True, 1
            with mock.patch.object(play, "append_row"):
                p.update_battle([], None, None, 99.0, False)
            self.assertEqual(p.battle_index, expected_index)
            self.assertIsNot(p.battle, first)  # a fresh battle either way

    def test_rest_key_passes_the_turn(self):
        p = new_play()
        p.mode = "battle"
        p.calibration = CAL
        p.start_battle()
        p.handle_key(ord("0"), 0.0)
        self.assertEqual(p.battle.turn, "enemy")


class LoggingTest(unittest.TestCase):
    def test_a_completed_practice_constellation_is_logged_once(self):
        p = new_play()
        p.mode = "practice"
        p.start_reach()
        p.reach.update = lambda *args: None
        p.reach.won_at = 5.0
        with mock.patch.object(play, "append_row") as append:
            p.update_practice([], None, None, 6.0, False)
            p.update_practice([], None, None, 6.1, False)
        append.assert_called_once()
        row = append.call_args[0][0]
        self.assertEqual((row["mode"], row["constellation"], row["result"]), ("practice", "Aries", "completed"))

    def test_a_won_battle_is_logged_with_its_damage(self):
        p = new_play()
        p.mode = "battle"
        p.start_battle()
        battle = p.battle
        battle.update = lambda *args: None
        battle.phase, battle.phase_at, battle.enemy_health = "won", 0.0, 0
        with mock.patch.object(play, "append_row") as append:
            p.update_battle([], None, None, 1.0, False)
            p.update_battle([], None, None, 1.1, False)
        append.assert_called_once()
        row = append.call_args[0][0]
        self.assertEqual((row["mode"], row["result"], row["damage dealt"]), ("battle", "won", battle.enemy_max))


if __name__ == "__main__":
    unittest.main()

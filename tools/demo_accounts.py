"""Fill a separate demo folder with accounts to try the portal: two coaches (one open, one closed), a patient
linked to the open coach with the simulated patient's sessions (tools/simulate.py) and a short recorded
clip, and a second patient with no coach yet. Never touches the real data/ folder.

Run:   .venv/bin/python -m tools.demo_accounts          (writes demo_data/)
Then:  .venv/bin/python -m portal --data demo_data      and open http://localhost:8765
Logins (password demo123 for all): coach_amy (open), coach_ben (closed), pat_sam (linked), pat_ria (no coach)
"""
import os
import shutil
import sys

import cv2

import tools.make_screenshots as shots
from accounts import Store
from recording import Recorder, video_name

DEMO_DIR = "demo_data"
PASSWORD = "demo123"


def demo_clip(path, folder):
    """A few seconds of the battle screen, recorded the way the game records sessions."""
    play = shots.new_play(folder, wins=1)
    battle = shots.start_battle(play, 1)
    battle.choose(1, 1.0)
    battle.reach.update([], None, shots.figure(), (0, 0, 1, 1), 1.0, shots.CAL)
    play.reach = battle.reach
    rec = Recorder()
    rec.start(path)
    for i in range(150):  # 5 seconds at 30 FPS
        t = 1.0 + i / 30
        battle.reach.lit_at = [1.0 + k for k in range(min(len(battle.reach.points), int(i / 30)))]
        rec.write(shots.frame(play, t))
    return rec.stop()


def main(out=DEMO_DIR):
    if os.path.exists(out):
        shutil.rmtree(out)
    store = Store(out)
    amy = store.register("coach_amy", PASSWORD, "coach", "Coach Amy", "Upper-limb stroke rehab, 12 years of home programmes",
                         "Stroke rehabilitation")
    ben = store.register("coach_ben", PASSWORD, "coach", "Coach Ben", "Hand therapy and grip strength", "Hand therapy")
    store.set_status(ben, "closed")
    sam = store.register("pat_sam", PASSWORD, "patient", "Sam")
    store.register("pat_ria", PASSWORD, "patient", "Ria")
    store.link(sam, amy.id)
    run = store.create_run(sam, "September programme")
    log, _, videos = store.run_paths(run)
    source = os.path.join("simulation", "bot_a_sessions.csv")
    if os.path.exists(source):
        shutil.copyfile(source, log)
    else:
        print("No simulation/bot_a_sessions.csv: run  .venv/bin/python -m tools.simulate  first for session data")
    store.create_run(sam, "Fresh start")
    clip = demo_clip(os.path.join(videos, video_name("20261006-101400", "Scorpius")), os.path.join(out, "tmp"))
    store.add_feedback(amy, sam.id, "Lovely straight paths this week. Try one Block every few turns: the fist hold is great "
                                    "practice for your hand.", run.id)
    store.touch_run(run)
    store.close()
    shutil.rmtree(os.path.join(out, "tmp"), ignore_errors=True)
    print(f"Demo accounts in {out}/ (password {PASSWORD}): coach_amy, coach_ben, pat_sam, pat_ria. Clip: {clip}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEMO_DIR)

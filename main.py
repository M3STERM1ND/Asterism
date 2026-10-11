"""Asterism: opens the webcam, tracks hands and shoulders, calibrates, and plays Reach constellations.

Start menu: P play (battles), R practice, E editor, T lean test, G progress, D difficulty, A assisted learning.
Anywhere: M start screen, C recalibrate, L lean guard on/off, N next constellation, R restart it, H hint
(assisted learning off), D lean bars, F full screen, Q or Esc quit.
Battle, your turn: 1-8 attack with a spell, B (or hold a fist) block, 0 rest. After a battle: 1-5 answer the
check-in (S skips), then Enter through the report. Progress (G): R writes the therapist report.
Editor: click to place stars, right-click or Backspace to undo, X clear, N name, S save.
Each finished battle or practice constellation is logged to sessions.csv.
Test keys (not in battles, where the turn rules own those moments): 1 STAR, 2 WIN, 3 WARN LEAN, 4 ATTACK, 5 SHIELD.
"""
import time

import cv2

import events
import battle_screen
import render
import screens
import session_log
from camera import Camera
from orion import Orion
from pacing import FramePacer
from accounts import Store
from play import Play
from tracking import Tracker
from view import View

WINDOW = "Asterism"
FRAME_SECONDS = 1 / 30  # the screen redraws at 30 FPS on its own, even if the webcam slows down in dim light
TEST_KEYS = {ord("2"): "WIN", ord("3"): "WARN LEAN", ord("4"): "ATTACK", ord("5"): "SHIELD"}


STAGES = ("logic", "draw", "show", "wait", "asked")  # the FPS line's breakdown: "asked" is the wait requested


def add_stage_times(stage_ms, start, drawn_at, shown_at, end):
    """Add one frame's game logic, drawing and imshow times (ms) to the running totals."""
    stage_ms["logic"] += (drawn_at - start) * 1000
    stage_ms["draw"] += (shown_at - drawn_at) * 1000
    stage_ms["show"] += (end - shown_at) * 1000


def handle_key(key, star_count):
    """Fire a test event for number keys; return the updated star count."""
    if key == ord("1"):
        star_count += 1
        events.emit("STAR", star_count)
    elif key in TEST_KEYS:
        events.emit(TEST_KEYS[key])
    return star_count


def open_window(play):
    """Open the game window full screen; it scales to any screen size and keeps its shape.
    Mouse clicks go to the editor (OpenCV reports them in the 1280x720 image's pixels)."""
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    def on_mouse(event, x, y, flags, param):
        if event in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN):
            play.handle_click(x, y, time.monotonic(), right=event == cv2.EVENT_RBUTTONDOWN)

    cv2.setMouseCallback(WINDOW, on_mouse)


def toggle_fullscreen():
    """Switch between full screen and a normal window."""
    is_full = cv2.getWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN) == cv2.WINDOW_FULLSCREEN
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL if is_full else cv2.WINDOW_FULLSCREEN)


def main():
    """Main loop: draw at a steady 30 FPS with the latest tracking, handle keys, report FPS."""
    events.init_audio()
    session_log.upgrade_log()  # an older sessions.csv gets the new columns now, keeping every row
    camera = Camera()
    tracker = Tracker(camera)
    orion = Orion()
    view = View()
    star_count = 0
    store = Store()  # accounts, runs and coach feedback (data/asterism.db)
    play = Play((render.W, render.H), view, store=store, use_cloud=True)  # Supabase sign-in when .env is set up
    open_window(play)
    tuning = False  # key D shows the lean check bars while playing
    fps, track_fps, frames, tracked, last_report = 0.0, 0.0, 0, 0, time.monotonic()
    stage_ms = dict.fromkeys(STAGES, 0.0)  # time spent in each part of the frame since the last report
    pacer = FramePacer(FRAME_SECONDS)

    while True:
        frame_start = time.monotonic()
        hands, pose = tracker.latest()
        now = time.monotonic()
        view.follow(pose, now)
        hands, pose = view.apply(hands, pose)  # frame the player so distance from the laptop doesn't matter
        figure = orion.update(pose, hands, now)
        play.update(hands, pose, figure, now)
        drawn_at = time.monotonic()
        world = None
        if play.mode == "battle":
            world = lambda frame, glow: battle_screen.draw_battle_world(frame, glow, play, figure, hands, now)
        image = render.draw(hands, pose, figure, fps, track_fps, play, world)
        screens.draw_screens(image, play, tuning, now)
        if play.mode == "battle":
            battle_screen.draw_battle_hud(image, play, now)
        shown_at = time.monotonic()
        cv2.imshow(WINDOW, image)  # the camera feed itself stays hidden
        play.recorder.write(image)  # the session's video for the coach (only while one is recording)

        frames += 1
        now = time.monotonic()
        add_stage_times(stage_ms, frame_start, drawn_at, shown_at, now)
        if now - last_report >= 1:
            fps = frames / (now - last_report)
            track_fps = (tracker.updates - tracked) / (now - last_report)
            print(f"FPS: {fps:.1f}  tracking: {track_fps:.1f}  hands: {len(hands)}  pose: {'yes' if pose else 'no'}"
                  f"  mode: {play.mode}  ms/frame: " + "  ".join(f"{k} {v / frames:.1f}" for k, v in stage_ms.items()))
            frames, tracked, last_report = 0, tracker.updates, now
            stage_ms = dict.fromkeys(STAGES, 0.0)

        wait_ms = pacer.wait_ms(time.monotonic() - frame_start)
        waited_at = time.monotonic()
        key = cv2.waitKey(wait_ms) & 0xFF  # waiting here keeps a steady frame rate
        waited_ms = (time.monotonic() - waited_at) * 1000
        pacer.record(wait_ms, waited_ms)
        stage_ms["wait"] += waited_ms
        stage_ms["asked"] += wait_ms
        if key != 0xFF and play.typing():  # naming a constellation: every key is a letter, even Q and Esc
            play.handle_key(key, now, figure)
            continue
        if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            break
        if key == ord("f"):
            toggle_fullscreen()
        elif key == ord("d") and play.mode not in ("start", "progress", "lobby"):
            tuning = not tuning
        play.handle_key(key, now, figure)
        if play.mode not in ("battle", "start", "progress", "lobby"):  # a battle's attacks and shields come only from its turns
            star_count = handle_key(key, star_count)

    play.recorder.cancel()  # quitting mid-session: no report row, so no video
    store.close()
    tracker.close()
    camera.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

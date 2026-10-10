"""Asterism: opens the webcam, tracks hands and shoulders, calibrates, and plays Reach constellations.

Start menu: P play (battles), R practice, E editor, T lean test. Anywhere: M start screen, C recalibrate,
L lean guard on/off, N next constellation, R restart it, D lean bars, F full screen, Q or Esc quit.
Editor: click to place stars, right-click or Backspace to undo, X clear, N name, S save.
Each finished battle or practice constellation is logged to sessions.csv.
Test keys: 1 STAR, 2 WIN, 3 WARN LEAN, 4 ATTACK, 5 SHIELD.
"""
import time

import cv2

import events
import battle_screen
import render
import screens
from camera import Camera
from orion import Orion
from play import Play
from tracking import Tracker
from view import View

WINDOW = "Asterism"
FRAME_SECONDS = 1 / 30  # the screen redraws at 30 FPS on its own, even if the webcam slows down in dim light
TEST_KEYS = {ord("2"): "WIN", ord("3"): "WARN LEAN", ord("4"): "ATTACK", ord("5"): "SHIELD"}


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
    camera = Camera()
    tracker = Tracker(camera)
    orion = Orion()
    view = View()
    star_count = 0
    play = Play((render.W, render.H), view)
    open_window(play)
    tuning = False  # key D shows the lean check bars while playing
    fps, track_fps, frames, tracked, last_report = 0.0, 0.0, 0, 0, time.monotonic()

    while True:
        frame_start = time.monotonic()
        hands, pose = tracker.latest()
        now = time.monotonic()
        view.follow(pose, now)
        hands, pose = view.apply(hands, pose)  # frame the player so distance from the laptop doesn't matter
        figure = orion.update(pose, hands, now)
        play.update(hands, pose, figure, now)
        image = render.draw(hands, pose, figure, fps, track_fps, play)
        screens.draw_screens(image, play, tuning, now)
        if play.mode == "battle":
            battle_screen.draw_battle(image, play, figure, hands, now)
        cv2.imshow(WINDOW, image)  # the camera feed itself stays hidden

        frames += 1
        now = time.monotonic()
        if now - last_report >= 1:
            fps = frames / (now - last_report)
            track_fps = (tracker.updates - tracked) / (now - last_report)
            print(f"FPS: {fps:.1f}  tracking: {track_fps:.1f}  hands: {len(hands)}  pose: {'yes' if pose else 'no'}")
            frames, tracked, last_report = 0, tracker.updates, now

        wait_ms = int((FRAME_SECONDS - (time.monotonic() - frame_start)) * 1000)
        key = cv2.waitKey(max(1, wait_ms)) & 0xFF  # waiting here keeps a steady frame rate
        if key != 0xFF and play.typing():  # naming a constellation: every key is a letter, even Q and Esc
            play.handle_key(key, now, figure)
            continue
        if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            break
        if key == ord("f"):
            toggle_fullscreen()
        elif key == ord("d"):
            tuning = not tuning
        play.handle_key(key, now, figure)
        star_count = handle_key(key, star_count)

    tracker.close()
    camera.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

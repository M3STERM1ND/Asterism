run# Asterism PRD

Oct 10, 2026 · @Abdul · Hyphen-Hacks, theme: Crafting Constellations

## Overview

Asterism helps stroke survivors do their home rehab exercises: a webcam turns their hand into stars, and every correct repetition draws one more line of a constellation their therapist designed.

**Why the name:** an asterism (AS-ter-izm) is a small, recognizable star pattern inside a bigger constellation, like the Big Dipper inside Ursa Major. Each session is one asterism; together they build the patient's whole constellation of recovery. Say the definition in the first ten seconds of the pitch, since most people won't know the word.

**The game: you are Orion.** The patient's own body is drawn as Orion the hunter. Scorpius has swallowed the sky, and the patient wins it back one turn-based battle at a time by drawing zodiac constellations with their arm. In the Greek myth, the scorpion defeated Orion and the two were placed on opposite sides of the sky. In Asterism, every patient gets the rematch.

**Second pitch line:** "Every rep is a spell. Lean instead of reaching and it fizzles. Reach properly and the sky lights up."

**Pitch line:** "After a stroke, recovery happens at home, one repetition at a time. But only 28% of survivors keep doing their exercises. Asterism turns every repetition into a star, so recovery becomes a constellation you can see."

**Theme fit (Crafting Constellations):**

- **Constellations.** The patient's hand joints are drawn as stars, each exercise is a target constellation, and progress over weeks becomes a growing night sky.
- **Crafting.** The therapist crafts the constellation as the prescription by placing stars where the patient needs to reach. The patient crafts their recovery by drawing it, one repetition per line.
- **Test:** remove the stars and the app no longer works. The constellation is the mechanic, not decoration.

**Positioning:** Asterism complements therapy; it does not replace it. It is how patients do their homework between visits.

## Problem and evidence

Stroke recovery depends on repeated arm and hand exercises at home, and most survivors stop doing them.

| Finding | Source |
| --- | --- |
| Only 28% of 92 stroke survivors did more than 70% of their prescribed home exercises | [Mahmood et al., Physiotherapy Research International](https://nova.newcastle.edu.au/vital/access/%20/manager/Repository/uon:37652) |
| More than half of stroke patients go home for rehab because rehab resources are limited; about 80% have limb problems | [Dove Press review](https://www.dovepress.com/article/download/112022) |
| Lower adherence is linked to tiredness, exercise feeling difficult, forgetfulness, not being part of the routine, and feeling it helps little | [Bulletin of Faculty of Physical Therapy](https://bfpt.springeropen.com/articles/10.1186/s43161-024-00224-4/tables/5) |
| Adherence was higher during an organized group program and dropped after patients graduated | [Topics in Stroke Rehabilitation](https://synapsesocial.com/papers/W2023112820) |

**Why people skip, and what Asterism does about it:**

| Barrier | Asterism's answer |
| --- | --- |
| Boring, repetitive | Every rep lights a star; finishing draws a constellation |
| No feedback at home | Camera checks reach and grip live; a star lights only when the rep is done right |
| Feels like it isn't helping | Each session saves to "My sky" with reach numbers that grow over time |
| Forgetting, no routine | Short sessions (2 to 3 minutes) with a clear finish |
| Therapist can't see what happened | Session log the therapist can review |

**Is game-based rehab real?** Yes, with a caveat. Commercial consoles (Wii, Xbox, EyeToy) are widely used for upper limb rehab, and one review found the Wii as effective as conventional therapy ([World Physiotherapy](https://world.physio/congress-proceeding/systematic-review-effectiveness-commercial-gaming-systems-improving-upper-0)). A meta-analysis found non-immersive computer-game therapy effective and acceptable after stroke ([Masaryk University](https://www.muni.cz/vyzkum/publikace/1670358)). A 2025 review found positive effects but low-quality evidence, so it can't be recommended over conventional therapy ([Manipal](https://researcher.manipal.edu/en/publications/effects-of-game-based-rehabilitation-on-upper-limb-motor-function/)). That is why Asterism is pitched as a complement.

## Users and goals

The patient is the main user; the therapist sets up and reviews; the judge must get it in under a minute.

| User | Goal | What they do in Asterism |
| --- | --- | --- |
| Stroke survivor at home | Keep doing arm and hand exercises and see improvement | Plays Reach and Grip sessions, checks My sky |
| Physical or occupational therapist | Prescribe the right movements and see progress between visits | Crafts constellations in the editor, reviews the session log |
| Hackathon judge | Understand and try it fast | Plays one Reach constellation live |

**Success at judging:** a judge completes a constellation live, sound and visuals react to every star, and every teammate can explain the key decisions.

## How it works

One loop: the therapist crafts a constellation, the patient draws it with their hand, the sky celebrates with sound and light, and the result is saved to their sky.

&#91;embedded content: core loop · 6 steps\]

The therapist crafts once; the patient repeats the loop at home, and each pass makes the next constellation a little bigger.

**Sessions**

- **Reach (hero, arm).** Stars sit at the edge of the patient's calibrated range. Touching each with the index fingertip lights it and draws a line to the previous star. Finishing reveals the constellation's name.
- **Grip (hand).** Clench the fist for 3 seconds, then open fully. Each full cycle lights a star. Detected from fingertip-to-palm distance.
- **Breathe (calm, optional).** Open hands slowly to inhale, close to exhale, paced to box breathing (4 in, 4 hold, 4 out, 4 hold). A rushed breath doesn't light a star. Used as a warm-up or cool-down.

**Orion vs Scorpius (the game layer)**

- **Orion body view:** MediaPipe Pose draws the patient as Orion. Shoulders = Betelgeuse and Bellatrix, hips = the belt (Alnitak, Alnilam, Mintaka), knees = Saiph and Rigel, with star names fading in.
- **Battle turns:** the patient picks a zodiac spell and draws it with Reach. Damage scales with how far they reached and whether form was clean. A lean makes the star flicker and the spell weaker.
- **The Void's turn:** it attacks; a Grip rep (clench, then open) raises a shield.
- **Win:** that sign joins the patient's sky permanently, and the sky celebrates with a chime and a glow.
- **Levels:** each zodiac sign is a battle with a shape that trains a movement. Aries is small and easy, Leo is wide for side reaches, Scorpius is a long curving sweep across the body and is the final boss.
- **No time pressure:** turns wait for the patient, so slow, careful reps are rewarded. That's why it's turn-based, not an action game.

**Feedback (sound and screen, no hardware)**

- **Every star:** a soft chime that rises in pitch with each star, plus a gold burst on screen.
- **Win:** a short melody, the whole constellation glows, its name fades in.
- **Scorpius attacks:** a deep rumble and red pulses at the screen edges.
- **Warnings:** a low tone, the target turns red, and the spell visibly fizzles.
- Sound plays through the laptop speakers; everything is driven by one `events.py` module.

**Form guard (warnings)**

- **Lean (P1, the demo moment):** MediaPipe Pose compares shoulder height and torso angle to calibration. If the patient leans or hikes the shoulder instead of reaching with the arm, a low tone plays, the target turns red, and the star won't count.
- **Too fast (P2):** jerky swipes get a gentle tone and a "slow down" message.
- **Fatigue (P2):** if reps slow or reach shrinks, a soft chime suggests resting.
- **Daily reminder (P2):** an on-screen reminder at a set time while the app runs.

**Constellation editor (the "crafting")**

- Therapist clicks on the webcam view to place 4 to 8 stars, names the constellation, and saves it to a JSON file.
- Stars are stored in normalized coordinates, so the same constellation scales to each patient's reach.

**Calibration**

- At the start, the patient sweeps their hand as far as is comfortable. Asterism records that range and scales the constellation to sit just at its edge.
- When a session is completed easily, the next one is scaled 5 to 10% larger, so the sky grows as reach improves.

**My sky**

- Every finished constellation is saved with date, time to complete, and max reach.
- The My sky screen shows all saved constellations together, plus reach over time for the therapist.

## Requirements

P0 is the minimum live demo, P1 makes it a winning project, P2 only if P1 is done before 4:00.

**P0 (must work by about 2:00)**

- [ ] Webcam feed with MediaPipe Hands, mirrored, at 20+ fps
- [ ] Starry rendering in OpenCV: dark background, hand joints drawn as glowing stars joined by lines
- [ ] Reach: one hard-coded constellation, stars lit by index fingertip within a radius, lines drawn between lit stars
- [ ] Completion: name reveal and glow animation
- [ ] `emit(event)` in events.py that fires `STAR n`, `WIN` and plays a sound and screen effect for each

**P1 (the strong project)**

- [ ] Calibration of reach range and scaling of the constellation to it
- [ ] Sound and screen feedback: rising chime per star, win melody, Scorpius rumble, warning tone, gold bursts and red edge pulses
- [ ] Lean warning: Pose compares shoulders and torso to calibration, sends `WARN LEAN`, star refuses to light
- [ ] Orion body view: patient's pose drawn as Orion with star names
- [ ] Battle mode for 2 battles (Orion warm-up, Scorpius boss): turns, health bars, damage from reach and form, Grip as shield
- [ ] 3 constellation files: Orion, Aries, Scorpius
- [ ] Constellation editor: click to place stars, name, save and load JSON
- [ ] Grip session
- [ ] Session log to CSV (date, session, time to complete, max reach, lean warnings)
- [ ] Menu to pick a session (keyboard first, joystick or IR remote if time)

**P2 (stretch)**

- [ ] All 12 zodiac signs as battles; patient starts with their own sign
- [ ] My sky as a zodiac wheel that lights up as signs are won
- [ ] Reach-over-time graph for the therapist
- [ ] Too-fast and fatigue warnings, daily reminder
- [ ] Breathe session
- [ ] Auto difficulty: next constellation 5 to 10% larger after an easy finish

## Technical design

Everything runs in Python on one laptop with its webcam; no extra hardware. Game logic fires events, and one module turns them into sound and screen effects.

**Engine**

- **Tracking:** MediaPipe Hands gives 21 landmarks per hand (index fingertip = landmark 8, wrist = 0).
- **Normalization:** subtract the reference point and divide by a size measure (wrist to middle-finger base for Grip; shoulder width or calibrated range for Reach), so camera distance and position don't matter.
- **Hit test (Reach):** a star is hit when the fingertip is within a radius r of it for about 0.3 seconds, which avoids accidental hits from swiping through.
- **Grip test:** average fingertip-to-wrist distance, normalized by hand size. Below a closed threshold for 3 seconds, then above an open threshold, counts as one rep.
- **Smoothing:** average the last 3 to 5 frames of each landmark to remove jitter.

**Rendering (OpenCV)**

- Dark background with faint random stars; the webcam image shown dimmed or hidden.
- Glow = draw each star as stacked circles of decreasing size and increasing brightness, or blur a copy and add it back.
- Target stars pulse until hit; lit stars stay bright; lines fade in.

**Constellation file (JSON)**

```
{"name": "The Reach", "stars": [[0.2, 0.3], [0.5, 0.1], [0.8, 0.35]], "order": "sequential"}
```

**Events, sound and effects**

- One function, `emit(event)` in `events.py`. Game code only calls `emit`; `events.py` decides what plays and what flashes.
- Sounds are generated as short tones with NumPy and played with `pygame.mixer`, so no audio files are needed. Add real sound files later if there's time.

| Event | Fired when | Sound | Screen |
| --- | --- | --- | --- |
| `STAR n` | Star n is lit | Chime, pitch rises with n | Gold burst, line fades in |
| `WIN` | Constellation or battle won | Short melody | Whole shape glows, name fades in |
| `WARN LEAN` | Body leans or shoulder hikes | Low tone | Target turns red, "Reach with your arm" |
| `ATTACK` | Scorpius's turn | Deep rumble | Red pulses at screen edges |
| `SHIELD` | Grip rep completed during an attack | Bright ping | Blue shield ring |
| `WARN FAST` / `REST` (P2) | Too jerky / fatigue | Gentle double tone / soft chime | Message |

**Stack**

| Layer | Tool | Used for |
| --- | --- | --- |
| Language | Python 3.10 or 3.11 in a virtual environment | Main app (MediaPipe supports these versions most reliably) |
| Hand and body tracking | MediaPipe Hands + Pose | 21 hand landmarks; shoulders, hips and knees for the Orion body view and lean detection |
| Camera and drawing | OpenCV (`opencv-python`) | Webcam feed, star rendering, glow, editor clicks |
| Text | Pillow | Clean TTF fonts on screen (DM Sans) |
| Math | NumPy | Normalization, distances, smoothing, generating tones |
| Sound | pygame (mixer only) | Chimes, melody, rumble, warning tones |
| Data | JSON + CSV (standard library) | Constellation files, session log |
| Graphs (P2) | matplotlib | Reach-over-time chart |
| Website (optional) | Next.js, Tailwind, Framer Motion | Landing page for the pitch and Devpost |
| Code sharing | GitHub repo | README with decision log |

Setup: `pip install mediapipe opencv-python numpy pillow pygame`.

## Build plan for today

The Orion body view and Reach work before lunch, battles work by 4:00, and features freeze at 5:00. No hardware: hackathon rules don't allow it.

| Time | Game and vision | Look and sound | Pitch and extras |
| --- | --- | --- | --- |
| 11:00 to 12:00 | Prompts 0, 1, 3: setup, Orion body view | Prompt 2: night-sky look | Ask organizers if external webcams are allowed; pitch outline |
| 12:00 to 12:45 | Lunch | Lunch | Lunch |
| 12:45 to 2:30 | Prompts 4, 5: Reach, calibration, lean warning | Sound layer in events.py; tune glow and effects | Check constellation files against a star chart; website (optional) |
| 2:30 to 4:00 | Prompt 6: battle mode | Battle visuals: health bars, attack and shield effects | Prompt 7: editor, log, menu |
| 4:00 to 5:00 | Bug fixes; P2 only if battles work | Final visual polish | Devpost text, record backup demo video |
| 5:00 to 5:45 | Feature freeze: bug fixes only | Test the demo in the judging room's light | Rehearse pitch twice with a timer |
| 5:45 | Dinner | Dinner | Dinner |
| 6:30 | Submit |  |  |
| 6:45 | Presentations and judging |  |  |

If the team has fewer than three people, merge the third column into the other two and cut the website first, then the editor.

## Build prompts

Paste these into Claude Code one at a time, in order, and move on only when each step runs. After each step, one teammate reads the new code and adds a line to the decision log, so everyone can explain it to judges.

**Prompt 0: rules (paste once)**

```
We're building Asterism at a hackathon: a webcam rehab game for stroke survivors. The player is Orion: their body is drawn as the Orion constellation, and they win back a sky swallowed by Scorpius in turn-based battles by reaching to draw zodiac constellations. Python 3.11 in a virtual environment, OpenCV, MediaPipe, NumPy, Pillow, pygame (sound only). No external hardware is allowed: everything runs on the laptop and its webcam. Rules: keep code simple and readable, one job per file, no new libraries without asking, run it after every change, and after each step explain each new function in 1 to 2 lines so we understand it.
```

**Prompt 1: setup**

```
Create the project: main.py, tracking.py, render.py, events.py, game/ (battle logic), sessions/ (reach.py, grip.py), constellations/ (JSON), assets/ (fonts). Open the webcam mirrored at 1280x720, run MediaPipe Hands and Pose, print FPS. events.py has emit(event, n=None): it plays a short sound generated with NumPy through pygame.mixer (a chime for STAR that rises in pitch with n, a short melody for WIN, a low tone for WARN LEAN, a deep rumble for ATTACK, a bright ping for SHIELD) and records the event so render.py can show a matching screen effect. If audio fails to start, keep running silently.
```

**Prompt 2: the look**

```
Make render.py look like a premium night-sky game, not a debug window:
- Hide the camera feed. Background: deep navy gradient (#070B1A to #0F1A3A) with about 150 faint twinkling stars.
- Glow: draw shapes on a separate layer, Gaussian blur it, add it back on top.
- Palette: white-gold stars (#FFE8B0), one accent (soft cyan #7FDBFF) for the active target, red (#FF6B6B) only for warnings and Scorpius.
- Text with Pillow and one clean TTF font (DM Sans from Google Fonts), sentence case, generous margins. No OpenCV Hershey fonts.
- Keep 25+ FPS. Screenshot the result and fix anything that looks cheap before showing me.
```

**Prompt 3: Orion body view**

```
Draw the player's body as the Orion constellation using Pose: left and right shoulders = Betelgeuse and Bellatrix, three belt stars spaced across the hips = Alnitak, Alnilam, Mintaka, knees = Saiph and Rigel (fall back to hips if knees are out of frame), plus the reaching hand as a bright star. Connect them with faint lines like a star chart. When the player first appears, fade the star names in for 3 seconds. Hand joints stay as small stars.
```

**Prompt 4: Reach**

```
Build sessions/reach.py. Create constellations/orion.json, aries.json and scorpius.json with simplified stars (Aries 4, Orion 7, Scorpius 8 to 10), normalized 0 to 1, and tell me which real stars you used so we can check them against a star chart. Show one target star at a time, pulsing cyan. A star is hit when the index fingertip (landmark 8) stays within a radius for 0.3 s: it turns gold, a line fades in from the previous star, and emit("STAR n") fires. When all are hit, the shape glows, its name fades in, and emit("WIN") fires. Smooth landmarks over the last 4 frames.
```

**Prompt 5: calibration and lean warning**

```
Add calibration before play: for 5 seconds the player sweeps their arm as far as is comfortable; record reach range from the shoulder, plus resting shoulder height and torso angle. Scale each constellation so its outer stars sit at the edge of the range. During Reach, if the torso leans past a threshold or a shoulder rises, turn the target red, show "Reach with your arm, not your body", block the hit, and emit("WARN LEAN"). Key L toggles the guard for demos. Explain the thresholds.
```

**Prompt 6: battle mode**

```
Build game/battle.py, turn-based, never timed. Player turn: draw the battle's constellation with Reach; damage per star = base x reach quality (how far past 80% of calibrated range) x form (half damage if a lean warning fired on that star). Scorpius turn: a short red attack animation; the player blocks by doing one Grip rep (sessions/grip.py: clench fist 3 s, open fully, using normalized fingertip-to-wrist distance), otherwise loses some health. Health bars for both, in the night-sky style. Battle 1: Orion warm-up against a small shadow. Battle 2: Scorpius boss using the scorpius constellation. On win: the constellation joins the sky and emit("WIN").
```

**Prompt 7: editor, log and menu**

```
1) Editor (key E): click to place 4 to 8 stars, N to name, S to save JSON in constellations/. 2) Log each finished battle to sessions.csv: date, battle, time, max reach, lean warnings, damage dealt. 3) Start menu in the same style: Play (battles), Practice (Reach only), Editor. Keyboard controls.
```

**Throughout:** every place a prompt says emit(...), the game fires that event and events.py handles the sound and effect.

## Rubric strategy

The plan targets the top band in every category except AI Usage, where the goal is the top of the 11 to 24 band.

| Category | Points | Target band | How Asterism earns it |
| --- | --- | --- | --- |
| Wow + Innovation | 30 | Outstanding (26 to 30) | Your body becomes Orion; reps are spells in a turn-based battle against Scorpius; bad form makes spells fizzle |
| Execution | 25 | Outstanding (21 to 25) | One complete loop that never breaks; polished night-sky visuals and sound; no hardware to fail |
| AI Usage | 25 | Good, high end (20 to 24) | AI used to help code; every teammate can explain normalization, hit test, thresholds, damage formula and scope cuts; keep a decision log |
| Potential for Impact | 20 | Outstanding (16 to 20) | Real problem (28% adherence), studied approach, needs only a laptop webcam, new exercises are just new JSON files |
| Theme | 15 | Outstanding (13 to 15) | Therapist crafts constellations, patient draws them with their body, and the patient literally is Orion |
| Pitch | 10 | Outstanding (9 to 10) | Two-minute script, judge plays live, rehearsed twice |

**Decision log (keep it in the repo README):** for each key decision, write what was chosen, what was rejected, and why. Examples so far: switched from three modes to a stroke-rehab focus for impact; dropped sign language for reliability; framed as a complement to therapy because the evidence is mixed; made it a turn-based game so slow, careful reps win; dropped the Arduino because hardware isn't allowed, and moved feedback to sound and screen.

## Risks, demo and open questions

The biggest risk is a demo that breaks at the judging table, so every risk has a fallback that keeps Reach playable.

| Risk | Fallback |
| --- | --- |
| Bad lighting at the judging table | Test there at dinner; sit facing a window or lights; raise the hit radius |
| Judge's hand or body tracked poorly | Larger hit radius in demo mode; teammate demos first |
| Lean warning fires falsely | Widen the threshold; key L toggles it off |
| Judge's knees out of frame for the Orion view | Fall back to hips for Saiph and Rigel |
| Sound doesn't play in the room | App runs silently; screen effects carry the feedback |
| Battle mode not finished by 4:00 | Demo Reach + lean warning + Orion view, which is a complete project |
| Calibration buggy | Hard-coded default range |
| Laptop fails | Backup demo video recorded by 5:00 |

**Two-minute demo script**

1. Hook: "After a stroke, recovery happens at home, but only 28% of survivors keep doing their exercises."
2. The judge steps up and their body lights up as Orion: "This is you. And you've got a scorpion to beat."
3. Hand the judge the controls: they calibrate and draw their first spell while chimes rise with every star. Ask them to lean instead of reaching: a low tone plays, the target turns red, and the spell fizzles. Then they reach properly, the spell lands on Scorpius, and the sky lights up with a melody.
4. Show Grip briefly and the session log.
5. Impact: just a laptop webcam, works at home, new exercises are new constellations; a complement to therapy, backed by research on game-based rehab.
6. One sentence on AI: what it helped with, and which decisions the team made.

**Open questions**

- [ ] How many people are on the team, and who owns each column of the build plan?
- [ ] Does the no-hardware rule also cover external webcams, or only the built-in camera?
- [ ] Where is judging, and what is the lighting like there?
- [ ] Constellation names: real ones (Big Dipper) or our own (The Reach)?

## Sources

- [Measurement of adherence to home-based exercises among community-dwelling stroke survivors in India](https://nova.newcastle.edu.au/vital/access/%20/manager/Repository/uon:37652)
- [Factors Influencing Adherence to Home-Based Exercise Rehabilitation in Stroke Patients](https://www.dovepress.com/article/download/112022)
- [Adherence to home-based exercise programs among stroke survivors and perspectives of informal caregivers](https://bfpt.springeropen.com/articles/10.1186/s43161-024-00224-4/tables/5)
- [Factors affecting adherence to a home-based exercise program after stroke](https://synapsesocial.com/papers/W2023112820)
- [Systematic review of commercial gaming systems for upper limb function after stroke](https://world.physio/congress-proceeding/systematic-review-effectiveness-commercial-gaming-systems-improving-upper-0)
- [Computer game-based rehabilitation for post-stroke upper limb deficits: meta-analysis](https://www.muni.cz/vyzkum/publikace/1670358)
- [Effects of game-based rehabilitation on upper limb motor function following stroke (2025)](https://researcher.manipal.edu/en/publications/effects-of-game-based-rehabilitation-on-upper-limb-motor-function/)

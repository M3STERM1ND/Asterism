"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FilesetResolver, HandLandmarker } from "@mediapipe/tasks-vision";
import { configured, supabase } from "@/lib/supabase";

// Reach practice in the browser: the webcam finds your index fingertip (MediaPipe, on this device; the video
// never leaves the browser) and you touch each star of a constellation in order, holding briefly on each.
// Signed-in patients' rounds are saved to their account so their coach sees them.
// This is practice only: no calibration or lean guard, so the stars stay in a modest central area.

const W = 1280, H = 720;
const HIT_RADIUS = 52;          // px on the 1280x720 canvas
const DWELL_SECONDS = 0.4;
const BOX = { left: W * 0.3, top: H * 0.2, width: W * 0.4, height: H * 0.55 };  // a modest, central reach area
const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.1.0/wasm";
const CONSTELLATIONS = ["aries", "taurus", "gemini", "cancer", "leo", "pisces"];
const GOLD = "#f2c45a", IVORY = "#f5f0e6", MIST = "#c3cae0", NIGHT = "#0b1024";

type Point = [number, number];
type Round = { name: string; points: Point[]; lit: number[]; errors: number[]; started: number };

function fit(stars: Point[]): Point[] {
  const xs = stars.map((s) => s[0]), ys = stars.map((s) => s[1]);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const spanX = Math.max(Math.max(...xs) - minX, 1e-6), spanY = Math.max(Math.max(...ys) - minY, 1e-6);
  const k = Math.min(BOX.width / spanX, BOX.height / spanY);
  const offX = BOX.left + (BOX.width - spanX * k) / 2, offY = BOX.top + (BOX.height - spanY * k) / 2;
  return stars.map(([x, y]) => [offX + (x - minX) * k, offY + (y - minY) * k]);
}

async function saveRound(round: Round, now: number) {
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return "Not saved: log in at /portal to keep your rounds.";
  const me = auth.user.id;
  let { data: run } = await supabase.from("runs").select("id").eq("patient_id", me).eq("name", "Browser practice").maybeSingle();
  if (!run) {
    const made = await supabase.from("runs").insert({ patient_id: me, name: "Browser practice" }).select("id").single();
    if (made.error) return `Not saved: ${made.error.message}`;
    run = made.data;
  }
  const played = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${played.getFullYear()}-${pad(played.getMonth() + 1)}-${pad(played.getDate())} ${pad(played.getHours())}:${pad(played.getMinutes())}:${pad(played.getSeconds())}`;
  const seconds = (now - round.started) / 1000;
  const avgError = round.errors.reduce((a, b) => a + b, 0) / round.errors.length;
  const row = {
    date, mode: "browser practice", time: seconds.toFixed(1), constellation: round.name, result: "completed",
    "stars hit": String(round.lit.length), "avg error px": avgError.toFixed(1), "time per star": (seconds / round.lit.length).toFixed(2),
    assisted: "on", difficulty: "Browser",
  };
  const { error } = await supabase.from("sessions").insert({
    run_id: run!.id, patient_id: me, played_at: played.toISOString(), mode: "browser practice",
    constellation: round.name, result: "completed", row,
  });
  return error ? `Not saved: ${error.message}` : "Saved to your account. Your coach can see it.";
}

export default function Play() {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const landmarker = useRef<HandLandmarker | null>(null);
  const round = useRef<Round | null>(null);
  const dwell = useRef<{ since: number | null }>({ since: null });
  const [status, setStatus] = useState<"idle" | "loading" | "playing" | "done" | "error">("idle");
  const [message, setMessage] = useState("");
  const [choice, setChoice] = useState(0);
  const [signedIn, setSignedIn] = useState<boolean | null>(null);

  useEffect(() => {
    if (configured) supabase.auth.getUser().then(({ data }) => setSignedIn(Boolean(data.user)));
    else setSignedIn(false);
  }, []);

  const newRound = useCallback(async (index: number) => {
    const name = CONSTELLATIONS[index % CONSTELLATIONS.length];
    const data = await fetch(`/constellations/${name}.json`).then((r) => r.json());
    round.current = { name: data.name, points: fit(data.stars), lit: [], errors: [], started: performance.now() };
    dwell.current.since = null;
  }, []);

  const draw = useCallback((tip: Point | null, now: number) => {
    const ctx = canvas.current?.getContext("2d");
    const r = round.current;
    if (!ctx || !r) return;
    ctx.fillStyle = NIGHT;
    ctx.fillRect(0, 0, W, H);
    const target = r.lit.length < r.points.length ? r.lit.length : -1;
    ctx.lineWidth = 2;
    ctx.strokeStyle = GOLD;
    ctx.beginPath();
    r.lit.forEach((i, k) => { const [x, y] = r.points[i]; if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
    ctx.stroke();
    r.points.forEach(([x, y], i) => {
      const lit = i < r.lit.length;
      ctx.beginPath();
      ctx.arc(x, y, lit ? 7 : 5, 0, Math.PI * 2);
      ctx.fillStyle = lit ? GOLD : i === target ? IVORY : "rgba(195,202,224,0.25)";
      ctx.fill();
      if (i === target) {
        const pulse = 0.5 + 0.5 * Math.sin(now / 250);
        ctx.beginPath();
        ctx.arc(x, y, HIT_RADIUS * (0.6 + 0.15 * pulse), 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(242,196,90,${0.4 + 0.4 * pulse})`;
        ctx.lineWidth = 2;
        ctx.stroke();
        if (dwell.current.since !== null) {
          const p = Math.min(1, (now - dwell.current.since) / 1000 / DWELL_SECONDS);
          ctx.beginPath();
          ctx.arc(x, y, HIT_RADIUS * 0.85, -Math.PI / 2, -Math.PI / 2 + p * Math.PI * 2);
          ctx.strokeStyle = GOLD;
          ctx.lineWidth = 4;
          ctx.stroke();
        }
      }
    });
    if (tip) {
      ctx.beginPath();
      ctx.arc(tip[0], tip[1], 9, 0, Math.PI * 2);
      ctx.fillStyle = IVORY;
      ctx.shadowColor = GOLD;
      ctx.shadowBlur = 24;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
    ctx.fillStyle = MIST;
    ctx.font = "500 24px var(--font-dm-sans), sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(target < 0 ? `${r.name} complete` : `${r.name}  ·  ${r.lit.length} of ${r.points.length}`, W / 2, 56);
    if (!tip && target >= 0) ctx.fillText("Raise your hand so the camera can see it", W / 2, H - 48);
  }, []);

  const loop = useCallback(() => {
    const v = video.current, hl = landmarker.current, r = round.current;
    if (!v || !hl || !r) return;
    const now = performance.now();
    let tip: Point | null = null;
    if (v.readyState >= 2) {
      const result = hl.detectForVideo(v, now);
      const hand = result.landmarks?.[0];
      if (hand) tip = [(1 - hand[8].x) * W, hand[8].y * H];  // mirrored, so moving right moves right
    }
    const target = r.lit.length;
    if (target < r.points.length && tip) {
      const [x, y] = r.points[target];
      const distance = Math.hypot(tip[0] - x, tip[1] - y);
      if (distance <= HIT_RADIUS) {
        dwell.current.since ??= now;
        if ((now - dwell.current.since) / 1000 >= DWELL_SECONDS) {
          r.lit.push(target);
          r.errors.push(distance);
          dwell.current.since = null;
          if (r.lit.length === r.points.length) {
            setStatus("done");
            saveRound(r, now).then(setMessage);
          }
        }
      } else {
        dwell.current.since = null;
      }
    }
    draw(tip, now);
    requestAnimationFrame(loop);
  }, [draw]);

  async function start() {
    setStatus("loading");
    setMessage("");
    try {
      if (!landmarker.current) {
        const files = await FilesetResolver.forVisionTasks(WASM);
        landmarker.current = await HandLandmarker.createFromOptions(files, {
          baseOptions: { modelAssetPath: "/models/hand_landmarker.task", delegate: "GPU" },
          runningMode: "VIDEO", numHands: 1,
        });
      }
      if (!video.current!.srcObject) {
        video.current!.srcObject = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
        await video.current!.play();
      }
      await newRound(choice);
      setStatus("playing");
      requestAnimationFrame(loop);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error && error.name === "NotAllowedError"
        ? "Camera access was blocked. Allow the camera for this site in your browser, then try again."
        : `Couldn't start: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function next() {
    const index = choice + 1;
    setChoice(index);
    setMessage("");
    await newRound(index);
    setStatus("playing");
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line/60">
        <div className="mx-auto flex h-[72px] max-w-[1200px] items-center justify-between px-6">
          <a href="/" className="font-display text-2xl">✦ Asterism</a>
          <a href="/portal" className="rounded-full border border-line px-5 py-2.5 hover:border-ivory">
            {signedIn ? "Your account" : "Log in to save"}
          </a>
        </div>
      </header>
      <main className="mx-auto max-w-[1200px] px-6 py-12">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
          <div>
            <h1 className="font-display text-4xl md:text-5xl">Reach practice</h1>
            <p className="mt-3 max-w-[60ch] text-mist">
              Touch each star with your index fingertip, in order, and hold for a moment. Sit tall and reach with your arm,
              not your body. The camera stays on your device.
            </p>
          </div>
          {status === "idle" || status === "error" ? (
            <button onClick={start} className="rounded-full bg-gold px-8 py-4 text-lg font-semibold text-night">Start with my camera</button>
          ) : status === "done" ? (
            <button onClick={next} className="rounded-full bg-gold px-8 py-4 text-lg font-semibold text-night">Next constellation</button>
          ) : null}
        </div>
        {message && <p className="mb-6 rounded-xl border border-gold/50 px-4 py-3">{message}</p>}
        {status === "loading" && <p className="mb-6 text-mist">Starting the camera and hand tracking...</p>}
        <div className="relative overflow-hidden rounded-3xl border border-line bg-night">
          <canvas ref={canvas} width={W} height={H} className="block h-auto w-full" />
          {status === "idle" && (
            <div className="absolute inset-0 grid place-items-center p-6 text-center text-mist">
              Press “Start with my camera” and allow camera access.
            </div>
          )}
        </div>
        <video ref={video} className="hidden" playsInline muted />
        <p className="mt-6 max-w-[70ch] text-base text-mist">
          This is browser practice. The full game, with battles, blocking, safe-reach calibration and the lean guard,
          runs on your computer. Stop and rest if anything hurts, and tell your therapist.
        </p>
      </main>
    </div>
  );
}

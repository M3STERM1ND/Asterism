"use client";

import Image from "next/image";
import { MotionConfig, motion, type Variants } from "framer-motion";
import { useState } from "react";

const REPO = "https://github.com/M3STERM1ND/Asterism";
const EASE = [0.22, 1, 0.36, 1] as const;

// Motion moment 2: sections rise gently into place once, as they scroll in.
function Reveal({ children, className = "", delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.8, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="mb-6 text-base font-medium text-gold">{children}</p>;
}

/* ------------------------------------------------------------------ navbar */
function Navbar() {
  const links = [["How it works", "#features"], ["Results", "#proof"], ["Pricing", "#pricing"], ["FAQ", "#faq"]];
  return (
    <header className="sticky top-0 z-50 border-b border-line/60 bg-night/80 backdrop-blur-md">
      <nav className="mx-auto flex h-[72px] max-w-[1200px] items-center justify-between px-6 md:px-10" aria-label="Main">
        <a href="#top" className="flex items-center gap-2 font-display text-xl text-ivory md:gap-3 md:text-2xl">
          <StarMark /> Asterism
        </a>
        <div className="hidden items-center gap-10 text-base text-mist md:flex">
          {links.map(([label, href]) => (
            <a key={href} href={href} className="transition-colors hover:text-ivory">{label}</a>
          ))}
        </div>
        <a href="#pricing" className="whitespace-nowrap rounded-full bg-gold px-4 py-2 text-base font-semibold text-night transition-transform hover:-translate-y-0.5 md:px-5 md:py-2.5">
          Start free
        </a>
      </nav>
    </header>
  );
}

function StarMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 1.5l2.6 7.9 7.9 2.6-7.9 2.6L12 22.5l-2.6-7.9L1.5 12l7.9-2.6z" fill="var(--color-gold)" />
    </svg>
  );
}

/* ------------------------------------------------------------------ hero */
// Motion moment 1: a staggered entrance. The words rise, then the constellation draws itself star by star.
const STARS: [number, number][] = [[60, 330], [150, 250], [250, 285], [330, 170], [430, 205], [470, 90], [380, 60]];

function Constellation() {
  const path = STARS.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
  return (
    <svg viewBox="0 0 520 400" className="h-auto w-full" role="img" aria-label="A constellation drawn by a reaching hand">
      <motion.path
        d={path}
        fill="none"
        stroke="var(--color-gold)"
        strokeWidth="1.5"
        strokeOpacity="0.7"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 2.4, ease: "easeInOut", delay: 0.9 }}
      />
      {STARS.map(([x, y], i) => (
        <motion.g
          key={i}
          initial={{ opacity: 0, scale: 0.4 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: EASE, delay: 0.9 + i * 0.34 }}
          style={{ transformOrigin: `${x}px ${y}px` }}
        >
          <circle cx={x} cy={y} r="18" fill="var(--color-gold)" opacity="0.12" />
          <circle cx={x} cy={y} r={i === STARS.length - 1 ? 7 : 5} fill="var(--color-ivory)" />
        </motion.g>
      ))}
    </svg>
  );
}

const heroContainer: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.14, delayChildren: 0.1 } } };
const heroItem: Variants = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.8, ease: EASE } },
};

function Hero() {
  return (
    <section id="top" className="mx-auto grid max-w-[1200px] items-center gap-16 px-6 pb-[96px] pt-[96px] md:grid-cols-[1.1fr_1fr] md:px-10 md:pb-[160px] md:pt-[128px]">
      <motion.div variants={heroContainer} initial="hidden" animate="show">
        <motion.h1 variants={heroItem} className="font-display text-5xl font-medium leading-[1.05] tracking-tight text-ivory md:text-7xl">
          Every reach lights a star.
        </motion.h1>
        <motion.p variants={heroItem} className="mt-8 max-w-[34ch] text-xl leading-relaxed text-mist">
          A webcam game for home stroke rehab that turns each repetition into a constellation your therapist can follow.
        </motion.p>
        <motion.div variants={heroItem} className="mt-10">
          <a href="#pricing" className="inline-flex items-center gap-3 rounded-full bg-gold px-8 py-4 text-lg font-semibold text-night transition-transform hover:-translate-y-0.5">
            Start your first constellation
          </a>
        </motion.div>
      </motion.div>
      <div className="mx-auto w-full max-w-[520px]">
        <Constellation />
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ features */
// Motion moment 3 (signature hover): a feature's star lights up gold when you hover the card.
function FeatureStar() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true" className="transition-all duration-500 group-hover:drop-shadow-[0_0_10px_rgba(242,196,90,0.9)]">
      <path d="M12 1.5l2.6 7.9 7.9 2.6-7.9 2.6L12 22.5l-2.6-7.9L1.5 12l7.9-2.6z"
        className="fill-line transition-colors duration-500 group-hover:fill-gold" />
    </svg>
  );
}

function Features() {
  return (
    <section id="features" className="mx-auto max-w-[1200px] px-6 py-[96px] md:px-10 md:py-[160px]">
      <Reveal className="max-w-[680px]">
        <Eyebrow>How it works</Eyebrow>
        <h2 className="font-display text-4xl font-medium leading-tight md:text-5xl">
          Rehab exercises, played as a quiet battle under the stars.
        </h2>
      </Reveal>

      <div className="mt-[64px] grid gap-6 md:grid-cols-12">
        {/* Wide card with a real screenshot */}
        <Reveal className="md:col-span-7">
          <article className="group h-full overflow-hidden rounded-3xl border border-line bg-night-2 transition-colors duration-500 hover:border-gold/60">
            <div className="p-10">
              <FeatureStar />
              <h3 className="mt-6 font-display text-3xl">Reach to cast a spell</h3>
              <p className="mt-4 max-w-[46ch] text-mist">
                Pick a constellation, then touch each star with your fingertip. Stars sit just inside the reach you
                showed during calibration, never beyond what is safe for you.
              </p>
            </div>
            <Image src="/spell-picker.png" alt="The spell picker: eight constellations with their cost and damage"
              width={1280} height={720} className="w-full border-t border-line" sizes="(min-width: 768px) 640px, 100vw" />
          </article>
        </Reveal>

        {/* Tall text card */}
        <Reveal className="md:col-span-5" delay={0.1}>
          <article className="group flex h-full flex-col justify-between rounded-3xl border border-line p-10 transition-colors duration-500 hover:border-gold/60">
            <div>
              <FeatureStar />
              <h3 className="mt-6 font-display text-3xl">Your body stays honest</h3>
              <p className="mt-4 max-w-[40ch] text-mist">
                The game watches your shoulders. Lean instead of reaching and the star turns red until you sit tall
                again, so every rep trains the arm, not the habit.
              </p>
            </div>
            <div className="mt-10">
              <p className="font-display text-6xl text-gold">0.4 s</p>
              <p className="mt-2 max-w-[30ch] text-base text-mist">a lean has to last before it counts, so a wobble never does</p>
            </div>
          </article>
        </Reveal>

        {/* Short horizontal card */}
        <Reveal className="md:col-span-5">
          <article className="group h-full rounded-3xl border border-line p-10 transition-colors duration-500 hover:border-gold/60">
            <FeatureStar />
            <h3 className="mt-6 font-display text-3xl">Grip to block</h3>
            <p className="mt-4 max-w-[40ch] text-mist">
              Each turn you attack or block. A block is one slow fist, held for three seconds, then a wide open hand.
              Real grip practice, hidden inside a shield.
            </p>
          </article>
        </Reveal>

        {/* Wide card with the progress screenshot */}
        <Reveal className="md:col-span-7" delay={0.1}>
          <article className="group grid h-full overflow-hidden rounded-3xl border border-line bg-night-2 transition-colors duration-500 hover:border-gold/60 md:grid-cols-[1.25fr_1fr]">
            <div className="p-10">
              <FeatureStar />
              <h3 className="mt-6 font-display text-3xl">Progress your therapist sees</h3>
              <p className="mt-4 text-mist">
                Reach, accuracy, smoothness, tremor and grip are measured every session, with a recorded replay and a
                report your coach reads from anywhere.
              </p>
            </div>
            <div className="relative min-h-[240px] border-t border-line md:border-l md:border-t-0">
              <Image src="/progress.png" alt="The progress screen: trends for reach, accuracy and pain" fill
                className="object-cover object-left" sizes="(min-width: 768px) 420px, 100vw" />
            </div>
          </article>
        </Reveal>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ proof */
function Proof() {
  const stats = [
    ["32", "battles each, played by two simulated patients over 16 days"],
    ["9", "rehab measures recorded in every session"],
    ["30 fps", "on an ordinary laptop webcam, no extra hardware"],
  ];
  return (
    <section id="proof" className="border-y border-line bg-night-2">
      <div className="mx-auto grid max-w-[1200px] gap-16 px-6 py-[96px] md:grid-cols-[1fr_1.4fr] md:px-10 md:py-[128px]">
        <Reveal>
          <Eyebrow>Results so far</Eyebrow>
          <h2 className="font-display text-4xl font-medium leading-tight md:text-5xl">Measured, not guessed.</h2>
          <p className="mt-6 max-w-[42ch] text-mist">
            We tested Asterism by letting simulated patients play the real game for weeks. The report caught improving
            reach in one and rising shoulder pain in the other, the two things a therapist most needs to see.
          </p>
        </Reveal>
        <div className="grid gap-10 sm:grid-cols-3 md:grid-cols-1 lg:grid-cols-3">
          {stats.map(([value, label], i) => (
            <Reveal key={value} delay={i * 0.1}>
              <p className="font-display text-5xl text-gold">{value}</p>
              <p className="mt-3 text-base text-mist">{label}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ pricing */
function Pricing() {
  const plans = [
    { name: "Patient", price: "Free", note: "forever", points: ["The full game and every battle", "Your own progress screen", "Link to a coach of your choice"], cta: "Download the game", featured: false },
    { name: "Coach", price: "$29", note: "per month", points: ["Up to 25 linked patients", "Session replays and reports", "Written feedback in the game", "Open or close your practice"], cta: "Start a 30-day trial", featured: true },
    { name: "Clinic", price: "Let's talk", note: "for teams", points: ["Every coach on one account", "Shared patient caseloads", "Help with data agreements"], cta: "Contact us", featured: false },
  ];
  return (
    <section id="pricing" className="mx-auto max-w-[1200px] px-6 py-[96px] md:px-10 md:py-[160px]">
      <Reveal className="mx-auto max-w-[640px] text-center">
        <Eyebrow>Pricing</Eyebrow>
        <h2 className="font-display text-4xl font-medium leading-tight md:text-5xl">Free for patients. Simple for coaches.</h2>
      </Reveal>
      <div className="mt-[64px] grid items-stretch gap-6 md:grid-cols-3">
        {plans.map((plan, i) => (
          <Reveal key={plan.name} delay={i * 0.08}>
            <article className={`flex h-full flex-col rounded-3xl border p-10 ${plan.featured ? "border-gold bg-night-2" : "border-line"}`}>
              <h3 className="text-lg font-semibold">{plan.name}</h3>
              <p className="mt-6 font-display text-5xl">{plan.price}</p>
              <p className="mt-1 text-base text-mist">{plan.note}</p>
              <ul className="mt-8 flex-1 space-y-3 text-base text-mist">
                {plan.points.map((point) => (
                  <li key={point} className="flex gap-3"><span className="text-gold" aria-hidden="true">✦</span>{point}</li>
                ))}
              </ul>
              <a href={plan.name === "Patient" ? REPO : "#faq"}
                className={`mt-10 rounded-full px-6 py-3 text-center text-base font-semibold transition-transform hover:-translate-y-0.5 ${plan.featured ? "bg-gold text-night" : "border border-line text-ivory hover:border-ivory"}`}>
                {plan.cta}
              </a>
            </article>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ faq */
function Faq() {
  const items = [
    ["Do I need any special equipment?", "No. A laptop with a webcam and a chair is enough. Sit three to four feet from the screen and the game finds you."],
    ["Is it safe to play on my own?", "The game never places a star beyond the reach you showed it, warns you when you lean, and asks how you feel after every battle. If you report a lot of pain, it tells you to stop and contact your therapist. It supports your therapy; it does not replace your therapist."],
    ["What does my coach see?", "Only patients who link to a coach are visible to them. They see your sessions, a replay of the game screen and your progress report. The replay shows your movement as stars, not your face or your home."],
    ["Can I start over or keep going?", "Both. Each run is like a saved world: continue an old one to keep its progress, or start a fresh run any time."],
  ];
  const [open, setOpen] = useState(0);
  return (
    <section id="faq" className="mx-auto grid max-w-[1200px] gap-16 px-6 pb-[96px] md:grid-cols-[1fr_1.6fr] md:px-10 md:pb-[160px]">
      <Reveal>
        <Eyebrow>Questions</Eyebrow>
        <h2 className="font-display text-4xl font-medium leading-tight md:text-5xl">The things people ask first.</h2>
      </Reveal>
      <Reveal delay={0.1}>
        <dl className="divide-y divide-line border-y border-line">
          {items.map(([q, a], i) => (
            <div key={q}>
              <dt>
                <button onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}
                  className="flex w-full items-center justify-between gap-6 py-6 text-left text-xl text-ivory">
                  {q}
                  <span className={`text-gold transition-transform duration-300 ${open === i ? "rotate-45" : ""}`} aria-hidden="true">+</span>
                </button>
              </dt>
              <dd className={`grid transition-all duration-300 ${open === i ? "grid-rows-[1fr] pb-6" : "grid-rows-[0fr]"}`}>
                <p className="max-w-[62ch] overflow-hidden text-mist">{a}</p>
              </dd>
            </div>
          ))}
        </dl>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------ footer */
function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-10 px-6 py-[64px] md:flex-row md:items-end md:justify-between md:px-10">
        <div>
          <p className="flex items-center gap-3 font-display text-3xl"><StarMark /> Asterism</p>
          <p className="mt-4 max-w-[44ch] text-base text-mist">
            Named for the small star patterns inside bigger constellations. One session is one asterism. Together they
            make your whole sky.
          </p>
        </div>
        <div className="text-base text-mist md:text-right">
          <a href={REPO} className="text-ivory underline decoration-gold underline-offset-4">Source on GitHub</a>
          <p className="mt-3">Made at Hyphen Hacks 2026. Not a medical device.</p>
        </div>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <MotionConfig reducedMotion="user">
      <Navbar />
      <main>
        <Hero />
        <Features />
        <Proof />
        <Pricing />
        <Faq />
      </main>
      <Footer />
    </MotionConfig>
  );
}

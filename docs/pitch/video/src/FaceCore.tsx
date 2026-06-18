import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  Easing,
} from "remotion";
import { loadFont as loadDisplay } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadBody } from "@remotion/google-fonts/PlusJakartaSans";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

const fontOpts = { subsets: ["latin"] as const, ignoreTooManyRequestsWarning: true };
const { fontFamily: DISPLAY } = loadDisplay("normal", { weights: ["600"], ...fontOpts });
const { fontFamily: BODY } = loadBody("normal", { weights: ["400", "500", "600"], ...fontOpts });
const { fontFamily: MONO } = loadMono("normal", { weights: ["400", "500"], ...fontOpts });

// ── palette ──
const INK = "#050507";
const MIST = "#e7e8ee";
const EMERALD = "#34e0a1";
const VIOLET = "#a99bff";

// ── scene timing (30fps) ──
// scene durations are paced to the voiceover clips in public/vo (see voiceover-script.md)
const D = {
  intro: 120,
  problem: 240,
  flow: 810,
  arch: 440,
  features: 460,
  outro: 300,
};
const OFF = {
  intro: 0,
  problem: D.intro,
  flow: D.intro + D.problem,
  arch: D.intro + D.problem + D.flow,
  features: D.intro + D.problem + D.flow + D.arch,
  outro: D.intro + D.problem + D.flow + D.arch + D.features,
};
export const TOTAL_FRAMES =
  D.intro + D.problem + D.flow + D.arch + D.features + D.outro;

// ── helpers ──
const sceneOpacity = (frame: number, dur: number) =>
  interpolate(frame, [0, 14, dur - 14, dur], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const useRise = (delay = 0, distance = 46) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200, mass: 0.7 } });
  return { opacity: s, transform: `translateY(${interpolate(s, [0, 1], [distance, 0])}px)` };
};

const card: React.CSSProperties = {
  background: "linear-gradient(180deg, rgba(22,23,30,0.92), rgba(11,12,17,0.92))",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 28,
  boxShadow: "inset 0 1px 1px rgba(255,255,255,0.06)",
};

const Eyebrow: React.FC<{ children: React.ReactNode; color?: string }> = ({ children, color = EMERALD }) => (
  <div
    style={{
      fontFamily: MONO,
      fontSize: 20,
      letterSpacing: 6,
      textTransform: "uppercase",
      color,
    }}
  >
    {children}
  </div>
);

// ── persistent background ──
const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const f = (a: number, b: number, p = 0.00018) => Math.sin(frame * p * 1000 + a) * b;
  const orb = (x: number, y: number, size: number, c: string, a: number): React.CSSProperties => ({
    position: "absolute",
    width: size,
    height: size,
    left: x,
    top: y,
    borderRadius: 9999,
    filter: "blur(150px)",
    opacity: 0.55,
    background: `radial-gradient(circle, ${c} 0%, transparent 70%)`,
    transform: `translate(${f(a, 80)}px, ${f(a + 2, 70)}px)`,
  });
  return (
    <AbsoluteFill style={{ background: INK }}>
      <div style={orb(-260, -260, 820, "#1b6b4d", 0)} />
      <div style={orb(1280, 360, 760, "#3a2f7a", 3)} />
      <div style={orb(560, 720, 700, "#0f5e63", 6)} />
      {/* vignette */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.55) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

const Brand: React.FC<{ size?: number }> = ({ size = 34 }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
    <div
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.28,
        background: `linear-gradient(135deg, ${EMERALD}, #13b07d)`,
        display: "grid",
        placeItems: "center",
      }}
    >
      <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke={INK} strokeWidth={1.7}>
        <path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" />
        <circle cx="12" cy="11" r="2.4" />
        <path d="M8.5 16c.7-1.6 2-2.4 3.5-2.4s2.8.8 3.5 2.4" />
      </svg>
    </div>
    <span style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: size * 0.62, color: "#fff", letterSpacing: -0.5 }}>
      FaceCore
    </span>
  </div>
);

// ─────────────────────── SCENE: INTRO ───────────────────────
const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const brand = spring({ frame, fps, config: { damping: 200 } });
  const line1 = useRise(14);
  const line2 = useRise(24);
  const sub = useRise(40);
  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, D.intro), justifyContent: "center", alignItems: "center" }}>
      <div style={{ transform: `scale(${interpolate(brand, [0, 1], [0.9, 1])})`, opacity: brand, marginBottom: 36 }}>
        <Brand size={64} />
      </div>
      <div style={{ textAlign: "center", fontFamily: DISPLAY, fontWeight: 600, fontSize: 96, lineHeight: 1.0, letterSpacing: -2 }}>
        <div style={{ ...line1, color: "#fff" }}>Attendance that</div>
        <div style={{ ...line2, background: `linear-gradient(120deg,#fff,${EMERALD} 55%,${VIOLET})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
          recognises faces, not badges.
        </div>
      </div>
      <div style={{ ...sub, marginTop: 30, fontFamily: MONO, fontSize: 22, color: "rgba(231,232,238,0.5)", letterSpacing: 2 }}>
        Edge AI · Self-hosted · Frappe HRMS
      </div>
    </AbsoluteFill>
  );
};

// ─────────────────────── SCENE: PROBLEM ───────────────────────
const ProblemCard: React.FC<{ delay: number; title: string; body: string }> = ({ delay, title, body }) => {
  const r = useRise(delay);
  return (
    <div style={{ ...card, ...r, flex: 1, padding: 44 }}>
      <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 34, color: "#fff", marginBottom: 14 }}>{title}</div>
      <div style={{ fontFamily: BODY, fontSize: 24, lineHeight: 1.45, color: "rgba(231,232,238,0.55)" }}>{body}</div>
    </div>
  );
};
const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useRise(0);
  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, D.problem), justifyContent: "center", padding: "0 120px" }}>
      <div style={head}>
        <Eyebrow color={VIOLET}>The status quo is broken</Eyebrow>
        <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 66, color: "#fff", letterSpacing: -1.5, marginTop: 18, marginBottom: 54, lineHeight: 1.04 }}>
          Cards get shared. Punches get faked.<br />Hours get unfair.
        </div>
      </div>
      <div style={{ display: "flex", gap: 28 }}>
        <ProblemCard delay={10} title="Buddy punching" body="RFID cards and PINs are trivially shared. Proxy attendance silently inflates payroll on every shift." />
        <ProblemCard delay={20} title="Locked-in terminals" body="Proprietary face terminals mean capex per door and closed data. Cloud SaaS can't run on-prem at all." />
        <ProblemCard delay={30} title="Unfair IN/OUT" body="Step out of frame for a moment and naive logic records 'worked 12 seconds.' Multi-camera sites produce nonsense." />
      </div>
    </AbsoluteFill>
  );
};

// ─────────────────────── SCENE: FLOW ───────────────────────
const FLOW_STEPS = [
  { n: "01", t: "Enroll", d: "Employee self-registers a webcam photo at /face. It becomes a 512-d vector — then the image is discarded." },
  { n: "02", t: "Approve", d: "HR runs the Face Profile Approval workflow. Only Approved profiles ever sync to devices." },
  { n: "03", t: "Sync to edge", d: "Each camera pulls approved embeddings incrementally and caches them locally — no per-frame network hop." },
  { n: "04", t: "Recognise", d: "Edge detects, tracks & matches in milliseconds. Passive liveness blocks photo & video spoofs." },
  { n: "05", t: "Check-in", d: "A signed event is posted; the server creates the Employee Checkin. HRMS derives attendance natively." },
];
const RIBBON = [
  "POST /embed  X-Secret:****  →  { embedding:[512], det:0.91 }",
  "workflow: Draft → Pending → Approved ✓",
  "GET get_face_data?since=…  →  142 approved embeddings synced",
  "edge match cosine=0.87  liveness=0.94  track#7  ✓ live",
  "POST post_event  →  Employee Checkin HR-EMP-00001 @ 09:01:14",
];
const Flow: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useRise(0);
  const per = Math.floor((D.flow - 40) / FLOW_STEPS.length);
  const active = Math.min(FLOW_STEPS.length - 1, Math.floor(Math.max(0, frame - 30) / per));
  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, D.flow), justifyContent: "center", padding: "0 110px" }}>
      <div style={{ ...head, textAlign: "center", marginBottom: 46 }}>
        <Eyebrow>End-to-end in five moves</Eyebrow>
        <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 62, color: "#fff", letterSpacing: -1.4, marginTop: 16, lineHeight: 1.04 }}>
          From a face in front of a camera<br />to attendance in HRMS.
        </div>
      </div>

      {/* step rail */}
      <div style={{ display: "flex", gap: 18 }}>
        {FLOW_STEPS.map((s, i) => {
          const on = i === active;
          const seen = i <= active;
          return (
            <div
              key={s.n}
              style={{
                flex: 1,
                padding: 30,
                borderRadius: 24,
                border: `1px solid ${on ? "rgba(52,224,161,0.4)" : "rgba(255,255,255,0.08)"}`,
                background: on ? "rgba(52,224,161,0.08)" : "rgba(255,255,255,0.02)",
                transform: on ? "translateY(-10px)" : "translateY(0)",
                boxShadow: on ? "0 30px 70px -30px rgba(52,224,161,0.6)" : "none",
                opacity: seen ? 1 : 0.4,
                transition: "all 0.3s",
              }}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: 16,
                  display: "grid",
                  placeItems: "center",
                  fontFamily: MONO,
                  fontSize: 22,
                  marginBottom: 22,
                  color: on ? INK : MIST,
                  background: on ? `linear-gradient(135deg,${EMERALD},#13b07d)` : "rgba(255,255,255,0.04)",
                  border: on ? "none" : "1px solid rgba(255,255,255,0.1)",
                }}
              >
                {s.n}
              </div>
              <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 28, color: "#fff", marginBottom: 12 }}>{s.t}</div>
              <div style={{ fontFamily: BODY, fontSize: 19, lineHeight: 1.4, color: "rgba(231,232,238,0.55)" }}>{s.d}</div>
            </div>
          );
        })}
      </div>

      {/* data ribbon */}
      <div style={{ ...card, marginTop: 34, padding: 28, borderRadius: 22, background: "rgba(0,0,0,0.45)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: MONO, fontSize: 18, color: "rgba(231,232,238,0.4)", marginBottom: 14 }}>
          <span style={{ width: 12, height: 12, borderRadius: 99, background: EMERALD }} /> camera → edge → frappe
        </div>
        <div style={{ fontFamily: MONO, fontSize: 24, color: EMERALD }}>{RIBBON[active]}</div>
      </div>
    </AbsoluteFill>
  );
};

// ─────────────────────── SCENE: ARCHITECTURE ───────────────────────
const ArchNode: React.FC<{ delay: number; tag: string; title: string; body: string; port: string; accent?: string }> = ({
  delay, tag, title, body, port, accent = "rgba(255,255,255,0.08)",
}) => {
  const r = useRise(delay);
  return (
    <div style={{ ...r, flex: 1, padding: 34, borderRadius: 24, background: "rgba(255,255,255,0.02)", border: `1px solid ${accent}`, display: "flex", flexDirection: "column", minHeight: 280 }}>
      <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 4, textTransform: "uppercase", color: EMERALD, marginBottom: 16 }}>{tag}</div>
      <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 30, color: "#fff", marginBottom: 14 }}>{title}</div>
      <div style={{ fontFamily: BODY, fontSize: 20, lineHeight: 1.4, color: "rgba(231,232,238,0.5)" }}>{body}</div>
      <div style={{ marginTop: "auto", paddingTop: 18, fontFamily: MONO, fontSize: 17, color: "rgba(231,232,238,0.35)" }}>{port}</div>
    </div>
  );
};
const Architecture: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useRise(0);
  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, D.arch), justifyContent: "center", padding: "0 110px" }}>
      <div style={{ ...head, marginBottom: 44 }}>
        <Eyebrow>Dual-engine architecture</Eyebrow>
        <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 60, color: "#fff", letterSpacing: -1.4, marginTop: 16, lineHeight: 1.05 }}>
          Two engines, two jobs — deliberately not merged.
        </div>
      </div>
      <div style={{ display: "flex", gap: 20 }}>
        <ArchNode delay={8} tag="System of record" title="Frappe HRMS" body="Profiles · approval workflow · device registry · events · /face portal" port=":8000" />
        <ArchNode delay={16} tag="Single AI gateway" title="ai_service" body="FastAPI · /embed real-time · /analyze proxy · secret-gated" port=":8080" accent="rgba(52,224,161,0.3)" />
        <ArchNode delay={24} tag="On the edge" title="edge_client" body="Multi-camera · IoU tracking · NumPy match · liveness · offline SQLite" port="RTSP / ONVIF" />
        <ArchNode delay={32} tag="Analytics sidecar" title="DeepFace stack" body="Docker · demographics & emotion · Weaviate · MinIO — async, offline-only" port=":5005" accent="rgba(169,155,255,0.25)" />
      </div>
    </AbsoluteFill>
  );
};

// ─────────────────────── SCENE: FEATURES ───────────────────────
const FEATURES = [
  ["Sub-second edge match", "512-d ArcFace, NumPy cosine — sub-ms up to ~50k faces."],
  ["Passive liveness", "MiniFASNet blocks photo & screen-replay. No blink, no head-turn."],
  ["Fair presence-hours", "Sessions per area — short breaks don't end the day."],
  ["Cross-camera cooldown", "Dozens of sightings collapse to one check-in per window."],
  ["Device fleet health", "Heartbeats, last-seen, app version, stale detection."],
  ["Privacy by design", "Irreversible embeddings; the photo is discarded."],
  ["Full audit + offline queue", "Every event scored & deduped; SQLite drains on reconnect."],
  ["Native HRMS", "Feeds Frappe's shift auto-attendance — no parallel pipeline."],
];
const Features: React.FC = () => {
  const frame = useCurrentFrame();
  const head = useRise(0);
  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, D.features), justifyContent: "center", padding: "0 110px" }}>
      <div style={{ ...head, marginBottom: 40 }}>
        <Eyebrow>Capabilities</Eyebrow>
        <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 60, color: "#fff", letterSpacing: -1.4, marginTop: 16 }}>
          Everything a serious deployment needs.
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 20 }}>
        {FEATURES.map(([t, d], i) => {
          const r = useRise(6 + i * 4, 30);
          return (
            <div key={t} style={{ ...card, ...r, padding: 30, borderRadius: 22, minHeight: 190 }}>
              <div style={{ width: 14, height: 14, borderRadius: 99, background: i % 2 ? VIOLET : EMERALD, marginBottom: 22 }} />
              <div style={{ fontFamily: DISPLAY, fontWeight: 600, fontSize: 25, color: "#fff", marginBottom: 12, lineHeight: 1.1 }}>{t}</div>
              <div style={{ fontFamily: BODY, fontSize: 18, lineHeight: 1.4, color: "rgba(231,232,238,0.5)" }}>{d}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ─────────────────────── SCENE: OUTRO ───────────────────────
const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const brand = spring({ frame: frame - 6, fps, config: { damping: 200 } });
  const head = useRise(18);
  const sub = useRise(32);
  const tags = useRise(46);
  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, D.outro), justifyContent: "center", alignItems: "center" }}>
      <div style={{ opacity: brand, transform: `scale(${interpolate(brand, [0, 1], [0.92, 1])})`, marginBottom: 30 }}>
        <Brand size={56} />
      </div>
      <div style={{ ...head, textAlign: "center", fontFamily: DISPLAY, fontWeight: 600, fontSize: 92, color: "#fff", letterSpacing: -2, lineHeight: 1.0 }}>
        Put a face to every{" "}
        <span style={{ background: `linear-gradient(120deg,#fff,${EMERALD} 60%,${VIOLET})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
          check-in.
        </span>
      </div>
      <div style={{ ...sub, marginTop: 28, fontFamily: BODY, fontSize: 26, color: "rgba(231,232,238,0.55)", maxWidth: 900, textAlign: "center", lineHeight: 1.4 }}>
        Self-hosted, privacy-first attendance on the cameras you already own and the HRMS you already trust.
      </div>
      <div style={{ ...tags, marginTop: 40, fontFamily: MONO, fontSize: 20, color: "rgba(231,232,238,0.4)", letterSpacing: 2 }}>
        tb-facecore · tb_face_attendance · by Techbird IT
      </div>
    </AbsoluteFill>
  );
};

// ─────────────────────── ROOT COMPOSITION ───────────────────────
export const FaceCore: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: INK, fontFamily: BODY }}>
      <Background />
      <Sequence from={OFF.intro} durationInFrames={D.intro}><Intro /></Sequence>
      <Sequence from={OFF.problem} durationInFrames={D.problem}><Problem /></Sequence>
      <Sequence from={OFF.flow} durationInFrames={D.flow}><Flow /></Sequence>
      <Sequence from={OFF.arch} durationInFrames={D.arch}><Architecture /></Sequence>
      <Sequence from={OFF.features} durationInFrames={D.features}><Features /></Sequence>
      <Sequence from={OFF.outro} durationInFrames={D.outro}><Outro /></Sequence>

      {/* ── Voiceover (Samantha TTS) — one clip per scene, placed at the scene's start ── */}
      <Sequence from={OFF.intro}><Audio src={staticFile("vo/scene_1.mp3")} /></Sequence>
      <Sequence from={OFF.problem}><Audio src={staticFile("vo/scene_2.mp3")} /></Sequence>
      <Sequence from={OFF.flow}><Audio src={staticFile("vo/scene_3.mp3")} /></Sequence>
      <Sequence from={OFF.arch}><Audio src={staticFile("vo/scene_4.mp3")} /></Sequence>
      <Sequence from={OFF.features}><Audio src={staticFile("vo/scene_5.mp3")} /></Sequence>
      <Sequence from={OFF.outro}><Audio src={staticFile("vo/scene_6.mp3")} /></Sequence>
    </AbsoluteFill>
  );
};

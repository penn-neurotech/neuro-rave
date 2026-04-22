import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getApiBase } from "../apiBase";
import { useEEGStream } from "../hooks/useEEGStream";
import { EEGFeatures } from "../hooks/useEEGStream";
import { WS_PORT } from "../constants";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

const WS_URL = import.meta.env.VITE_WS_URL ?? `ws://localhost:${WS_PORT}/ws`;

const moodColors: Record<string, string> = {
  calm: "#60a5fa",
  focus: "#34d399",
  hype: "#f97316",
  deep_focus: "#a78bfa",
};

const defaultPlaylistLabels: Record<string, string> = {
  calm: "Ambient Reset",
  focus: "Deep Focus Flow",
  hype: "High Energy Boost",
  deep_focus: "Deep Focus Flow",
};

function playlistLabel(mood: string, labels: Record<string, string>): string {
  if (labels[mood]) return labels[mood];
  if (mood === "deep_focus" && labels.focus) return labels.focus;
  return defaultPlaylistLabels[mood] ?? mood.replace(/_/g, " ");
}


function formatStreak(sec: number): string {
  if (sec < 60) return `${Math.floor(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}m ${s}s`;
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatusBadge({ text, color }: { text: string; color: string }) {
  return (
    <span className="status-badge" style={{ backgroundColor: color }}>
      {text}
    </span>
  );
}

function LogItem({ text, time }: { text: string; time: string }) {
  return (
    <div className="log-item">
      <span className="log-time">{time}</span>
      <span>{text}</span>
    </div>
  );
}

function LiveWaveform({
  channel,
  color,
}: {
  channel: Float32Array;
  color: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || channel.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);

    let max = 0;
    for (let i = 0; i < channel.length; i++) {
      if (Math.abs(channel[i]) > max) max = Math.abs(channel[i]);
    }
    if (max === 0) return;

    const mid = height / 2;
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = 0.7;

    for (let i = 0; i < channel.length; i++) {
      const x = (i / (channel.length - 1)) * width;
      const y = mid - (channel[i] / max) * (mid - 4);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke();
  });

  return (
    <canvas
      ref={canvasRef}
      width={800}
      height={64}
      style={{ width: "100%", height: 64 }}
    />
  );
}

function BandVisualizer({ features }: { features: EEGFeatures | null }) {
  const bands = [
    { label: "Energy", value: features?.energy ?? 0, color: "#f97316" },
    { label: "Focus", value: features?.focus ?? 0, color: "#60a5fa" },
  ];

  return (
    <div className="band-viz">
      {bands.map((b) => (
        <div key={b.label} className="band-bar-group">
          <div className="band-bar-track">
            <div
              className="band-bar-fill"
              style={{
                height: `${Math.max(b.value * 100, 2)}%`,
                background: b.color,
                boxShadow: `0 0 8px ${b.color}88`,
              }}
            />
          </div>
          <div className="band-label">{b.label}</div>
        </div>
      ))}
    </div>
  );
}

interface MoodSegment {
  mood: string;
  start: number;
  end: number | null;
}

function MoodTimeline({ segments }: { segments: MoodSegment[] }) {
  if (segments.length === 0) return null;

  const now = Date.now();
  const totalMs = now - segments[0].start;
  if (totalMs < 1000) return null;

  return (
    <section className="panel mood-timeline-panel">
      <h2>Session Mood Timeline</h2>
      <div className="mood-timeline-bar">
        {segments.map((seg, i) => {
          const end = seg.end ?? now;
          const pct = ((end - seg.start) / totalMs) * 100;
          return (
            <div
              key={i}
              className="mood-timeline-segment"
              style={{
                width: `${pct}%`,
                background: moodColors[seg.mood] ?? "#64748b",
              }}
              title={`${seg.mood.replace(/_/g, " ")} — ${formatStreak((end - seg.start) / 1000)}`}
            />
          );
        })}
      </div>
      <div className="mood-timeline-legend">
        {Array.from(new Set(segments.map((s) => s.mood))).map((m) => (
          <div key={m} className="mood-timeline-legend-item">
            <span
              className="mood-timeline-dot"
              style={{ background: moodColors[m] ?? "#64748b" }}
            />
            <span>{m.replace(/_/g, " ")}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

interface HistoryPoint {
  time: string;
  energy: number;
  focus: number;
}

interface NowPlayingTrack {
  name: string;
  artists: string[];
  album?: string | null;
  image_url?: string | null;
  duration_ms?: number | null;
}

interface DashboardPlayerState {
  paused: boolean;
  is_playing: boolean;
  progress_ms?: number | null;
  track?: NowPlayingTrack | null;
}

function HistoryLineChart({
  history,
  metricKey,
  color,
  title,
}: {
  history: HistoryPoint[];
  metricKey: "energy" | "focus";
  color: string;
  title: string;
}) {
  const chartData = history.map((point) => ({
    time: point.time,
    shortTime: point.time.slice(-8),
    value: Math.round(point[metricKey] * 100),
  }));

  return (
    <div className="chart-card real-chart-card">
      <div className="chart-title">{title}</div>
      <div className="real-chart-wrap">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart
            data={chartData}
            margin={{ top: 10, right: 12, left: -18, bottom: 0 }}
          >
            <CartesianGrid
              stroke="rgba(148, 163, 184, 0.12)"
              vertical={false}
            />
            <XAxis
              dataKey="shortTime"
              tick={{ fill: "#94a3b8", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: "#94a3b8", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={34}
            />
            <Tooltip
              contentStyle={{
                background: "rgba(15, 23, 42, 0.96)",
                border: "1px solid rgba(120, 160, 255, 0.18)",
                borderRadius: "12px",
                color: "#e2e8f0",
              }}
              labelStyle={{ color: "#cbd5e1" }}
              formatter={(value) => {
                const n = Number(value);
                return [`${Number.isFinite(n) ? n : 0}%`, title];
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={3}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              isAnimationActive={true}
              animationDuration={500}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function EmptyChartCard({ title }: { title: string }) {
  return (
    <div className="chart-card empty-chart-card">
      <div className="chart-title">{title}</div>
      <div className="empty-chart-placeholder">
        <div className="empty-chart-line short" />
        <div className="empty-chart-line medium" />
        <div className="empty-chart-line tall" />
        <div className="empty-chart-line medium" />
        <div className="empty-chart-line short" />
      </div>
      <div className="small-text">Waiting for live feature updates...</div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function LiveDashboard() {
  const { buffer, features, connected } = useEEGStream(WS_URL);
  const navigate = useNavigate();
  const api = useMemo(() => getApiBase(), []);

  const [playbackKind, setPlaybackKind] = useState<"playlist" | "pool">("playlist");
  const [spotifyTokenConnected, setSpotifyTokenConnected] = useState(false);
  const [playbackPaused, setPlaybackPaused] = useState(false);
  const [isSpotifyPlaying, setIsSpotifyPlaying] = useState(false);
  const [nowPlaying, setNowPlaying] = useState<NowPlayingTrack | null>(null);
  const [nowPlayingDurationMs, setNowPlayingDurationMs] = useState<number | null>(null);
  const [displayProgressMs, setDisplayProgressMs] = useState<number | null>(null);
  const [playerActionBusy, setPlayerActionBusy] = useState(false);
  const [volume, setVolume] = useState(50);
  // Ref-based interpolation so the tick closure never goes stale
  const progressRef = useRef({ ms: 0, duration: 0, playing: false });
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [moodTimeline, setMoodTimeline] = useState<MoodSegment[]>([]);
  const [spotifyLabels, setSpotifyLabels] = useState<Record<string, string>>({});
  const [logs, setLogs] = useState([
    { time: new Date().toLocaleTimeString(), text: "Dashboard started" },
  ]);
  const prevMoodRef = useRef<string | null>(null);

  const mood = features?.mood ?? "calm";
  const moodColor = moodColors[mood] ?? "#64748b";

  const currentPlaylist = useMemo(
    () => playlistLabel(mood, spotifyLabels),
    [mood, spotifyLabels],
  );

  // ── Feature 1: mood-reactive background ──────────────────────────────────────
  useEffect(() => {
    document.body.style.background = [
      `radial-gradient(circle at top left, ${hexToRgba(moodColor, 0.15)}, transparent 32%)`,
      `radial-gradient(circle at top right, ${hexToRgba(moodColor, 0.08)}, transparent 32%)`,
      "#0f172a",
    ].join(", ");
    return () => { document.body.style.background = ""; };
  }, [moodColor]);

  // ── Feature 5: mood timeline tracking ────────────────────────────────────────
  useEffect(() => {
    if (!features) return;
    setMoodTimeline((prev) => {
      const now = Date.now();
      if (prev.length === 0) return [{ mood: features.mood, start: now, end: null }];
      const last = prev[prev.length - 1];
      if (last.mood === features.mood) return prev;
      return [
        ...prev.slice(-30).map((s, i, arr) =>
          i === arr.length - 1 ? { ...s, end: now } : s,
        ),
        { mood: features.mood, start: now, end: null },
      ];
    });
  }, [features?.mood]);

  // ── Progress interpolation ────────────────────────────────────────────────────
  // Keep ref in sync with play/pause state so the tick closure is never stale.
  useEffect(() => {
    progressRef.current.playing = isSpotifyPlaying && !playbackPaused;
  }, [isSpotifyPlaying, playbackPaused]);

  // Single long-lived tick — advances display progress every second while playing.
  useEffect(() => {
    const id = setInterval(() => {
      if (!progressRef.current.playing) return;
      const next = progressRef.current.ms + 1000;
      const cap = progressRef.current.duration || Infinity;
      progressRef.current.ms = Math.min(next, cap);
      setDisplayProgressMs(progressRef.current.ms);
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Data fetching ─────────────────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${api}/spotify/dashboard/playback-mode`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: null | { mode?: string }) => {
        if (!data?.mode) return;
        setPlaybackKind(data.mode === "pool" ? "pool" : "playlist");
      })
      .catch(() => {});
  }, [api]);

  const fetchPlayerState = useCallback(async () => {
    const response = await fetch(`${api}/spotify/dashboard/player`);
    if (!response.ok) return;
    const data: DashboardPlayerState = await response.json();
    setPlaybackPaused(Boolean(data.paused));
    setIsSpotifyPlaying(Boolean(data.is_playing));
    setNowPlaying(data.track ?? null);
    const prog = typeof data.progress_ms === "number" ? data.progress_ms : null;
    const dur = typeof data.track?.duration_ms === "number" ? data.track.duration_ms : null;
    setNowPlayingDurationMs(dur);
    if (prog !== null) {
      progressRef.current.ms = prog;
      setDisplayProgressMs(prog);
    }
    if (dur !== null) progressRef.current.duration = dur;
  }, [api]);

  useEffect(() => {
    fetchPlayerState().catch(() => {});
    const id = window.setInterval(() => { fetchPlayerState().catch(() => {}); }, 5000);
    return () => window.clearInterval(id);
  }, [fetchPlayerState]);

  useEffect(() => {
    fetch(`${api}/spotify/setup/status`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: null | { refresh_token_configured?: boolean }) => {
        setSpotifyTokenConnected(Boolean(data?.refresh_token_configured));
      })
      .catch(() => setSpotifyTokenConnected(false));
  }, [api]);

  useEffect(() => {
    fetch(`${api}/spotify/playlists/mapping/display`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: null | Record<string, { name?: string }>) => {
        if (!data) return;
        const next: Record<string, string> = {};
        if (data.calm?.name) next.calm = data.calm.name;
        if (data.focus?.name) next.focus = data.focus.name;
        if (data.hype?.name) next.hype = data.hype.name;
        if (data.deep_focus?.name) next.deep_focus = data.deep_focus.name;
        if (Object.keys(next).length) setSpotifyLabels(next);
      })
      .catch(() => {});
  }, [api]);

  useEffect(() => {
    if (!features) return;
    const now = new Date().toLocaleTimeString();
    setHistory((prev) =>
      [...prev, { time: now, energy: features.energy, focus: features.focus }].slice(-20),
    );
    const prevMood = prevMoodRef.current;
    if (prevMood !== null && features.mood !== prevMood) {
      setLogs((prev) =>
        [{ time: now, text: `Mood changed from ${prevMood} to ${features.mood}` }, ...prev].slice(0, 8),
      );
      if (playbackKind === "playlist") {
        const name = playlistLabel(features.mood, spotifyLabels);
        setLogs((prev) =>
          [{
            time: now,
            text: playbackPaused
              ? `Playback paused — holding "${name}" until resume`
              : `Playlist mode → context "${name}"`,
          }, ...prev].slice(0, 8),
        );
      } else {
        setLogs((prev) =>
          [{
            time: now,
            text: playbackPaused
              ? `Playback paused — pool mode changes are locked`
              : `Pool mode → mood ${features.mood} (nearest track from CSV)`,
          }, ...prev].slice(0, 8),
        );
      }
    }
    prevMoodRef.current = features.mood;
  }, [features, playbackKind, playbackPaused, spotifyLabels]);

  const channels: Float32Array[] = buffer
    ? buffer.getData().map((ch) => new Float32Array(ch))
    : [];

  // ── Playback actions ──────────────────────────────────────────────────────────
  const postPlaybackMode = async (mode: "playlist" | "pool") => {
    await fetch(`${api}/spotify/dashboard/playback-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    setPlaybackKind(mode);
  };

  const onSkipNext = async () => {
    setPlayerActionBusy(true);
    try {
      const response = await fetch(`${api}/spotify/dashboard/next`, { method: "POST" });
      if (response.ok) {
        const data = (await response.json().catch(() => null)) as { paused?: boolean } | null;
        const nowUnlocked = data?.paused === false;
        if (nowUnlocked) {
          setPlaybackPaused(false);
          setLogs((prev) =>
            [{
              time: new Date().toLocaleTimeString(),
              text: "Next track pressed — playback unlocked",
            }, ...prev].slice(0, 8),
          );
        }
      }
    } finally {
      setPlayerActionBusy(false);
      setTimeout(() => fetchPlayerState().catch(() => {}), 600);
    }
  };

  const onSkipPrevious = async () => {
    setPlayerActionBusy(true);
    try {
      const response = await fetch(`${api}/spotify/dashboard/previous`, { method: "POST" });
      if (response.ok) {
        const data = (await response.json().catch(() => null)) as { paused?: boolean } | null;
        const nowUnlocked = data?.paused === false;
        if (nowUnlocked) {
          setPlaybackPaused(false);
          setLogs((prev) =>
            [{
              time: new Date().toLocaleTimeString(),
              text: "Previous track pressed — playback unlocked",
            }, ...prev].slice(0, 8),
          );
        }
      }
    } finally {
      setPlayerActionBusy(false);
      setTimeout(() => fetchPlayerState().catch(() => {}), 600);
    }
  };

  const onVolumeCommit = (e: React.SyntheticEvent<HTMLInputElement>) => {
    const vol = Number((e.target as HTMLInputElement).value);
    fetch(`${api}/spotify/dashboard/volume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ volume_percent: vol }),
    }).catch(() => {});
  };

  const onPausePlayback = async () => {
    setPlayerActionBusy(true);
    try {
      const response = await fetch(`${api}/spotify/dashboard/pause`, { method: "POST" });
      if (response.ok) {
        setPlaybackPaused(true);
        setLogs((prev) =>
          [{ time: new Date().toLocaleTimeString(), text: "Playback paused — auto-switching is locked" }, ...prev].slice(0, 8),
        );
      }
    } finally {
      setPlayerActionBusy(false);
      fetchPlayerState().catch(() => {});
    }
  };

  const onResumePlayback = async () => {
    setPlayerActionBusy(true);
    try {
      const response = await fetch(`${api}/spotify/dashboard/resume`, { method: "POST" });
      if (response.ok) {
        setPlaybackPaused(false);
        setLogs((prev) =>
          [{ time: new Date().toLocaleTimeString(), text: "Playback resumed — auto-switching unlocked" }, ...prev].slice(0, 8),
        );
      }
    } finally {
      setPlayerActionBusy(false);
      fetchPlayerState().catch(() => {});
    }
  };

  const connectSpotifyHref = `${api}/spotify/oauth/authorize`;

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-text">
          <h1>EEG-Powered Music Dashboard</h1>
          <p className="subtitle">
            Frontend dashboard for live brain metrics, mood detection, and music response.
          </p>
        </div>
        <div className="topbar-status">
          <StatusBadge
            text={connected ? "Connected" : "Connecting"}
            color={connected ? "#16a34a" : "#dc2626"}
          />
          <StatusBadge
            text={`Spotify: ${playbackKind}`}
            color="#1d4ed8"
          />
          <StatusBadge
            text={playbackPaused ? "Playback locked" : "Playback live"}
            color={playbackPaused ? "#b45309" : "#16a34a"}
          />
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="hero-grid">
        <div className="card mood-hero">
          <div className="section-label">Current Mood</div>
          <div className="mood-hero-content">
            <div className="mood-hero-text">
              <h2>{mood.replace(/_/g, " ").toUpperCase()}</h2>
              <p>Mood is classified from EEG-derived energy values.</p>
              <span className="mood-meta">
                {connected ? "Live signal active" : "Waiting for signal"}
              </span>
            </div>
            <div
              className="mood-orb"
              style={{ backgroundColor: moodColor, boxShadow: `0 0 40px ${hexToRgba(moodColor, 0.5)}` }}
            >
              {mood.replace(/_/g, " ").toUpperCase()}
            </div>
          </div>

          <div className="legend-row">
            {(["calm", "deep_focus", "focus", "hype"] as const).map((m) => (
              <span key={m} className={`legend-pill ${mood === m ? "active" : ""}`}>
                {m.replace(/_/g, " ")}
              </span>
            ))}
          </div>

          {/* Feature 2: live waveform */}
          {channels.length > 0 && (
            <div className="mood-waveform">
              <LiveWaveform channel={channels[0]} color={moodColor} />
            </div>
          )}
        </div>

        <div className="card eeg-status-card">
          <div className="section-label">Live EEG Status</div>

          <div className="status-list">
            <div className="status-row">
              <span className={`status-dot ${connected ? "live" : "dead"}`} />
              <span>{connected ? "Connected to EEG stream" : "Connecting…"}</span>
            </div>
            <div className="status-row">
              <span className={`status-dot ${features ? "live" : "dead"}`} />
              <span>{features ? "Receiving EEG updates" : "Waiting for signal"}</span>
            </div>
          </div>

          {/* Feature 6: band visualizer */}
          <BandVisualizer features={features} />

          <div className="mini-metrics">
            <div>
              <div className="mini-label">Focus streak</div>
              <div className={`mini-value${features?.is_attentive ? " attentive" : ""}`}>
                {formatStreak(features?.sustained_streak_sec ?? 0)}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Music Control ── */}
      <section className="music-section">
        <div className="music-section-header">
          <div>
            <h2>Music Control</h2>
            <p className="small-text music-helper">
              {spotifyTokenConnected
                ? "Spotify token connected. You can control playback."
                : "Connect Spotify first to save a local refresh token and enable playback control."}
            </p>
          </div>
        </div>

        <div className="music-controls-row">
          <div className="music-action-btns">
            {!spotifyTokenConnected && (
              <a className="action-btn spotify-connect-btn" href={connectSpotifyHref}>
                Connect Spotify
              </a>
            )}
            <button
              className="action-btn"
              type="button"
              onClick={() => void navigate("/setup")}
            >
              Update playlist
            </button>
          </div>
          <div className="mode-toggle-group">
            <button
              className={`mode-toggle-btn${playbackKind === "playlist" ? " active" : ""}`}
              type="button"
              onClick={() => void postPlaybackMode("playlist")}
            >
              Playlist mode
            </button>
            <button
              className={`mode-toggle-btn${playbackKind === "pool" ? " active" : ""}`}
              type="button"
              onClick={() => void postPlaybackMode("pool")}
            >
              Pool mode
            </button>
          </div>
        </div>

        {playbackKind === "playlist" ? (
          <div className="music-grid" style={{ marginBottom: 16 }}>
            <div className="card music-card">
              <div className="card-label">Playback</div>
              <div className="big-text">Mood playlists</div>
            </div>
            <div className="card music-card">
              <div className="card-label">Active context (by mood)</div>
              <div className="big-text">{currentPlaylist}</div>
            </div>
            <div className="card music-card">
              <div className="card-label">Setup</div>
              <div className="small-text">
                Playlist mode starts from the default mood → playlist mapping until
                you set your own contexts using Update playlist.
              </div>
            </div>
          </div>
        ) : (
          <div className="music-grid" style={{ marginBottom: 16 }}>
            <div className="card music-card">
              <div className="card-label">Playback</div>
              <div className="big-text">CSV track pool</div>
            </div>
            <div className="card music-card">
              <div className="card-label">Behavior</div>
              <div className="small-text">
                No setup step — neuro-rave picks nearest tracks from your pool
                as EEG features update.
              </div>
            </div>
            <div className="card music-card">
              <div className="card-label">Mood</div>
              <div className="big-text">{mood.replace(/_/g, " ").toUpperCase()}</div>
            </div>
          </div>
        )}

        {/* Feature 3: album art + Spotify player bar */}
        <div className="spotify-bar">
          <div className="spotify-bar-main">
          {/* Left: art + track info */}
          <div className="spotify-bar-left">
            {nowPlaying?.image_url && (
              <img className="spotify-album-art" src={nowPlaying.image_url} alt="Album art" />
            )}
            <div className="spotify-bar-track-info">
              <div className="spotify-bar-track">{nowPlaying?.name ?? "No active track"}</div>
              <div className="spotify-bar-artist">
                {[
                  nowPlaying?.artists?.length ? nowPlaying.artists.join(", ") : null,
                  nowPlaying?.album ?? null,
                ].filter(Boolean).join(" · ") || "—"}
              </div>
            </div>
          </div>

          {/* Center: prev · play/pause · next */}
          <div className="spotify-bar-center">
            <button
              className="spotify-skip-btn"
              type="button"
              disabled={playerActionBusy}
              onClick={() => void onSkipPrevious()}
              aria-label="Previous track"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect x="2" y="2" width="2" height="12" rx="1" />
                <polygon points="14,2 6,8 14,14" />
              </svg>
            </button>

            <button
              className="spotify-play-btn"
              type="button"
              disabled={playerActionBusy}
              onClick={() =>
                void (playbackPaused || !isSpotifyPlaying
                  ? onResumePlayback()
                  : onPausePlayback())
              }
              aria-label={playbackPaused || !isSpotifyPlaying ? "Resume" : "Pause"}
            >
              {playbackPaused || !isSpotifyPlaying ? (
                <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
                  <polygon points="4,1 17,9 4,17" />
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
                  <rect x="2" y="1" width="5" height="16" rx="1" />
                  <rect x="11" y="1" width="5" height="16" rx="1" />
                </svg>
              )}
            </button>

            <button
              className="spotify-skip-btn"
              type="button"
              disabled={playerActionBusy}
              onClick={() => void onSkipNext()}
              aria-label="Next track"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <polygon points="2,2 10,8 2,14" />
                <rect x="12" y="2" width="2" height="12" rx="1" />
              </svg>
            </button>
          </div>

          {/* Right: volume slider + position */}
          <div className="spotify-bar-right">
            <div className="volume-control">
              <svg className="volume-icon" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M2 5.5h3l4-3.5v12l-4-3.5H2V5.5z" />
                <path d="M11.5 4a4.5 4.5 0 0 1 0 8" opacity="0.5" />
                <path d="M11.5 6.5a2 2 0 0 1 0 3" />
              </svg>
              <input
                className="volume-slider"
                type="range"
                min={0}
                max={100}
                value={volume}
                onChange={(e) => setVolume(Number(e.target.value))}
                onMouseUp={onVolumeCommit}
                onTouchEnd={onVolumeCommit}
                aria-label="Volume"
                style={{
                  background: `linear-gradient(to right, white ${volume}%, rgba(255,255,255,0.15) ${volume}%)`,
                }}
              />
            </div>
          </div>
          </div>{/* end spotify-bar-main */}

          {/* Progress bar row */}
          <div className="progress-bar-row">
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{
                  width:
                    nowPlayingDurationMs && displayProgressMs !== null
                      ? `${Math.min((displayProgressMs / nowPlayingDurationMs) * 100, 100)}%`
                      : "0%",
                }}
              />
            </div>
          </div>
        </div>{/* end spotify-bar */}
      </section>

      {/* ── History charts ── */}
      <section className="history-grid">
        {history.length > 0 ? (
          <>
            <HistoryLineChart history={history} metricKey="energy" color="#f97316" title="Energy History" />
            <HistoryLineChart history={history} metricKey="focus" color="#34d399" title="Focus History" />
          </>
        ) : (
          <>
            <EmptyChartCard title="Energy History" />
            <EmptyChartCard title="Focus History" />
          </>
        )}
      </section>

      {/* Feature 5: mood timeline */}
      <MoodTimeline segments={moodTimeline} />

      {/* ── Activity log ── */}
      <section className="panel">
        <h2>Recent Activity Log</h2>
        <div className="log-list">
          {logs.map((log, index) => (
            <LogItem key={index} time={log.time} text={log.text} />
          ))}
        </div>
      </section>
    </div>
  );
}

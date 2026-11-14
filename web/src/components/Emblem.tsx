import { useId, type CSSProperties } from 'react';
import type { Visual } from '../lib/status';

/** The DarAI mark, drawn at the logo's true proportions (roof, pillars, sun). */
export function DaraiMark({ className = '' }: { className?: string }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={className} viewBox="151 143 210 160" aria-hidden>
      <defs>
        <linearGradient id={`r${id}`} x1="0" y1=".5" x2="1" y2=".5">
          <stop offset="0" stopColor="#0b4eb7" /><stop offset=".52" stopColor="#53bde9" /><stop offset="1" stopColor="#0d55bd" />
        </linearGradient>
        <linearGradient id={`l${id}`} x1=".5" y1="0" x2=".5" y2="1">
          <stop offset="0" stopColor="#75c8ed" /><stop offset="1" stopColor="#1767c8" />
        </linearGradient>
        <radialGradient id={`s${id}`}>
          <stop offset="0" stopColor="#fff8d5" /><stop offset=".48" stopColor="#ffd169" /><stop offset="1" stopColor="#efa82d" />
        </radialGradient>
      </defs>
      <path d="M156 218v47c0 21 13 31 29 31 17 0 29-13 29-31v-25l42-31 42 31v25c0 18 12 31 29 31 16 0 29-10 29-31v-47L273 158a29 29 0 0 0-34 0z" fill={`url(#l${id})`} opacity=".95" />
      <path d="m156 218 83-60a29 29 0 0 1 34 0l83 60v35l-83-60a29 29 0 0 0-34 0l-83 60z" fill={`url(#r${id})`} />
      <circle className="mark-sun" cx="256" cy="247" r="24" fill={`url(#s${id})`} />
    </svg>
  );
}

/**
 * Voice emblem. `level` (0..1) is the live audio level of whoever is talking;
 * rings and the sun's glow follow it, so motion always means real sound.
 */
export function VoiceEmblem({ visual, level = 0, size = 'lg' }: { visual: Visual; level?: number; size?: 'md' | 'lg' }) {
  const style = { '--level': Math.min(1, Math.max(0, level)).toFixed(3) } as CSSProperties;
  return (
    <div data-agent={visual} style={style}
      className={`voice-emblem relative grid place-items-center ${size === 'lg' ? 'size-[min(300px,78vw)]' : 'size-[min(200px,56vw)]'}`}>
      <span className="ve-aura" aria-hidden />
      <span className="ve-ring ve-ring-3" aria-hidden />
      <span className="ve-ring ve-ring-2" aria-hidden />
      <span className="ve-ring ve-ring-1" aria-hidden />
      <span className="ve-orbit" aria-hidden />
      <div className="ve-core">
        <span className="ve-sheen" aria-hidden />
        <DaraiMark className="ve-mark" />
      </div>
    </div>
  );
}

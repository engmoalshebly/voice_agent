import { useState, type ReactNode } from 'react';
import type { StatusView } from '../../lib/status';
import { VoiceEmblem } from '../Emblem';
import { Controls, type ControlsProps } from './Controls';
import { TranscriptPanel } from './TranscriptPanel';
import type { Line } from './types';

const DOT: Record<StatusView['visual'], string> = {
  idle: 'bg-muted', connecting: 'bg-warn', listening: 'bg-ok', thinking: 'bg-sun', speaking: 'bg-accent',
};

export interface CallLayoutProps {
  view: StatusView;
  level: number;
  lines: Line[];
  reconnecting?: boolean;
  controls: Omit<ControlsProps, 'transcriptOpen' | 'onToggleTranscript'>;
  footer?: ReactNode;
}

/** Pure presentation of a live call; all data arrives through props. */
export function CallLayout({ view, level, lines, reconnecting, controls, footer }: CallLayoutProps) {
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  return (
    <div className="mx-auto grid min-h-0 w-full max-w-6xl flex-1 gap-4 p-4 sm:gap-6 sm:p-6 lg:grid-cols-[minmax(0,1fr)_380px]">
      <section className="relative flex min-h-[520px] flex-col items-center rounded-[28px] border border-line bg-surface/70 px-5 pb-6 pt-5 shadow-sm backdrop-blur">
        <div className="flex w-full items-center justify-between">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium shadow-sm">
            <span className={`size-2 rounded-full ${DOT[view.visual]}`} aria-hidden /> مساعد داري
          </span>
          <span className="text-xs text-muted">اتصال آمن</span>
        </div>
        {reconnecting && (
          <p role="status" className="fade-in mt-3 rounded-full bg-warn/12 px-3 py-1 text-sm text-warn">الاتصال ضعيف، نعيد الاتصال…</p>
        )}

        <div className="flex flex-1 flex-col items-center justify-center py-6">
          <VoiceEmblem visual={view.visual} level={level} />
          <p className="mt-5 text-2xl font-bold" aria-live="polite">{view.label}</p>
          <p className="mt-1.5 h-5 text-sm text-muted">{view.hint}</p>
          {footer}
        </div>

        <Controls {...controls} transcriptOpen={transcriptOpen} onToggleTranscript={() => setTranscriptOpen((v) => !v)} />
      </section>

      <aside aria-label="نص المحادثة"
        className={`${transcriptOpen ? 'flex' : 'hidden'} fade-in max-h-[60vh] min-h-[320px] flex-col overflow-hidden rounded-[28px] border border-line bg-surface shadow-sm lg:flex lg:max-h-none`}>
        <TranscriptPanel lines={lines} />
      </aside>
    </div>
  );
}

import { useEffect, useRef } from 'react';
import { DaraiMark } from '../Emblem';
import { ChatIcon } from '../Icons';
import type { Line } from './types';

function Avatar({ mine }: { mine: boolean }) {
  return mine ? (
    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-2 text-xs font-bold text-muted ring-1 ring-line">أنت</span>
  ) : (
    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface ring-1 ring-line shadow-sm">
      <DaraiMark className="w-5" />
    </span>
  );
}

export function TranscriptPanel({ lines }: { lines: Line[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }); }, [lines]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="text-[15px] font-bold">نص المحادثة</h2>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent">
          <span className="size-1.5 animate-pulse rounded-full bg-accent" aria-hidden /> مباشر
        </span>
      </div>
      {lines.length === 0 ? (
        <div className="m-auto flex max-w-[16rem] flex-col items-center gap-3 px-6 py-10 text-center text-sm text-muted">
          <span className="grid size-11 place-items-center rounded-2xl bg-surface-2 text-muted"><ChatIcon /></span>
          سيظهر نص المحادثة هنا أثناء حديثكما.
        </div>
      ) : (
        <ol className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-5" aria-live="polite" aria-label="نص المحادثة">
          {lines.map((line) => (
            <li key={line.id} className={`fade-in flex items-end gap-2.5 ${line.mine ? 'flex-row' : 'flex-row-reverse'}`}>
              <Avatar mine={line.mine} />
              <div className={`flex max-w-[80%] flex-col gap-1 ${line.mine ? 'items-start' : 'items-end'}`}>
                <span className="px-1 text-[11px] font-medium text-muted">{line.mine ? 'أنت' : 'مساعد داري'}</span>
                <p className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[14.5px] leading-7 ${line.mine
                  ? 'brand-gradient rounded-ee-md text-white shadow-sm'
                  : 'rounded-es-md border border-line bg-surface-2/70'}`}>
                  {line.text}
                </p>
              </div>
            </li>
          ))}
          <div ref={end} />
        </ol>
      )}
    </div>
  );
}

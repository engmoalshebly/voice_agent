import { formatDuration } from '../lib/status';

export function Header({ live, elapsed }: { live: boolean; elapsed: number }) {
  return (
    <header className="border-b border-line/70 bg-surface/70 backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
      <div className="flex items-center gap-4">
        <img src="/brand/darai_logo_full.png" alt="داري Dar AI" className="h-9 w-auto dark:brightness-0 dark:invert sm:h-10" />
        <span className="hidden h-8 w-px bg-line sm:block" aria-hidden />
        <div className="hidden leading-tight sm:block">
          <p className="text-[15px] font-bold">المساعد الصوتي</p>
          <p className="text-xs text-muted">خدمات كاك بنك · نسخة تجريبية</p>
        </div>
      </div>
      {live ? (
        <div className="fade-in flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-sm font-medium tabular-nums shadow-sm">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-ok opacity-60" />
            <span className="relative inline-flex size-2 rounded-full bg-ok" />
          </span>
          <span dir="ltr">{formatDuration(elapsed)}</span>
        </div>
      ) : (
        <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent sm:hidden">المساعد الصوتي</span>
      )}
      </div>
    </header>
  );
}

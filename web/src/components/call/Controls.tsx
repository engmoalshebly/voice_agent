import type { ReactNode } from 'react';
import { ChatIcon, MicIcon, MicOffIcon, PhoneOffIcon } from '../Icons';

export interface ControlsProps {
  micEnabled: boolean;
  micPending?: boolean;
  onToggleMic: () => void;
  onEnd: () => void;
  transcriptOpen: boolean;
  onToggleTranscript: () => void;
  deviceMenu?: ReactNode;
}

const round = 'grid size-12 place-items-center rounded-full transition duration-200';

export function Controls(p: ControlsProps) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-line bg-surface p-1.5 shadow-[0_10px_30px_-12px_rgb(15_23_42/0.25)]">
      <div className="flex items-center rounded-full bg-surface-2">
        <button type="button" onClick={p.onToggleMic} disabled={p.micPending} aria-pressed={!p.micEnabled}
          aria-label={p.micEnabled ? 'كتم الميكروفون (M)' : 'إلغاء كتم الميكروفون (M)'} title={p.micEnabled ? 'كتم (M)' : 'إلغاء الكتم (M)'}
          className={`${round} ${p.micEnabled ? 'text-ink hover:bg-line/70' : 'bg-danger/12 text-danger'}`}>
          {p.micEnabled ? <MicIcon /> : <MicOffIcon />}
        </button>
        {p.deviceMenu}
      </div>
      <button type="button" onClick={p.onToggleTranscript} aria-pressed={p.transcriptOpen} aria-label="نص المحادثة"
        className={`${round} lg:hidden ${p.transcriptOpen ? 'bg-accent-soft text-accent' : 'bg-surface-2 text-ink hover:bg-line/70'}`}>
        <ChatIcon />
      </button>
      <button type="button" onClick={p.onEnd} aria-label="إنهاء المكالمة"
        className="flex h-12 items-center gap-2 rounded-full bg-[#dc2626] px-5 text-sm font-bold text-white transition hover:brightness-110 active:scale-[.97]">
        <PhoneOffIcon width={20} height={20} /> إنهاء
      </button>
    </div>
  );
}

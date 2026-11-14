import { useMediaDeviceSelect } from '@livekit/components-react';
import { useEffect, useRef, useState } from 'react';
import { ChevronIcon } from './Icons';

export function DeviceMenu() {
  const { devices, activeDeviceId, setActiveMediaDevice } = useMediaDeviceSelect({ kind: 'audioinput', requestPermissions: false });
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close); };
  }, [open]);

  if (devices.length < 2) return null;
  return (
    <div ref={box} className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-haspopup="listbox" aria-expanded={open}
        aria-label="اختيار الميكروفون" className="grid h-12 w-8 place-items-center rounded-e-full border-s border-line/60 text-muted hover:text-ink">
        <ChevronIcon />
      </button>
      {open && (
        <ul role="listbox" aria-label="الميكروفونات" className="fade-in absolute bottom-16 start-0 z-20 w-72 overflow-hidden rounded-2xl border border-line bg-surface p-1 shadow-xl">
          {devices.map((d) => (
            <li key={d.deviceId}>
              <button type="button" role="option" aria-selected={d.deviceId === activeDeviceId}
                onClick={() => { void setActiveMediaDevice(d.deviceId); setOpen(false); }}
                className={`w-full truncate rounded-xl px-3 py-2.5 text-start text-sm hover:bg-surface-2 ${d.deviceId === activeDeviceId ? 'font-semibold text-accent' : ''}`}>
                {d.label || 'ميكروفون'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}


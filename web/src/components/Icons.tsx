import type { SVGProps } from 'react';

const base = { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
  strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true } as const;

export const MicIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
);
export const MicOffIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M15 9.3V6a3 3 0 0 0-5.7-1.3M9 9v2a3 3 0 0 0 4.6 2.5M5 11a7 7 0 0 0 11.4 5.4M19 11a7 7 0 0 1-.6 2.8M12 18v3M3 3l18 18" /></svg>
);
export const PhoneOffIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M3.6 14.6c-.8-.8-.8-2 0-2.7 4.6-4.1 12.2-4.1 16.8 0 .8.7.8 1.9 0 2.7l-1.5 1.5c-.6.6-1.5.6-2.1.1l-1.6-1.3a1.5 1.5 0 0 1-.5-1.4l.2-1.2a10 10 0 0 0-5.8 0l.2 1.2c.1.5-.1 1-.5 1.4l-1.6 1.3c-.6.5-1.5.5-2.1-.1z" /></svg>
);
export const ChevronIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={16} height={16} {...p}><path d="m6 9 6 6 6-6" /></svg>
);
export const ShieldIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={18} height={18} {...p}><path d="M12 3 5 6v5c0 4.4 3 8.3 7 9.5 4-1.2 7-5.1 7-9.5V6z" /><path d="m9 12 2 2 4-4" /></svg>
);
export const ChatIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M21 12a8 8 0 0 1-11.8 7L4 20l1.1-4.6A8 8 0 1 1 21 12Z" /></svg>
);

/** Visual QA only (built with --mode preview, never shipped). */
import { CallLayout } from './components/call/CallLayout';
import { Header } from './components/Header';
import type { Visual } from './lib/status';
import { statusView } from './lib/status';

const LINES = [
  { id: '1', mine: false, text: 'أهلاً وسهلاً بك، معك المساعد الصوتي لخدمات كاك بنك. كيف أقدر أساعدك؟' },
  { id: '2', mine: true, text: 'السلام عليكم، إيش الخدمات اللي تقدموها؟' },
  { id: '3', mine: false, text: 'أكيد، أتحقق لك من التفاصيل.' },
  { id: '4', mine: false, text: 'نقدم الحسابات الجارية والتوفير، والبطاقات، والتحويلات، والخدمات الرقمية عبر التطبيق.' },
];

export function Preview() {
  const params = new URLSearchParams(location.search);
  const state = (params.get('state') ?? 'speaking') as 'speaking' | 'listening' | 'thinking';
  const view = statusView(state, state === 'thinking' ? 'searching' : 'idle', false);
  const visual: Visual = view.visual;
  return (
    <div className="brand-backdrop flex h-full flex-col">
      <Header live elapsed={95} />
      <main className="flex min-h-0 flex-1 flex-col">
        <CallLayout view={{ ...view, visual }} level={state === 'speaking' ? 0.7 : 0.25} lines={params.has('empty') ? [] : LINES}
          controls={{ micEnabled: true, onToggleMic: () => {}, onEnd: () => {} }} />
      </main>
    </div>
  );
}

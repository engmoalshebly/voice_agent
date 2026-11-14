import type { CallPhase } from '../hooks/useVoiceCall';
import type { FriendlyError } from '../lib/errors';
import { VoiceEmblem } from './Emblem';
import { MicIcon, ShieldIcon } from './Icons';

const TOPICS = ['الحسابات والخدمات', 'البطاقات والقنوات الرقمية', 'الفروع وأوقات العمل', 'الرسوم والسياسات العامة'];

export function PreCall({ phase, error, onStart }: { phase: CallPhase; error: FriendlyError | null; onStart: () => void }) {
  const connecting = phase === 'connecting';
  const ended = phase === 'ended';
  return (
    <section className="fade-in mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-5 py-8 text-center">
      <VoiceEmblem visual={connecting ? 'thinking' : 'idle'} size="md" />

      <p className="mt-2 inline-flex items-center gap-2 rounded-full bg-sun-soft px-3 py-1 text-xs font-medium text-sun">
        <span className="size-1.5 rounded-full bg-sun" aria-hidden />
        {ended ? 'انتهت المكالمة' : 'متاح الآن على مدار الساعة'}
      </p>
      <h1 className="mt-4 text-balance text-3xl font-bold leading-tight sm:text-[2.6rem]">
        {ended ? 'شكراً لتواصلك معنا' : <>تحدّث مع <span className="brand-text">مساعد داري</span> الصوتي</>}
      </h1>
      <p className="mt-3 max-w-md text-pretty leading-8 text-muted">
        داري بإحتياجهم، وذكي بالرد عليهم. اسأل بالعربية كما تسأل موظف خدمة العملاء، ويجيبك من معلومات البنك المعتمدة.
      </p>

      <button
        type="button"
        onClick={onStart}
        disabled={connecting}
        className="brand-gradient group mt-8 inline-flex h-14 items-center gap-3 rounded-full px-8 text-base font-bold text-white shadow-[0_16px_40px_-12px_rgb(var(--glow)/0.7)] transition duration-300 hover:-translate-y-0.5 hover:shadow-[0_20px_50px_-12px_rgb(var(--glow)/0.8)] active:translate-y-0 disabled:cursor-wait disabled:opacity-85"
      >
        {connecting
          ? <span className="size-5 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden />
          : <MicIcon />}
        <span aria-live="polite">{connecting ? 'جارٍ الاتصال الآمن…' : ended ? 'ابدأ مكالمة جديدة' : 'ابدأ المكالمة'}</span>
      </button>

      {error && (
        <div role="alert" className="fade-in mt-6 w-full max-w-md rounded-2xl border border-danger/30 bg-danger/5 p-4 text-start">
          <p className="font-bold text-danger">{error.title}</p>
          <p className="mt-1 text-sm text-muted">{error.detail}</p>
        </div>
      )}

      <ul className="mt-10 flex flex-wrap justify-center gap-2" aria-label="مواضيع يمكن السؤال عنها">
        {TOPICS.map((topic) => (
          <li key={topic} className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-xs text-muted shadow-sm">{topic}</li>
        ))}
      </ul>
      <p className="mt-8 flex items-center gap-1.5 text-xs text-muted">
        <ShieldIcon /> لا تشارك كلمات المرور أو رموز التحقق أو أرقام البطاقات.
      </p>
    </section>
  );
}

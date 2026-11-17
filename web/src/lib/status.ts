import type { AgentState } from '@livekit/components-react';

export type Lookup = 'idle' | 'searching' | 'answering' | 'failed';
export type Visual = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking';

export interface StatusView {
  visual: Visual;
  label: string;
  hint: string;
}

/** One place that decides what the caller sees for each combined state. */
export function statusView(agent: AgentState, lookup: Lookup, micMuted: boolean): StatusView {
  if (agent === 'disconnected' || agent === 'failed') {
    return { visual: 'idle', label: 'انتهت المكالمة', hint: '' };
  }
  if (agent === 'connecting' || agent === 'initializing' || agent === 'pre-connect-buffering') {
    return { visual: 'connecting', label: 'جارٍ تجهيز المساعد…', hint: 'يمكنك البدء بالكلام خلال لحظات' };
  }
  if (agent === 'speaking') {
    return { visual: 'speaking', label: 'المساعد يتحدث', hint: 'تكلّم في أي وقت لمقاطعته' };
  }
  if (lookup === 'searching') {
    return { visual: 'thinking', label: 'جارٍ مراجعة المعلومات المعتمدة', hint: 'لحظات وأعود إليك بالإجابة · يمكنك تعديل سؤالك' };
  }
  if (agent === 'thinking') {
    return { visual: 'thinking', label: 'يجهّز الرد', hint: 'ثوانٍ قليلة' };
  }
  if (micMuted) {
    return { visual: 'idle', label: 'الميكروفون مكتوم', hint: 'ألغِ الكتم لتتحدث' };
  }
  return { visual: 'listening', label: 'أنا أستمع', hint: 'تحدث بشكل طبيعي' };
}

export function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

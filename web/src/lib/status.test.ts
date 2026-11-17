import { describe, expect, it } from 'vitest';
import { formatDuration, statusView } from './status';

describe('statusView', () => {
  it('prefers the DarAI lookup over generic thinking', () => {
    expect(statusView('listening', 'searching', false).label).toContain('مراجعة');
    expect(statusView('thinking', 'idle', false).visual).toBe('thinking');
  });
  it('speaking wins over everything while connected', () => {
    expect(statusView('speaking', 'searching', true).visual).toBe('speaking');
  });
  it('reports a muted microphone instead of "listening"', () => {
    expect(statusView('listening', 'idle', true).label).toContain('مكتوم');
    expect(statusView('listening', 'idle', false).visual).toBe('listening');
  });
  it('treats setup states as connecting', () => {
    for (const s of ['connecting', 'initializing', 'pre-connect-buffering'] as const) {
      expect(statusView(s, 'idle', false).visual).toBe('connecting');
    }
  });
});

describe('formatDuration', () => {
  it('pads minutes and seconds', () => {
    expect(formatDuration(0)).toBe('00:00');
    expect(formatDuration(125)).toBe('02:05');
  });
});

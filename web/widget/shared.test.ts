import { describe, expect, it } from 'vitest';
import { DEFAULT_APPEARANCE, anchorStyle, friendlyError, resolveAppearance, withAlpha } from './shared';

describe('resolveAppearance', () => {
  it('uses the defaults when the dashboard set nothing', () => {
    expect(resolveAppearance({})).toEqual(DEFAULT_APPEARANCE);
    expect(resolveAppearance(null)).toEqual(DEFAULT_APPEARANCE);
  });

  it('takes the dashboard settings, then lets the page override them', () => {
    const look = resolveAppearance(
      { color: '#112233', voice: { title: 'مساعد كاك', show_transcript: false,
        launcher: { position: 'top_center', style: 'bar', label: 'اتصل بنا', offset_x: 40 } } },
      { position: 'bottom_left', label: '  تكلم  معنا ', offsetY: '500' },
    );
    expect(look.title).toBe('مساعد كاك');
    expect(look.show_transcript).toBe(false);
    expect(look.launcher).toEqual({ position: 'bottom_left', style: 'bar', label: 'تكلم معنا', color: '#112233',
      text_color: '#ffffff', offset_x: 40, offset_y: 120 });
  });

  it('ignores anything invalid from either side', () => {
    const look = resolveAppearance(
      { voice: { launcher: { position: 'middle', style: 'giant', color: 'red', label: 7 } } },
      { style: 'nope', color: 'javascript:alert(1)', offsetX: 'x' },
    );
    expect(look.launcher).toEqual(DEFAULT_APPEARANCE.launcher);
  });

  it('respects a switched-off assistant and falls back to the channel title', () => {
    expect(resolveAppearance({ voice: { enabled: false } }).enabled).toBe(false);
    expect(resolveAppearance({ title: 'الدردشة' }).title).toBe('الدردشة');
  });
});

describe('anchorStyle', () => {
  const base = DEFAULT_APPEARANCE.launcher;
  it('anchors to the chosen corner with its offsets', () => {
    expect(anchorStyle({ ...base, position: 'bottom_left', offset_x: 10, offset_y: 20 })).toEqual({ bottom: '20px', left: '10px' });
    expect(anchorStyle({ ...base, position: 'top_right' })).toEqual({ top: '24px', right: '24px' });
  });
  it('centres horizontally and spans the edge as a bar', () => {
    expect(anchorStyle({ ...base, position: 'top_center' })).toEqual({ top: '24px', left: '50%', transform: 'translateX(-50%)' });
    expect(anchorStyle({ ...base, position: 'top_center', style: 'bar' })).toEqual({ top: '0px', left: '0px', right: '0px' });
  });
});

describe('helpers', () => {
  it('makes a translucent brand colour, and a safe one from garbage', () => {
    expect(withAlpha('#ff0080', 0.5)).toBe('rgba(255, 0, 128, 0.5)');
    expect(withAlpha('bad', 1)).toBe('rgba(1, 77, 182, 1)');
  });
  it('explains failures without leaking them', () => {
    expect(friendlyError('token', 403)).toContain('غير متاح على هذا الموقع');
    expect(friendlyError('token', 429)).toContain('دقيقة');
    expect(friendlyError('mic')).toContain('الميكروفون');
    expect(friendlyError('call')).toContain('الإنترنت');
  });
});

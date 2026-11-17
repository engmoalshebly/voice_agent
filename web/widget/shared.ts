/**
 * What the embeddable voice assistant looks like and where it sits.
 *
 * The organisation sets this in its DarAI dashboard; the gateway serves it
 * from /ws/bootstrap. A site can override a few things with data-attributes
 * on the script tag. Everything has a sensible default, so a bare
 * <script src=".../widget.js" data-id="..."> works.
 */

export type Position = 'bottom_right' | 'bottom_left' | 'bottom_center' | 'top_right' | 'top_left' | 'top_center';
export type LauncherStyle = 'bubble' | 'pill' | 'bar';

export interface Launcher {
  position: Position;
  style: LauncherStyle;
  label: string;
  color: string;
  text_color: string;
  offset_x: number;
  offset_y: number;
}

export interface Appearance {
  enabled: boolean;
  title: string;
  show_transcript: boolean;
  launcher: Launcher;
}

export const POSITIONS: readonly Position[] = ['bottom_right', 'bottom_left', 'bottom_center', 'top_right', 'top_left', 'top_center'];
export const STYLES: readonly LauncherStyle[] = ['bubble', 'pill', 'bar'];

export const DEFAULT_APPEARANCE: Appearance = {
  enabled: true,
  title: 'المساعد الصوتي',
  show_transcript: true,
  launcher: {
    position: 'bottom_right',
    style: 'pill',
    label: 'تحدث معنا',
    color: '#014db6',
    text_color: '#ffffff',
    offset_x: 24,
    offset_y: 24,
  },
};

const COLOR = /^#[0-9a-fA-F]{6}$/;

function text(value: unknown, limit: number): string | undefined {
  if (typeof value !== 'string') return undefined;
  const clean = value.replace(/\s+/g, ' ').trim();
  return clean ? clean.slice(0, limit) : undefined;
}

function bounded(value: unknown, low: number, high: number): number | undefined {
  const n = typeof value === 'string' && value.trim() !== '' ? Number(value) : value;
  return typeof n === 'number' && Number.isFinite(n) ? Math.max(low, Math.min(high, Math.round(n))) : undefined;
}

/** Merge, in order: defaults, the dashboard's settings, the page's data-attributes. Invalid values are ignored. */
export function resolveAppearance(
  bootstrap: { voice?: Record<string, unknown>; color?: unknown; title?: unknown } | null | undefined,
  dataset: Record<string, string | undefined> = {},
): Appearance {
  const voice = (bootstrap?.voice ?? {}) as Record<string, unknown>;
  const fromServer = (voice.launcher ?? {}) as Record<string, unknown>;
  const launcher: Launcher = { ...DEFAULT_APPEARANCE.launcher };
  // The channel's brand colour is the natural default for its button.
  if (typeof bootstrap?.color === 'string' && COLOR.test(bootstrap.color)) launcher.color = bootstrap.color;

  for (const source of [fromServer, {
    position: dataset.position, style: dataset.style, label: dataset.label,
    color: dataset.color, text_color: dataset.textColor, offset_x: dataset.offsetX, offset_y: dataset.offsetY,
  } as Record<string, unknown>]) {
    if (POSITIONS.includes(source.position as Position)) launcher.position = source.position as Position;
    if (STYLES.includes(source.style as LauncherStyle)) launcher.style = source.style as LauncherStyle;
    const label = text(source.label, 30);
    if (label) launcher.label = label;
    if (typeof source.color === 'string' && COLOR.test(source.color)) launcher.color = source.color;
    if (typeof source.text_color === 'string' && COLOR.test(source.text_color)) launcher.text_color = source.text_color;
    const x = bounded(source.offset_x, 0, 120);
    if (x !== undefined) launcher.offset_x = x;
    const y = bounded(source.offset_y, 0, 120);
    if (y !== undefined) launcher.offset_y = y;
  }

  return {
    enabled: voice.enabled !== false,
    title: text(voice.title, 60) ?? text(bootstrap?.title, 60) ?? DEFAULT_APPEARANCE.title,
    show_transcript: voice.show_transcript !== false,
    launcher,
  };
}

/** Fixed-position CSS for an element anchored like the launcher. A bar spans the page edge. */
export function anchorStyle(launcher: Launcher): Record<string, string> {
  const [vertical, horizontal] = launcher.position.split('_') as ['top' | 'bottom', 'left' | 'right' | 'center'];
  if (launcher.style === 'bar') {
    return { [vertical]: '0px', left: '0px', right: '0px' };
  }
  const css: Record<string, string> = { [vertical]: `${launcher.offset_y}px` };
  if (horizontal === 'center') {
    css.left = '50%';
    css.transform = 'translateX(-50%)';
  } else {
    css[horizontal] = `${launcher.offset_x}px`;
  }
  return css;
}

/** "#rrggbb" with an alpha, for soft rings and shadows in the brand colour. */
export function withAlpha(color: string, alpha: number): string {
  const hex = COLOR.test(color) ? color : DEFAULT_APPEARANCE.launcher.color;
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** What a failed step means to a visitor. Never the raw error. */
export function friendlyError(step: 'token' | 'call' | 'mic', status?: number): string {
  if (step === 'mic') return 'لم نتمكن من استخدام الميكروفون. اسمح للمتصفح باستخدامه ثم حاول مجدداً.';
  if (status === 403) return 'المساعد الصوتي غير متاح على هذا الموقع حالياً.';
  if (status === 404 || status === 410) return 'المساعد الصوتي غير متاح حالياً.';
  if (status === 429) return 'بدأت عدة مكالمات خلال وقت قصير. حاول بعد دقيقة.';
  if (step === 'call') return 'تعذّر الاتصال بالمساعد. تحقق من الإنترنت ثم حاول مجدداً.';
  return 'تعذّر بدء المكالمة. حاول مجدداً بعد قليل.';
}

/** What widget-call.js exposes for widget.js. */
export interface CallApi {
  open(options: { gateway: string; channelId: string; appearance: Appearance; onClose: () => void }): void;
}

declare global {
  interface Window {
    __daraiVoice?: boolean;
    DaraiVoiceCall?: CallApi;
  }
}

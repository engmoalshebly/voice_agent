/**
 * DarAI voice assistant — the embed script.
 *
 *   <script src="https://voice.example.com/widget.js" data-id="webchat_xxxxxxxx" defer></script>
 *
 * Draws only the button (a few KB, no dependencies). The call itself, with
 * its audio library, loads the first time a visitor presses it.
 *
 * Optional attributes: data-gateway, data-position, data-style, data-label,
 * data-color, data-text-color, data-offset-x, data-offset-y.
 */
import { anchorStyle, resolveAppearance, withAlpha, type Appearance } from './shared';

const MIC = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-6a3.5 3.5 0 1 0-7 0v6A3.5 3.5 0 0 0 12 15Zm6.25-3.5a.75.75 0 0 0-1.5 0 4.75 4.75 0 0 1-9.5 0 .75.75 0 0 0-1.5 0 6.26 6.26 0 0 0 5.5 6.2V20H9a.75.75 0 0 0 0 1.5h6a.75.75 0 0 0 0-1.5h-2.25v-2.3a6.26 6.26 0 0 0 5.5-6.2Z"/></svg>';

function styles(a: Appearance): string {
  const l = a.launcher;
  return `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: "Segoe UI", Tahoma, system-ui, -apple-system, sans-serif; }
  .launcher { position: fixed; z-index: 2147483000; display: flex; align-items: center; gap: 10px;
    border: 0; cursor: pointer; color: ${l.text_color}; background: ${l.color};
    box-shadow: 0 10px 30px ${withAlpha(l.color, 0.35)}, 0 2px 8px rgba(0,0,0,.12);
    transition: transform .18s ease, box-shadow .18s ease, opacity .2s ease; direction: rtl; }
  .launcher:hover { transform: translateY(-2px); box-shadow: 0 14px 34px ${withAlpha(l.color, 0.45)}, 0 2px 8px rgba(0,0,0,.14); }
  .launcher:focus-visible { outline: 3px solid ${withAlpha(l.color, 0.45)}; outline-offset: 3px; }
  .launcher[hidden] { display: none; }
  .icon { position: relative; display: grid; place-items: center; flex: none; }
  .icon::after { content: ""; position: absolute; inset: -6px; border-radius: 999px;
    border: 2px solid ${withAlpha(l.text_color, 0.55)}; animation: ring 2.4s ease-out infinite; }
  @keyframes ring { 0% { transform: scale(.75); opacity: .9 } 100% { transform: scale(1.35); opacity: 0 } }
  @media (prefers-reduced-motion: reduce) { .icon::after { animation: none; opacity: 0 } .launcher { transition: none } }
  .bubble { width: 60px; height: 60px; border-radius: 50%; justify-content: center; }
  .pill { height: 52px; padding: 0 20px 0 16px; border-radius: 999px; font-size: 15px; font-weight: 700; }
  .bar { width: 100%; min-height: 48px; padding: 8px 16px; justify-content: center; font-size: 15px; font-weight: 700;
    box-shadow: 0 2px 12px rgba(0,0,0,.12); border-radius: 0; }
  .bar .cta { margin-inline-start: 12px; padding: 6px 14px; border-radius: 999px; font-size: 13px;
    background: ${l.text_color}; color: ${l.color}; }
  .bar:hover { transform: none; }
  @media (max-width: 480px) { .pill .text { display: none } .pill { width: 56px; padding: 0; justify-content: center } }
  `;
}

function render(appearance: Appearance, onPress: () => void): HTMLButtonElement {
  const host = document.createElement('div');
  host.setAttribute('data-darai-voice', '');
  const root = host.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = styles(appearance);
  const button = document.createElement('button');
  const l = appearance.launcher;
  button.type = 'button';
  button.className = `launcher ${l.style}`;
  button.setAttribute('aria-label', `${l.label} — ${appearance.title}`);
  Object.assign(button.style, anchorStyle(l));
  const icon = `<span class="icon">${MIC}</span>`;
  button.innerHTML = l.style === 'bubble'
    ? icon
    : l.style === 'bar'
      ? `${icon}<span class="text"></span><span class="cta">ابدأ المكالمة</span>`
      : `${icon}<span class="text"></span>`;
  const label = button.querySelector('.text');
  if (label) label.textContent = l.style === 'bar' ? `${l.label} · ${appearance.title}` : l.label;
  button.addEventListener('click', onPress);
  root.append(style, button);
  document.body.appendChild(host);
  return button;
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const tag = document.createElement('script');
    tag.src = src;
    tag.async = true;
    tag.onload = () => resolve();
    tag.onerror = () => reject(new Error('call script failed to load'));
    document.head.appendChild(tag);
  });
}

async function start(script: HTMLScriptElement): Promise<void> {
  const dataset = script.dataset as Record<string, string | undefined>;
  const scriptUrl = new URL(script.src, location.href);
  const channelId = (dataset.id || scriptUrl.searchParams.get('id') || '').trim();
  if (!channelId) {
    console.warn('[DarAI voice] data-id is missing on the script tag.');
    return;
  }
  let gateway = (dataset.gateway || '').replace(/\/+$/, '');
  if (!gateway) {
    const config: { gatewayUrl?: string } = await fetch(`${scriptUrl.origin}/api/config`, { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : {}));
    gateway = String(config?.gatewayUrl || '').replace(/\/+$/, '');
  }
  if (!gateway) {
    console.warn('[DarAI voice] no gateway configured.');
    return;
  }
  const response = await fetch(`${gateway}/ws/bootstrap?cId=${encodeURIComponent(channelId)}`, { credentials: 'include' });
  if (!response.ok) {
    console.warn(`[DarAI voice] this site cannot use assistant ${channelId} (${response.status}).`);
    return;
  }
  const appearance = resolveAppearance(await response.json(), dataset);
  if (!appearance.enabled) return;

  let loading: Promise<void> | null = null;
  const button = render(appearance, async () => {
    button.disabled = true;
    try {
      loading ??= window.DaraiVoiceCall ? Promise.resolve() : loadScript(`${scriptUrl.origin}/widget-call.js`);
      await loading;
      button.hidden = true;
      window.DaraiVoiceCall!.open({
        gateway, channelId, appearance,
        onClose: () => { button.hidden = false; button.disabled = false; button.focus(); },
      });
    } catch (error) {
      loading = null;
      button.disabled = false;
      console.warn('[DarAI voice] the call could not start.', error);
    }
  });
}

(() => {
  const script = document.currentScript as HTMLScriptElement | null;
  if (!script || window.__daraiVoice) return;
  window.__daraiVoice = true;
  const go = () => void start(script).catch(error => console.warn('[DarAI voice]', error));
  if (document.body) go();
  else document.addEventListener('DOMContentLoaded', go, { once: true });
})();

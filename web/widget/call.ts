/**
 * DarAI voice assistant — the call panel (widget-call.js).
 *
 * Loaded by widget.js the first time a visitor presses the button. A call is
 * the visitor's DarAI web conversation, spoken: the same widget token a chat
 * widget gets (channel and site checked by the gateway), traded for a room
 * token, then audio both ways over WebRTC.
 */
import { ConnectionState, Room, RoomEvent, Track, type Participant, type RemoteTrack, type TextStreamReader } from 'livekit-client';
import { anchorStyle, friendlyError, withAlpha, type Appearance } from './shared';

type Phase = 'connecting' | 'waiting' | 'listening' | 'thinking' | 'speaking' | 'ended' | 'error';

const PHASE_TEXT: Record<Phase, string> = {
  connecting: 'جارٍ الاتصال…',
  waiting: 'جارٍ تجهيز المساعد…',
  listening: 'أستمع إليك',
  thinking: 'لحظة من فضلك…',
  speaking: 'يتحدث الآن',
  ended: 'انتهت المكالمة',
  error: 'تعذّرت المكالمة',
};

class StepError extends Error {
  constructor(public readonly step: 'token' | 'call' | 'mic', public readonly status?: number) {
    super(step);
  }
}

async function postJson(url: string, init: RequestInit, step: 'token' | 'call'): Promise<any> {
  let response: Response;
  try {
    response = await fetch(url, { method: 'POST', cache: 'no-store', credentials: 'include', ...init });
  } catch {
    throw new StepError(step);
  }
  if (!response.ok) throw new StepError(step, response.status);
  return response.json();
}

const ICONS = {
  close: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M6.7 5.3 12 10.6l5.3-5.3 1.4 1.4-5.3 5.3 5.3 5.3-1.4 1.4-5.3-5.3-5.3 5.3-1.4-1.4 5.3-5.3-5.3-5.3z"/></svg>',
  mic: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-6a3.5 3.5 0 1 0-7 0v6A3.5 3.5 0 0 0 12 15Zm6.25-3.5a.75.75 0 0 0-1.5 0 4.75 4.75 0 0 1-9.5 0 .75.75 0 0 0-1.5 0 6.26 6.26 0 0 0 5.5 6.2V20H9a.75.75 0 0 0 0 1.5h6a.75.75 0 0 0 0-1.5h-2.25v-2.3a6.26 6.26 0 0 0 5.5-6.2Z"/></svg>',
  micOff: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M3.3 2.3 2.2 3.4l6.3 6.3v1.8a3.5 3.5 0 0 0 5.3 3l1.1 1.1a4.75 4.75 0 0 1-7.4-4 .75.75 0 0 0-1.5 0 6.26 6.26 0 0 0 5.5 6.2V20H9a.75.75 0 0 0 0 1.5h6a.75.75 0 0 0 0-1.5h-2.25v-2.3c1-.12 1.93-.47 2.74-1l4.1 4.1 1.1-1.1zM15.5 11.5v-6a3.5 3.5 0 0 0-6.9-.8l6.9 6.9v-.1Zm2.1 1.6 1.2 1.2c.3-.86.45-1.79.45-2.8a.75.75 0 0 0-1.5 0c0 .55-.06 1.08-.15 1.6Z"/></svg>',
  end: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85a1 1 0 0 1-1.41-.02L.29 13.07a1 1 0 0 1 0-1.41C3.34 8.77 7.46 7 12 7s8.66 1.77 11.71 4.66a1 1 0 0 1 0 1.41l-2.48 2.48a1 1 0 0 1-1.41.02 11.27 11.27 0 0 0-2.67-1.85 1 1 0 0 1-.56-.9v-3.1A15 15 0 0 0 12 9Z"/></svg>',
};

function styles(a: Appearance): string {
  const c = a.launcher.color;
  return `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: "Segoe UI", Tahoma, system-ui, -apple-system, sans-serif; }
  .panel { position: fixed; z-index: 2147483001; width: 360px; max-width: calc(100vw - 24px);
    background: #fff; color: #0f172a; border-radius: 22px; direction: rtl; overflow: hidden;
    box-shadow: 0 24px 60px rgba(15,23,42,.22), 0 2px 10px rgba(15,23,42,.08);
    animation: in .22s ease-out; display: flex; flex-direction: column; }
  @keyframes in { from { opacity: 0; transform: translateY(8px) scale(.98) } to { opacity: 1; transform: none } }
  @media (prefers-color-scheme: dark) { .panel { background: #0f172a; color: #e2e8f0 } .line.caller { background: #1e293b } .muted { color: #94a3b8 } }
  @media (max-width: 480px) { .panel { left: 8px !important; right: 8px !important; width: auto; bottom: 8px !important; top: auto !important; transform: none !important } }
  header { display: flex; align-items: center; gap: 10px; padding: 14px 16px; background: ${c}; color: #fff; }
  header .who { flex: 1; min-width: 0; }
  header .title { font-size: 15px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  header .status { font-size: 12px; opacity: .9; display: flex; align-items: center; gap: 6px; margin-top: 2px; }
  header .dot { width: 7px; height: 7px; border-radius: 50%; background: #4ade80; }
  header .dot.off { background: #fbbf24; }
  button { font: inherit; cursor: pointer; border: 0; }
  .close { background: rgba(255,255,255,.18); color: #fff; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; }
  .close:hover { background: rgba(255,255,255,.28); }
  .stage { padding: 26px 16px 18px; display: grid; justify-items: center; gap: 14px; }
  .orb { width: 112px; height: 112px; border-radius: 50%; position: relative;
    background: radial-gradient(circle at 35% 30%, ${withAlpha(c, 0.55)}, ${c} 70%);
    box-shadow: 0 12px 30px ${withAlpha(c, 0.35)}; transition: transform .3s ease; }
  .orb::before, .orb::after { content: ""; position: absolute; inset: -10px; border-radius: 50%; border: 2px solid ${withAlpha(c, 0.35)}; opacity: 0; }
  .orb.listening::before { animation: pulse 2s ease-out infinite; }
  .orb.speaking { animation: talk .9s ease-in-out infinite alternate; }
  .orb.speaking::before, .orb.speaking::after { animation: pulse 1.2s ease-out infinite; }
  .orb.speaking::after { animation-delay: .6s; }
  .orb.thinking { animation: think 1.4s ease-in-out infinite; }
  .orb.connecting, .orb.waiting { opacity: .55; animation: think 1.8s ease-in-out infinite; }
  .orb.ended, .orb.error { opacity: .35; filter: grayscale(.6); }
  @keyframes pulse { 0% { transform: scale(.9); opacity: .9 } 100% { transform: scale(1.35); opacity: 0 } }
  @keyframes talk { from { transform: scale(1) } to { transform: scale(1.07) } }
  @keyframes think { 0%,100% { transform: scale(.96) } 50% { transform: scale(1.02) } }
  @media (prefers-reduced-motion: reduce) { .orb, .orb::before, .orb::after { animation: none !important } }
  .phase { font-size: 15px; font-weight: 700; }
  .muted { font-size: 12px; color: #64748b; text-align: center; line-height: 1.6; }
  .error { color: #b91c1c; font-size: 13px; text-align: center; line-height: 1.6; padding: 0 8px; }
  .transcript { max-height: 180px; overflow-y: auto; padding: 0 14px 6px; display: flex; flex-direction: column; gap: 6px; }
  .line { font-size: 13px; line-height: 1.6; padding: 7px 11px; border-radius: 14px; max-width: 88%; }
  .line.agent { align-self: flex-start; background: ${withAlpha(c, 0.1)}; }
  .line.caller { align-self: flex-end; background: #f1f5f9; }
  footer { display: flex; justify-content: center; align-items: center; gap: 18px; padding: 14px 16px 18px; }
  .round { width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; transition: transform .15s ease, background .15s ease; }
  .round:hover { transform: scale(1.05); }
  .round:focus-visible, .close:focus-visible, .play:focus-visible { outline: 3px solid ${withAlpha(c, 0.45)}; outline-offset: 2px; }
  .mute { background: #f1f5f9; color: #334155; }
  .mute[aria-pressed="true"] { background: #fee2e2; color: #b91c1c; }
  .hangup { background: #dc2626; color: #fff; width: 60px; height: 60px; }
  .again { background: ${c}; color: #fff; border-radius: 999px; padding: 10px 20px; font-weight: 700; font-size: 14px; }
  .play { background: ${c}; color: #fff; border-radius: 999px; padding: 8px 16px; font-size: 13px; font-weight: 700; }
  .powered { font-size: 10px; color: #94a3b8; text-align: center; padding-bottom: 10px; }
  [hidden] { display: none !important; }
  `;
}

function panelPosition(appearance: Appearance): Record<string, string> {
  const l = appearance.launcher;
  // Open where the button was; a bar opens from its edge, at the reading start.
  const anchored = anchorStyle(l.style === 'bar' ? { ...l, style: 'pill', position: l.position.startsWith('top') ? 'top_right' : 'bottom_right' } : l);
  const vertical = l.position.startsWith('top') ? 'top' : 'bottom';
  const offset = l.style === 'bar' ? 60 : l.offset_y;
  return { ...anchored, [vertical]: `${offset}px` };
}

interface Elements {
  panel: HTMLElement; title: HTMLElement; dot: HTMLElement; state: HTMLElement; orb: HTMLElement; phase: HTMLElement;
  hint: HTMLElement; play: HTMLElement; error: HTMLElement; again: HTMLElement; transcript: HTMLElement;
  handoff: HTMLButtonElement; chat: HTMLFormElement; chatInput: HTMLInputElement; mute: HTMLElement; hangup: HTMLElement; close: HTMLElement; footer: HTMLElement;
}

class Call {
  private room: Room | null = null;
  private callToken = '';
  private chatSocket: WebSocket | null = null;
  private chatMode = false;
  private readonly root: ShadowRoot;
  private readonly host: HTMLElement;
  private readonly el: Elements;
  private phase: Phase = 'connecting';
  private closed = false;
  private agentIdentity = '';
  private readonly audio: HTMLMediaElement[] = [];

  constructor(private readonly options: { gateway: string; channelId: string; appearance: Appearance; onClose: () => void }) {
    const a = options.appearance;
    this.host = document.createElement('div');
    this.host.setAttribute('data-darai-voice-call', '');
    this.root = this.host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = styles(a);
    const panel = document.createElement('section');
    panel.className = 'panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', a.title);
    Object.assign(panel.style, panelPosition(a));
    panel.innerHTML = `
      <header>
        <div class="who"><div class="title"></div><div class="status"><span class="dot off"></span><span class="state"></span></div></div>
        <button class="close" type="button" aria-label="إنهاء المكالمة وإغلاق">${ICONS.close}</button>
      </header>
      <div class="stage">
        <div class="orb connecting" aria-hidden="true"></div>
        <div class="phase" aria-live="polite"></div>
        <div class="muted hint">تحدّث بشكل طبيعي، ويمكنك مقاطعة المساعد في أي وقت.</div>
        <button class="play" type="button" hidden>اضغط لتشغيل الصوت</button>
        <div class="error" role="alert" hidden></div>
        <button class="again" type="button" hidden>اتصل مرة أخرى</button>
      </div>
      <div class="transcript" aria-live="polite"${a.show_transcript ? '' : ' hidden'}></div>
      <footer>
        <button class="round mute" type="button" aria-pressed="false" aria-label="كتم الميكروفون">${ICONS.mic}</button>
        <button class="round hangup" type="button" aria-label="إنهاء المكالمة">${ICONS.end}</button>
      </footer>
      <button class="handoff again" type="button" hidden>متابعة مع موظف بالدردشة</button>
      <form class="chat" hidden><label class="muted" for="voice-chat-text">رسالتك للموظف</label><div style="display:flex;gap:8px"><input id="voice-chat-text" maxlength="4000" autocomplete="off" required style="min-width:0;flex:1;padding:8px;border:1px solid #cbd5e1;border-radius:8px"/><button class="again" type="submit">إرسال</button></div></form>
      <div class="powered">مدعوم بواسطة DarAI</div>`;
    this.root.append(style, panel);
    const q = (selector: string) => panel.querySelector(selector) as HTMLElement;
    this.el = {
      panel, title: q('.title'), dot: q('.dot'), state: q('.state'), orb: q('.orb'), phase: q('.phase'),
      hint: q('.hint'), play: q('.play'), error: q('.error'), again: q('.again'), transcript: q('.transcript'),
      handoff: q('.handoff') as HTMLButtonElement, chat: q('.chat') as HTMLFormElement, chatInput: q('#voice-chat-text') as HTMLInputElement,
      mute: q('.mute'), hangup: q('.hangup'), close: q('.close'), footer: q('footer'),
    };
    this.el.title.textContent = a.title;
    this.el.handoff.style.margin = '0 16px 12px';
    this.el.chat.style.padding = '12px 16px';
    this.el.handoff.addEventListener('click', () => void this.handoff());
    this.el.chat.addEventListener('submit', event => {
      event.preventDefault();
      const text = this.el.chatInput.value.trim();
      if (!text || this.chatSocket?.readyState !== WebSocket.OPEN) return;
      this.chatSocket.send(JSON.stringify({ event: 'message.send', id: crypto.randomUUID(), payload: { type: 'text', text } }));
      this.addLine('caller', text);
      this.el.chatInput.value = '';
    });
    this.el.close.addEventListener('click', () => void this.close());
    this.el.hangup.addEventListener('click', () => void this.end());
    this.el.mute.addEventListener('click', () => void this.toggleMute());
    this.el.play.addEventListener('click', () => void this.room?.startAudio().then(() => { this.el.play.hidden = true; }));
    this.el.again.addEventListener('click', () => void this.restart());
    panel.addEventListener('keydown', event => { if ((event as KeyboardEvent).key === 'Escape') void this.close(); });
    document.body.appendChild(this.host);
    this.setPhase('connecting');
    this.el.hangup.focus();
  }

  private setPhase(phase: Phase): void {
    this.phase = phase;
    this.el.orb.className = `orb ${phase}`;
    this.el.phase.textContent = PHASE_TEXT[phase];
    this.el.state.textContent = phase === 'ended' || phase === 'error' ? 'غير متصل' : phase === 'connecting' ? 'جارٍ الاتصال' : 'متصل';
    this.el.dot.classList.toggle('off', !['listening', 'thinking', 'speaking'].includes(phase));
    const live = !['ended', 'error'].includes(phase);
    this.el.footer.hidden = !live;
    this.el.hint.hidden = !live;
    this.el.again.hidden = live;
  }

  private fail(message: string): void {
    this.el.error.textContent = message;
    this.el.error.hidden = false;
    this.setPhase('error');
  }

  private addLine(who: 'agent' | 'caller', text: string): void {
    if (!text.trim() || this.el.transcript.hidden) return;
    const line = document.createElement('div');
    line.className = `line ${who}`;
    line.textContent = text.trim();
    this.el.transcript.appendChild(line);
    while (this.el.transcript.childElementCount > 40) this.el.transcript.firstElementChild?.remove();
    this.el.transcript.scrollTop = this.el.transcript.scrollHeight;
  }

  async start(): Promise<void> {
    const { gateway, channelId } = this.options;
    try {
      const storageKey = `darai_voice_visitor:${channelId}`;
      let visitorKey: string | null = null;
      try { visitorKey = localStorage.getItem(storageKey); } catch { /* private mode */ }
      const widget = await postJson(`${gateway}/ws/token`, {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cId: channelId, visitor_key: visitorKey }),
      }, 'token');
      if (!widget?.token) throw new StepError('token');
      if (widget.visitorKey) { try { localStorage.setItem(storageKey, widget.visitorKey); } catch { /* private mode */ } }
      const call = await postJson(`${gateway}/ws/voice/token`, { headers: { Authorization: `Bearer ${widget.token}` } }, 'token');
      if (this.closed) return;
      this.callToken = call.callToken || '';
      this.el.handoff.hidden = !this.callToken;

      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      this.room = room;
      room
        .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
          if (track.kind !== Track.Kind.Audio) return;
          const element = track.attach();
          element.style.display = 'none';
          this.root.appendChild(element);
          this.audio.push(element);
        })
        .on(RoomEvent.ParticipantConnected, (participant: Participant) => this.watchAgent(participant))
        .on(RoomEvent.ParticipantAttributesChanged, (_changed: Record<string, string>, participant: Participant) => this.watchAgent(participant))
        .on(RoomEvent.AudioPlaybackStatusChanged, () => { this.el.play.hidden = room.canPlaybackAudio; })
        .on(RoomEvent.Disconnected, () => { if (!this.closed && !this.chatMode) this.setPhase('ended'); });
      room.registerTextStreamHandler('lk.transcription', async (reader: TextStreamReader, info: { identity: string }) => {
        const text = await reader.readAll();
        if (reader.info.attributes?.['lk.transcription_final'] === 'false') return;
        this.addLine(info.identity === room.localParticipant.identity ? 'caller' : 'agent', text);
      });

      try {
        await room.connect(call.serverUrl, call.participantToken);
      } catch {
        throw new StepError('call');
      }
      try {
        await room.localParticipant.setMicrophoneEnabled(true);
      } catch {
        throw new StepError('mic');
      }
      if (!room.canPlaybackAudio) this.el.play.hidden = false;
      room.remoteParticipants.forEach(participant => this.watchAgent(participant));
      if (!this.agentIdentity) this.setPhase('waiting');
    } catch (error) {
      await this.room?.disconnect();
      this.room = null;
      if (this.closed) return;
      const step = error instanceof StepError ? error : new StepError('call');
      this.fail(friendlyError(step.step, step.status));
    }
  }

  private watchAgent(participant: Participant): void {
    const state = participant.attributes?.['lk.agent.state'];
    if (!state && participant.identity !== this.agentIdentity) return;
    this.agentIdentity = participant.identity;
    if (this.chatMode) return;
    if (this.phase === 'ended' || this.phase === 'error') return;
    if (state === 'speaking') this.setPhase('speaking');
    else if (state === 'thinking') this.setPhase('thinking');
    else this.setPhase('listening');
  }

  private async handoff(): Promise<void> {
    if (!this.callToken || this.chatMode) return;
    this.el.handoff.disabled = true;
    try {
      const info = await postJson(`${this.options.gateway}/ws/voice/handoff`, {
        headers: { Authorization: `Bearer ${this.callToken}` },
      }, 'call');
      this.chatMode = true;
      await this.disconnect();
      this.setPhase('ended');
      this.el.phase.textContent = 'متابعة بالدردشة';
      this.el.state.textContent = 'في انتظار رد الموظف';
      this.el.again.hidden = true;
      this.el.handoff.hidden = true;
      this.el.transcript.hidden = false;
      this.el.chat.hidden = false;
      const url = new URL(`${this.options.gateway}/ws/ws`);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      url.search = new URLSearchParams({ platform: 'voice', account_id: info.accountId, sender_id: info.senderId, ticket: info.wsTicket }).toString();
      this.chatSocket = new WebSocket(url);
      this.chatSocket.onopen = () => { this.el.chatInput.focus(); };
      this.chatSocket.onmessage = event => {
        try {
          const message = JSON.parse(event.data);
          if (message.event === 'message.new' && message.payload?.text) this.addLine('agent', message.payload.text);
          if (message.event === 'system.error') {
            this.el.error.textContent = 'تعذّر إرسال الرسالة. يرجى المحاولة مجددًا.';
            this.el.error.hidden = false;
          }
        } catch { /* ignore unsupported protocol messages */ }
      };
      this.chatSocket.onclose = () => {
        if (!this.closed) { this.el.state.textContent = 'انقطع اتصال الدردشة؛ أعد فتح المساعد للمتابعة'; this.el.chat.hidden = true; }
      };
    } catch {
      this.el.error.textContent = 'تعذّر التحويل الآن. تحدث مع المساعد أولًا ثم حاول مجددًا.';
      this.el.error.hidden = false;
      this.el.handoff.disabled = false;
    }
  }

  private async toggleMute(): Promise<void> {
    const room = this.room;
    if (!room) return;
    const muted = this.el.mute.getAttribute('aria-pressed') === 'true';
    await room.localParticipant.setMicrophoneEnabled(muted);
    this.el.mute.setAttribute('aria-pressed', String(!muted));
    this.el.mute.setAttribute('aria-label', muted ? 'كتم الميكروفون' : 'إلغاء كتم الميكروفون');
    this.el.mute.innerHTML = muted ? ICONS.mic : ICONS.micOff;
  }

  private async disconnect(): Promise<void> {
    const room = this.room;
    this.room = null;
    for (const element of this.audio.splice(0)) element.remove();
    if (room && room.state !== ConnectionState.Disconnected) await room.disconnect();
  }

  async end(): Promise<void> {
    await this.disconnect();
    this.setPhase('ended');
  }

  private async restart(): Promise<void> {
    this.el.error.hidden = true;
    this.el.transcript.replaceChildren();
    this.agentIdentity = '';
    this.setPhase('connecting');
    await this.start();
  }

  async close(): Promise<void> {
    this.closed = true;
    this.chatSocket?.close();
    await this.disconnect();
    this.host.remove();
    this.options.onClose();
  }
}

let active: Call | null = null;

window.DaraiVoiceCall = {
  open(options) {
    if (active) return;
    const call = new Call({ ...options, onClose: () => { active = null; options.onClose(); } });
    active = call;
    void call.start();
  },
};

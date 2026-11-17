export interface Connection {
  serverUrl: string;
  participantToken: string;
  roomName: string;
}

export class TokenError extends Error {
  constructor(public readonly code: string, public readonly status: number) {
    super(code);
    this.name = 'TokenError';
  }
}

/** Where a call is set up. Served by this page's own host at /api/config. */
interface VoiceConfig {
  /** DarAI realtime gateway, e.g. https://app.example.com. Empty = legacy demo. */
  gatewayUrl: string;
  /** The webchat channel (widget id) calls belong to. `?c=` in the URL overrides it. */
  channelId: string;
}

let config: Promise<VoiceConfig> | null = null;

function loadConfig(signal?: AbortSignal): Promise<VoiceConfig> {
  config ??= fetch('/api/config', { headers: { Accept: 'application/json' }, cache: 'no-store', signal })
    .then((response) => (response.ok ? response.json() : {}))
    .then((raw: Partial<VoiceConfig>) => ({
      gatewayUrl: String(raw.gatewayUrl ?? '').replace(/\/+$/, ''),
      channelId: String(raw.channelId ?? ''),
    }))
    .catch((error) => {
      config = null; // let the next attempt try again
      throw error;
    });
  return config;
}

async function post(url: string, init: RequestInit, codes: Record<number, string>): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, { method: 'POST', cache: 'no-store', ...init });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new TokenError('network', 0);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: { code?: string } } | null;
    throw new TokenError(codes[response.status] ?? body?.error?.code ?? 'http_error', response.status);
  }
  return response.json();
}

/**
 * A call is the visitor's DarAI webchat conversation, spoken: first the same
 * widget token a chat widget gets (the gateway checks the channel and this
 * page's origin), then a room token for that visitor.
 */
async function viaGateway(gatewayUrl: string, channelId: string, signal?: AbortSignal): Promise<Connection> {
  const widget = (await post(
    `${gatewayUrl}/ws/token`,
    {
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ cId: channelId, platform: 'webchat' }),
      signal,
    },
    { 403: 'origin_forbidden', 404: 'channel_unavailable', 410: 'channel_unavailable' },
  )) as { token?: string };
  if (!widget.token) throw new TokenError('http_error', 200);
  return (await post(
    `${gatewayUrl}/ws/voice/token`,
    { headers: { Accept: 'application/json', Authorization: `Bearer ${widget.token}` }, signal },
    { 404: 'not_configured', 410: 'channel_unavailable', 429: 'rate_limited' },
  )) as Connection;
}

export async function requestConnection(signal?: AbortSignal): Promise<Connection> {
  let settings: VoiceConfig;
  try {
    settings = await loadConfig(signal);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new TokenError('network', 0);
  }
  const channelId = new URLSearchParams(window.location.search).get('c')?.trim() || settings.channelId;
  if (settings.gatewayUrl && channelId) return viaGateway(settings.gatewayUrl, channelId, signal);
  // Legacy demo: this host issues an anonymous room itself.
  return (await post('/api/token', { headers: { Accept: 'application/json' }, signal }, {})) as Connection;
}

/** Test seam: forget the cached config. */
export function resetConfigForTests(): void {
  config = null;
}

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TokenError, requestConnection, resetConfigForTests } from './api';

type Route = (init?: RequestInit) => { status?: number; body?: unknown };

function serve(routes: Record<string, Route>) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const route = routes[url];
    if (!route) throw new TypeError('network down');
    const { status = 200, body = {} } = route(init);
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  }));
  return calls;
}

const GATEWAY = 'https://app.example.com';
const ROOM = { serverUrl: 'wss://rtc.example.com', participantToken: 'lk', roomName: 'voice-1' };

beforeEach(() => {
  resetConfigForTests();
  window.history.replaceState({}, '', '/');
});
afterEach(() => vi.unstubAllGlobals());

describe('requestConnection', () => {
  it('trades the widget token for a room token at the gateway', async () => {
    const calls = serve({
      '/api/config': () => ({ body: { gatewayUrl: `${GATEWAY}/`, channelId: 'webchat_1' } }),
      [`${GATEWAY}/ws/token`]: () => ({ body: { token: 'visitor-jwt', senderId: 'v_1' } }),
      [`${GATEWAY}/ws/voice/token`]: () => ({ body: ROOM }),
    });

    expect(await requestConnection()).toEqual(ROOM);
    expect(JSON.parse(String(calls[1]?.init?.body))).toEqual({ cId: 'webchat_1', platform: 'webchat' });
    expect((calls[2]?.init?.headers as Record<string, string>).Authorization).toBe('Bearer visitor-jwt');
  });

  it('lets the page URL choose the channel', async () => {
    window.history.replaceState({}, '', '/?c=webchat_other');
    const calls = serve({
      '/api/config': () => ({ body: { gatewayUrl: GATEWAY, channelId: 'webchat_1' } }),
      [`${GATEWAY}/ws/token`]: () => ({ body: { token: 't' } }),
      [`${GATEWAY}/ws/voice/token`]: () => ({ body: ROOM }),
    });

    await requestConnection();
    expect(JSON.parse(String(calls[1]?.init?.body)).cId).toBe('webchat_other');
  });

  it.each([
    [{ status: 403 }, { body: ROOM }, 'origin_forbidden'],
    [{ status: 404 }, { body: ROOM }, 'channel_unavailable'],
    [{ body: { token: 't' } }, { status: 429 }, 'rate_limited'],
    [{ body: { token: 't' } }, { status: 404 }, 'not_configured'],
    [{ body: {} }, { body: ROOM }, 'http_error'],
  ])('names what went wrong (%#)', async (widget, room, code) => {
    serve({
      '/api/config': () => ({ body: { gatewayUrl: GATEWAY, channelId: 'webchat_1' } }),
      [`${GATEWAY}/ws/token`]: () => widget,
      [`${GATEWAY}/ws/voice/token`]: () => room,
    });

    await expect(requestConnection()).rejects.toMatchObject({ name: 'TokenError', code });
  });

  it('falls back to the legacy demo token when no gateway is configured', async () => {
    const calls = serve({ '/api/config': () => ({ body: {} }), '/api/token': () => ({ body: ROOM }) });

    expect(await requestConnection()).toEqual(ROOM);
    expect(calls.map((call) => call.url)).toEqual(['/api/config', '/api/token']);
  });

  it('reports an unreachable host as a network error and retries the config next time', async () => {
    serve({});
    await expect(requestConnection()).rejects.toEqual(new TokenError('network', 0));

    serve({ '/api/config': () => ({ body: {} }), '/api/token': () => ({ body: ROOM }) });
    expect(await requestConnection()).toEqual(ROOM);
  });
});

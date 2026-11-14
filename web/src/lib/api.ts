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

export async function requestConnection(signal?: AbortSignal): Promise<Connection> {
  let response: Response;
  try {
    response = await fetch('/api/token', {
      method: 'POST',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new TokenError('network', 0);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: { code?: string } } | null;
    throw new TokenError(body?.error?.code ?? 'http_error', response.status);
  }
  return (await response.json()) as Connection;
}

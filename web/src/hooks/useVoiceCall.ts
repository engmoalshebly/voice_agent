import { Room, RoomEvent } from 'livekit-client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { requestConnection } from '../lib/api';
import { describeError, type FriendlyError } from '../lib/errors';

export type CallPhase = 'idle' | 'connecting' | 'live' | 'ended' | 'error';

/** Owns the Room lifecycle: one room per call, never leaked, never doubled. */
export function useVoiceCall() {
  const [room, setRoom] = useState<Room | null>(null);
  const [phase, setPhase] = useState<CallPhase>('idle');
  const [error, setError] = useState<FriendlyError | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const active = useRef<Room | null>(null);
  const abort = useRef<AbortController | null>(null);

  const teardown = useCallback(async (next: CallPhase) => {
    abort.current?.abort();
    abort.current = null;
    const current = active.current;
    active.current = null;
    setRoom(null);
    setStartedAt(null);
    setPhase(next);
    if (current) await current.disconnect().catch(() => undefined);
  }, []);

  const start = useCallback(async () => {
    if (active.current || abort.current) return;
    setError(null);
    setPhase('connecting');
    const controller = new AbortController();
    abort.current = controller;
    const next = new Room({ adaptiveStream: true, dynacast: true, audioCaptureDefaults: {
      echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    } });
    try {
      const { serverUrl, participantToken } = await requestConnection(controller.signal);
      next.on(RoomEvent.Disconnected, () => {
        if (active.current === next) void teardown('ended');
      });
      // Start the mic first so the user's opening words are buffered for the agent.
      await Promise.all([
        next.localParticipant.setMicrophoneEnabled(true, undefined, { preConnectBuffer: true }),
        next.connect(serverUrl, participantToken),
      ]);
      if (controller.signal.aborted) {
        await next.disconnect();
        return;
      }
      abort.current = null;
      active.current = next;
      setRoom(next);
      setStartedAt(Date.now());
      setPhase('live');
    } catch (err) {
      await next.disconnect().catch(() => undefined);
      if (controller.signal.aborted) return;
      abort.current = null;
      setError(describeError(err));
      setPhase('error');
    }
  }, [teardown]);

  const end = useCallback(() => teardown('ended'), [teardown]);
  const fail = useCallback(async () => {
    await teardown('error');
    setError({ title: 'انقطعت المكالمة', detail: 'حدث خطأ في الواجهة. ابدأ مكالمة جديدة.', retryable: true });
  }, [teardown]);

  useEffect(() => () => {
    abort.current?.abort();
    void active.current?.disconnect();
  }, []);

  useEffect(() => {
    if (!room) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [room]);

  return { room, phase, error, startedAt, start, end, fail, dismissError: () => setError(null) };
}

import {
  RoomAudioRenderer, StartAudio, useConnectionState, useLocalParticipant, useTrackToggle,
  useTrackVolume, useTranscriptions, useVoiceAssistant,
} from '@livekit/components-react';
import { ConnectionState, ParticipantEvent, Track, type LocalAudioTrack } from 'livekit-client';
import { useEffect, useMemo, useState } from 'react';
import { statusView, type Lookup } from '../lib/status';
import { CallLayout } from './call/CallLayout';
import type { Line } from './call/types';
import { DeviceMenu } from './DeviceMenu';

const LOOKUPS: Lookup[] = ['idle', 'searching', 'answering', 'failed'];

/** Lookup phase published by the agent; safe before the agent has joined. */
function useLookup(): Lookup {
  const { agent } = useVoiceAssistant();
  const [raw, setRaw] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (!agent) { setRaw(undefined); return; }
    const sync = () => setRaw(agent.attributes['darai.lookup']);
    sync();
    agent.on(ParticipantEvent.AttributesChanged, sync);
    return () => { agent.off(ParticipantEvent.AttributesChanged, sync); };
  }, [agent]);
  return LOOKUPS.includes(raw as Lookup) ? (raw as Lookup) : 'idle';
}

function useLines(): Line[] {
  const items = useTranscriptions();
  const { localParticipant } = useLocalParticipant();
  return useMemo(() => items
    .filter((item) => /[\p{L}\p{N}]/u.test(item.text))  // drop noise like a lone '.'
    .map((item) => ({ id: item.streamInfo.id, mine: item.participantInfo.identity === localParticipant.identity, text: item.text })),
  [items, localParticipant.identity]);
}

/** Wires LiveKit state into the presentational CallLayout. */
export function CallScreen({ onEnd }: { onEnd: () => void }) {
  const { state, audioTrack } = useVoiceAssistant();
  const { microphoneTrack } = useLocalParticipant();
  const mic = useTrackToggle({ source: Track.Source.Microphone });
  const connection = useConnectionState();
  const lookup = useLookup();
  const lines = useLines();
  const view = statusView(state, lookup, !mic.enabled);

  const agentLevel = useTrackVolume(audioTrack);
  const userLevel = useTrackVolume(microphoneTrack?.track as LocalAudioTrack | undefined);
  const level = view.visual === 'speaking' ? agentLevel : view.visual === 'listening' ? userLevel * 0.8 : 0;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'm' && !e.repeat && !(e.target instanceof HTMLInputElement)) void mic.toggle();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mic]);

  return (
    <>
      <CallLayout
        view={view}
        level={level}
        lines={lines}
        reconnecting={connection === ConnectionState.Reconnecting}
        controls={{
          micEnabled: mic.enabled, micPending: mic.pending, onToggleMic: () => void mic.toggle(), onEnd,
          deviceMenu: <DeviceMenu />,
        }}
        footer={<StartAudio label="اضغط لتشغيل صوت المساعد" className="brand-gradient mt-5 rounded-full px-5 py-2.5 text-sm font-bold text-white" />}
      />
      <RoomAudioRenderer />
    </>
  );
}

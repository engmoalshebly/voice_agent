import { RoomContext } from '@livekit/components-react';
import { CallErrorBoundary } from './components/CallErrorBoundary';
import { CallScreen } from './components/CallScreen';
import { Header } from './components/Header';
import { PreCall } from './components/PreCall';
import { useElapsed } from './hooks/useElapsed';
import { useVoiceCall } from './hooks/useVoiceCall';

export function App() {
  const call = useVoiceCall();
  const elapsed = useElapsed(call.startedAt);

  return (
    <div className="flex h-full flex-col brand-backdrop">
      <Header live={call.phase === 'live'} elapsed={elapsed} />
      <main className="flex min-h-0 flex-1 flex-col">
        {call.room && call.phase === 'live' ? (
          <RoomContext.Provider value={call.room}>
            <CallErrorBoundary onCrash={() => void call.fail()}>
              <CallScreen onEnd={() => void call.end()} />
            </CallErrorBoundary>
          </RoomContext.Provider>
        ) : (
          <PreCall phase={call.phase} error={call.error} onStart={() => void call.start()} />
        )}
      </main>
    </div>
  );
}

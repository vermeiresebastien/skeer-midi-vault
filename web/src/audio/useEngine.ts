import { useSyncExternalStore } from 'react';
import type { EngineSnapshot, PreviewEngine } from './engine';

export function useEngineSnapshot(engine: PreviewEngine): EngineSnapshot {
  return useSyncExternalStore(engine.subscribe, engine.getSnapshot, engine.getSnapshot);
}

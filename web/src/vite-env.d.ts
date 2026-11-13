/// <reference types="vite/client" />

import type { PreviewEngine } from './audio/engine';

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
    __SKEER_MIDIVAULT_DEBUG__?: {
      engine: PreviewEngine;
      app: string;
      version: string;
    };
  }
}

export {};

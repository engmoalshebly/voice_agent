import { defineConfig } from 'vite';

/**
 * The embeddable voice assistant, built as two classic scripts (IIFE) a site
 * can include without a module loader:
 *   vite build -c vite.widget.config.ts --mode loader  → dist/widget.js      (the button)
 *   vite build -c vite.widget.config.ts --mode call    → dist/widget-call.js (the call, with LiveKit)
 */
export default defineConfig(({ mode }) => {
  const call = mode === 'call';
  return {
    publicDir: false,
    build: {
      outDir: 'dist',
      emptyOutDir: false,
      target: 'es2019',
      sourcemap: false,
      lib: {
        entry: call ? 'widget/call.ts' : 'widget/loader.ts',
        name: call ? 'DaraiVoiceCallBundle' : 'DaraiVoiceLoader',
        formats: ['iife'],
        fileName: () => (call ? 'widget-call.js' : 'widget.js'),
      },
    },
  };
});

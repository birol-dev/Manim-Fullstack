import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Backend for `npm run dev` (proxied, so the app always talks to its own origin).
const backend = process.env.MANIM_BACKEND_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // Direct access to Monaco's ESM modules (bypasses the package exports map),
      // so src/lib/monacoCore.ts can import only the parts the app needs.
      "monaco-editor-esm": path.resolve(__dirname, "./node_modules/monaco-editor/esm/vs"),
    },
  },
  server: {
    proxy: {
      '/api': { target: backend, ws: true },
      '/media': backend,
      // User uploads; Vite never serves anything under /assets in dev.
      '/assets': backend,
    },
  },
  build: {
    target: 'es2022',
    cssCodeSplit: true,
    // Monaco is large by nature; it is lazy-loaded with the editor.
    chunkSizeWarningLimit: 4000,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: [path.resolve(__dirname, './src/test/setup.ts')],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/main.tsx',
        'src/vite-env.d.ts',
        'src/test/**',
        '**/*.d.ts',
        // Monaco needs a real browser; tests swap in src/test/fakeEditor.tsx.
        'src/lib/monaco.ts',
        'src/lib/monacoCore.ts',
        'src/lib/monaco.worker.ts',
        'src/components/editor/CodeEditor.tsx',
      ],
      thresholds: {
        lines: 75,
        branches: 65,
      },
    },
  },
})

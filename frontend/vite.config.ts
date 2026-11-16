import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // The backend runs on :8000; proxying keeps the frontend free of hard-coded hosts.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
});

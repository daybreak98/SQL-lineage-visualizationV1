import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

const backendProxyTarget = process.env.BACKEND_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        subfield: resolve(__dirname, 'subfield.html'),
      },
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': backendProxyTarget,
    },
  },
  preview: { proxy: { '/api': backendProxyTarget } },
});

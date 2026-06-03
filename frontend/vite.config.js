import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
const backendProxyTarget = process.env.BACKEND_PROXY_TARGET || 'http://localhost:8000';
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        host: '0.0.0.0',
        proxy: {
            '/api': backendProxyTarget,
        },
    },
});

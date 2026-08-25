import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === 'production' ? '/dashboard/' : '/',
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:9528',
    },
  },
}));


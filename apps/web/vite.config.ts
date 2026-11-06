import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5174, strictPort: true,
    proxy: { '/api': { target: `http://127.0.0.1:${process.env.M1_API_PORT || '8010'}`, changeOrigin: true } } },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});

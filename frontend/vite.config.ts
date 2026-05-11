import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
        historyApiFallback: true,
        watch: {
          usePolling: true,
          interval: 1000,
        },
        proxy: {
          '/api': {
            target: 'https://mindweave-ai-backend.onrender.com',
            changeOrigin: true,
            secure: true,
        },
        '/xapi': {
          target: 'https://mindweave-ai-backend.onrender.com',
          changeOrigin: true,
          secure: true,
        },
      },
      },
      plugins: [react()],
      define: {
        'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
        'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      }
    };
});

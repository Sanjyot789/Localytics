import { defineConfig } from 'vite';

const proxy = { '/api/localytics': 'http://127.0.0.1:8766' };
export default defineConfig({ server: { proxy }, preview: { proxy } });

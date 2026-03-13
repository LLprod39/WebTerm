# MiniProd Frontend

Standalone React/Vite frontend extracted from the `mini_prod` monorepo.

## Stack

- React 18
- TypeScript
- Vite
- React Router
- TanStack Query
- Tailwind CSS
- Radix UI
- xterm.js

## Run

```bash
npm install
npm run dev
```

The app expects the backend at `http://127.0.0.1:9000` by default.

You can override it with:

```bash
VITE_DJANGO_URL=http://127.0.0.1:9000
VITE_DJANGO_WS_URL=ws://127.0.0.1:9000
VITE_BACKEND_ORIGIN=http://127.0.0.1:9000
```

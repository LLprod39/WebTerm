# WebTerm frontend-v3

Parallel UI rewrite: keep current `frontend/` on `:8080`, this app on `:8081`.
Both proxy to Django on `:9000`.

## Run

```powershell
cd C:\WebTrerm\frontend-v3
copy .env.example .env
npm install
npm run dev
```

Open `http://127.0.0.1:8081`.

## Proxy

Vite forwards:

- `/api/` → `VITE_DJANGO_URL` (default `http://127.0.0.1:9000`)
- `/servers/api/` → same
- `/ws/` → same (websocket)

`copyProxyHeaders` forwards `Cookie` and domain-auth headers on both HTTP
(`proxyReq`) and WS upgrade (`proxyReqWs`). Without that, terminal/ws auth fails.

## Theme

Default dark monochrome. Light theme via toggle (UI work by Пиксель).

## Notes

- Do not commit `.env*`
- Dual-run until acceptance; then this app becomes primary
- Plan: `docs/frontend-v3/PLAN.md`
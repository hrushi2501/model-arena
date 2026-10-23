# Frontend

Next.js App Router dashboard for Model Arena. It is deployed separately to Vercel; local development uses the Bun workspace from the repository root.

The initial page is a static scaffold. It intentionally displays no sample model metrics or rollout state. The `/api/health` route is a server-side proxy starter; add rollout, model, and audit routes as those control API endpoints are implemented.

Set `MODEL_ARENA_API_URL` in the Vercel project environment for the backend origin. Keep it server-side; do not prefix it with `NEXT_PUBLIC_`.

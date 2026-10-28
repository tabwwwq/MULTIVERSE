# multiverse-api

HTTP API (FastAPI). Composition root: `multiverse_api.main:create_app`. **Status:** health endpoint only.

```bash
npm run dev:api        # http://127.0.0.1:8000/api/v1/health, docs at /api/docs
```

Training and heavy computation never run inside an HTTP request (ADR-0003). Import rules forbid the API from importing `multiverse_forecast`, `multiverse_causal` and `multiverse_pipelines`.

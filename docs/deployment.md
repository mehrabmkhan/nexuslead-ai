# Deployment

NexusLead AI can run anywhere that supports a Python ASGI app or Docker container.

## Render

Use the Dockerfile and expose port `8000`.

Recommended start command if not using Docker:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Fly.io

Deploy with the Dockerfile. Use a small free-tier VM where available and mount a volume if you want SQLite data to persist.

## Railway

Use the Dockerfile or configure a Python service with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## GitHub Pages Static Demo

The full dashboard is FastAPI-backed. A static placeholder export can be generated from `src/nexuslead_ai/static_demo.py`, but the working CRM dashboard requires the FastAPI app.

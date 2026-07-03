# Validation

Run these commands from the repository root:

```bash
python -m pip install -r requirements.txt
python -m compileall app src tests
pytest -q
uvicorn app.main:app --reload
```

Then open:

```text
http://localhost:8000/dashboard
```

The test suite covers lead scoring, client matching, analytics, CSV export, and core FastAPI routes.

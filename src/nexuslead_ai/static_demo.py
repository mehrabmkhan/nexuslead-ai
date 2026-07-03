from pathlib import Path


def write_static_demo(path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        """<!doctype html><html><head><meta charset=\"utf-8\"><title>NexusLead AI Demo</title></head>
<body><h1>NexusLead AI</h1><p>Run the FastAPI app for the interactive dashboard.</p></body></html>""",
        encoding="utf-8",
    )
    return output

"""Writes the FastAPI OpenAPI schema to a JSON file (or stdout) without starting a server.

Used by `npm run api:types` / `npm run api:check` to generate and validate the frontend's
TypeScript API types. Importing the app creates the SQLAlchemy engine, so the database
is pointed at in-memory SQLite and the LLM provider is disabled first — this script never
opens the real application database or contacts an external service.
"""

import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_BASE_URL"] = ""
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402


def toolchain() -> str:
    """The versions that determine the schema's exact output (recorded in the generated
    types so `npm run api:check` can tell a toolchain difference from real API drift)."""
    import platform

    import fastapi
    import pydantic

    return f"python {platform.python_version()}, fastapi {fastapi.__version__}, pydantic {pydantic.__version__}"


def main() -> None:
    if sys.argv[1:] == ["--toolchain"]:
        sys.stdout.write(toolchain() + "\n")
        return
    schema = json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(schema, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(schema)


if __name__ == "__main__":
    main()

"""Static guards keeping the committed API contract honest.

These live in unit_tests/ rather than tests/ because they need no database:
they compare files on disk against the FastAPI app object, which imports
standalone. Same reasoning as test_compose_exposure.py next door.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO_ROOT / "openapi.json"

REGEN_HINT = (
    "The committed API contract is out of date.\n"
    "Regenerate both the snapshot and the frontend types:\n"
    "  ./.venv/bin/python -c \"import json,pathlib; from app.main import app; "
    "pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + chr(10))\"\n"
    "  cd frontend && npm run gen:api\n"
    "then commit openapi.json and frontend/src/api/schema.d.ts together."
)


def canonical_openapi() -> str:
    """The one true serialisation of the live schema. Deterministic: sorted keys,
    fixed indent, trailing newline so the file is POSIX-clean."""
    from app.main import app

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def test_openapi_snapshot_is_current():
    assert SNAPSHOT.exists(), f"{SNAPSHOT} is missing. {REGEN_HINT}"
    assert SNAPSHOT.read_text() == canonical_openapi(), REGEN_HINT


def test_canonical_openapi_is_deterministic():
    """If this ever fails, the snapshot guard would flap and get disabled."""
    assert canonical_openapi() == canonical_openapi()

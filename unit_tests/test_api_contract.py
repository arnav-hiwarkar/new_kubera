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


import re

TYPES_TS = REPO_ROOT / "frontend/src/api/types.ts"
ENDPOINTS_DIR = REPO_ROOT / "frontend/src/api/endpoints"

# Types with no server counterpart, verified absent from the OpenAPI. Every
# entry needs a reason, so this cannot quietly become a dumping ground.
LOCAL_ONLY_TYPES = {
    "ImpactPreview": "master-data impact preview is assembled client-side",
    "TBColumnMap": "trial-balance column mapping is a wizard-local structure",
}


def _schema_names() -> set[str]:
    return set(json.loads(SNAPSHOT.read_text())["components"]["schemas"])


def test_types_ts_has_no_shadow_of_an_api_schema():
    """A hand-written type whose name matches an API component is how drift
    becomes a silent bug: the declaration and the server disagree and nothing
    notices. Three depreciation shadows declared `number` for ~29 fields the API
    sends as Decimal strings; the DocVault approval types were hand-written
    because the generated schema was stale, which is what hid KUB-020-adjacent
    breakage in the graph inspector.

    Narrowing a loosely-typed server field is still allowed — write it as an
    intersection over the generated type (`S['X'] & { status: 'open' | 'closed' }`)
    so the rest of the shape cannot drift.
    """
    src = TYPES_TS.read_text()
    declared = {
        m.group(1)
        for m in re.finditer(
            r"^export\s+(?:interface|type)\s+([A-Za-z0-9_]+)\s*(?:=\s*)?\{", src, re.M
        )
    }
    shadows = sorted((declared & _schema_names()) - set(LOCAL_ONLY_TYPES))
    assert not shadows, (
        "types.ts hand-declares types the API already defines: "
        f"{shadows}\nUse S['<Name>'] instead, or an intersection over it to "
        "narrow a field. Add to LOCAL_ONLY_TYPES with a reason only if the type "
        "genuinely has no server counterpart."
    )


def _normalise(path: str) -> str:
    """`/api/v1/x/${id}/y` and `/api/v1/x/{id}/y` both become `/api/v1/x/{p}/y`."""
    path = re.sub(r"\$\{[^}]*\}", "{p}", path)
    path = re.sub(r"\{[^}]*\}", "{p}", path)
    return path.split("?")[0].rstrip("/")


def test_every_called_route_exists_in_the_contract():
    """Guard 1 catches drift in request/response *shapes*; this catches drift in
    *routes* — a frontend calling an endpoint that no longer exists.

    A bare prefix constant (`'/api/v1/asset-masters'`) counts as valid when real
    routes live beneath it, since those get concatenated at the call site.
    """
    known = {_normalise(p) for p in json.loads(SNAPSHOT.read_text())["paths"]}
    unmatched = []
    for f in sorted(ENDPOINTS_DIR.glob("*.ts")):
        for m in re.finditer(r"""[`'"](/api/v1/[^`'"]*)[`'"]""", f.read_text()):
            raw = m.group(1)
            n = _normalise(raw)
            if n in known or any(k.startswith(n + "/") for k in known):
                continue
            unmatched.append(f"{f.name}: {raw}")
    assert not unmatched, f"frontend calls routes absent from the API: {unmatched}"


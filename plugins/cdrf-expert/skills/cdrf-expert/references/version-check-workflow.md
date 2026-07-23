# DRF Version Check Workflow

Use this workflow whenever behavior may differ across DRF releases.

## Steps

1. Identify installed DRF version from user context (`requirements`, `pyproject`, or direct user statement).
2. Open the matching CDRF version namespace first.
3. Compare target class/method with adjacent versions only if mismatch is suspected.
4. Call out differences explicitly in the answer with version numbers.
5. Provide a safe fallback that works across versions when possible.

## Reporting Template

- Confirmed version: `<version>`
- Class inspected: `<class>`
- Method inspected: `<method>`
- Difference found: `<yes/no>`
- Action: `<override choice or compatibility fallback>`

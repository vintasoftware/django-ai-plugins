# MRO Debugging Playbook

Use this playbook when behavior is surprising or method origin is unclear.

## Steps

1. Open the exact class page in the correct CDRF version.
2. Inspect Ancestors/MRO to identify method provider order.
3. Locate the method in the Methods table and confirm the source class.
4. Verify if a mixin implementation calls helper hooks (`perform_*`, `get_queryset`, `get_object`).
5. Choose the lowest-risk override point in the nearest class you own.

## What to Extract from CDRF

- Full MRO chain
- Method source class
- Related helper hooks called by that method
- Attribute defaults that influence that path

## Debugging Heuristics

- If pagination or filtering seems skipped, inspect whether custom `list` bypassed mixin logic.
- If object-level permission checks seem skipped, inspect custom `get_object` or manual queryset access.
- If serializer differs by action incorrectly, inspect `get_serializer_class` and action names.

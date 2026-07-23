---
name: cdrf-expert
description: Expert guidance for Django REST Framework class-based views using Classy DRF (https://www.cdrf.co). Use when selecting or debugging APIView, GenericAPIView, concrete generic views, mixin combinations, or ViewSet/GenericViewSet/ModelViewSet behavior; tracing method resolution order (MRO); understanding which method to override (`create` vs `perform_create`, `update` vs `perform_update`, `destroy` vs `perform_destroy`, `get_queryset`, `get_serializer_class`); and comparing behavior across DRF versions. Do not use for function-based views, GraphQL, FastAPI/Flask, frontend work, or non-DRF backend frameworks.
---

# CDRF Expert

## Instructions

1. Classify the request.

Map the user request to one or more categories:
- Class selection (APIView vs GenericAPIView vs concrete generics vs ViewSets)
- Lifecycle tracing (request-to-response flow)
- Override strategy (which hook to customize)
- MRO debugging (method came from mixin/base class)
- Version differences (behavior changed between DRF versions)

2. Read only the required reference file(s).

Load the minimum needed context:
- `references/class-selection-matrix.md` for class selection
- `references/lifecycle-and-overrides.md` for hook placement and lifecycle
- `references/mro-debugging-playbook.md` for MRO/source-of-method tracing
- `references/version-check-workflow.md` for DRF-version comparisons

3. Navigate cdrf.co with version-first discipline.

- Identify the project DRF version from user context.
- If unknown, ask for version or provide a version-agnostic answer and explicitly mark assumptions.
- Open the matching CDRF version namespace first (for example `https://www.cdrf.co/3.16/`).
- Open the target class page and extract:
  - Ancestors and MRO
  - Available methods and source class for each method
  - Default attributes that affect behavior (`queryset`, `serializer_class`, pagination/filter backends)

4. Choose the minimal override point.

- Prefer narrow hooks (`perform_create`, `perform_update`, `perform_destroy`) before broad methods (`create`, `update`, `destroy`).
- Prefer `get_queryset` and `get_serializer_class` for per-request behavior over hardcoding class attributes.
- Keep HTTP orchestration in view methods and business/domain logic outside views.
- Preserve DRF defaults unless the request needs behavior changes.

5. Produce an answer grounded in method flow.

Return:
- Recommended class
- Method(s) to override
- Why these methods are correct in the MRO/lifecycle
- Concise code patch or skeleton
- Risks/regressions and tests to add

6. Validate before finalizing.

Check for common regressions:
- Accidentally bypassing permission/authentication/filter/pagination hooks
- Duplicating object-save logic between serializer and view
- Overriding broad methods when narrow hooks are sufficient
- Depending on methods not present in the selected DRF version

## Error Handling

1. If cdrf.co is unavailable, state that limitation and fall back to DRF official docs and installed source code.
2. If the user cannot provide DRF version, provide a version-agnostic path and clearly mark assumptions.
3. If multiple override points appear valid, recommend the narrowest hook first and explain tradeoffs.

## Output Rules

- Cite exact class and method names from CDRF.
- State assumptions when DRF version is unknown.
- Keep responses focused on DRF CBV internals and actionable code changes.

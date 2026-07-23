# Lifecycle and Override Guide

Use this file to place customization at the correct hook.

## Request Lifecycle (GenericAPIView family)

1. `dispatch`
2. `initialize_request`
3. `initial`
4. Authentication / permissions / throttling
5. Action method (`list`, `retrieve`, `create`, `update`, `partial_update`, `destroy`)
6. Serializer validation and persistence hooks
7. `finalize_response`

## Override Placement

- Query scoping: `get_queryset`
- Serializer choice by request/action: `get_serializer_class`
- Serializer context extension: `get_serializer_context`
- Object lookup customization: `get_object`
- Save-time side effects for create: `perform_create`
- Save-time side effects for update: `perform_update`
- Delete-time side effects: `perform_destroy`

## Prefer Narrow Hooks

1. Override `perform_create` instead of `create` unless HTTP response shape/status must change.
2. Override `perform_update` instead of `update`/`partial_update` unless orchestration must change.
3. Override `perform_destroy` instead of `destroy` unless response semantics must change.

## Common Mistakes

- Putting filtering/security scoping in `list` instead of `get_queryset`
- Duplicating validation in view and serializer
- Bypassing DRF orchestration by reimplementing `create`/`update` unnecessarily

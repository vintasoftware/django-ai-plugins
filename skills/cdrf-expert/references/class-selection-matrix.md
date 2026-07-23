# Class Selection Matrix

Use this matrix to choose the smallest DRF class that satisfies the requirement.

## Decision Rules

1. Use `APIView` when request/response flow is custom and generic query/serializer behavior is not needed.
2. Use `GenericAPIView` + selected mixins when custom combinations are required.
3. Use concrete generics (`ListAPIView`, `RetrieveAPIView`, `ListCreateAPIView`, etc.) for standard CRUD endpoints.
4. Use `GenericViewSet` or `ModelViewSet` when router-based multi-action resources are required.
5. Use `ReadOnlyModelViewSet` when only `list`/`retrieve` are needed.

## Quick Mapping

- List only: `ListAPIView` or `ReadOnlyModelViewSet`
- Retrieve only: `RetrieveAPIView` or `ReadOnlyModelViewSet`
- List + create: `ListCreateAPIView` or `ModelViewSet`
- Retrieve + update + delete: `RetrieveUpdateDestroyAPIView` or `ModelViewSet`
- Full CRUD with routers/actions: `ModelViewSet`
- Non-CRUD custom verbs/behavior: `APIView` or `ViewSet`

## Selection Checklist

- Confirm whether routers are required.
- Confirm if pagination/filter/ordering/search should be automatic.
- Confirm whether object lookup is single-field or custom/composite.
- Confirm whether per-action serializers/permissions are needed.

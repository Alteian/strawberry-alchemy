# API reference

Everything importable from the top-level `strawberry_alchemy` package, grouped by
area. Submodule-only symbols are listed at the end.

```python
import strawberry_alchemy
print(strawberry_alchemy.__version__)
```

## Enums and errors

| Symbol | Description |
|---|---|
| `Ordering` | Strawberry enum: `ASC`, `DESC` |
| `NotFoundError` | Raised by repository get/update/delete misses |

## Models

| Symbol | Description |
|---|---|
| `Base` | Abstract SQLAlchemy base: UUID PK, timestamps, auto `__tablename__` (Postgres UUID) |
| `SoftDeleteMixin` | Adds nullable indexed `deleted_at` |

## Types

| Symbol | Description |
|---|---|
| `BaseNodeType` | Relay `Node` + ClassVar ACL; `resolve_node(s)` / `resolve_list` / `resolve_connection` / `from_schema` |
| `ListResult[T]` | `{items, total_count}` list wrapper |
| `NestedListResult[T]` | `{items, has_more}` capped nested to-many wrapper |
| `NodeConfig` | `max_items` + per-field `fields` map for nested selectin caps |
| `OptimizedListConnection[T]` | Relay connection + `total_count` |
| `Edge` / `PageInfo` | Re-exports from `strawberry.relay` |
| `SliceMetadata` | Cursor/first/last → start/end/`fetch_limit` |

### `BaseNodeType` ClassVars

- `access_filter` (required)
- `node_config: NodeConfig = NodeConfig()` (default nested list cap 100)
- `CUSTOM_FILTERS: dict[str, Callable] = {}`
- `model_class` (from access filter)

### Resolve signatures

```python
await Type.resolve_node(node_id: str, *, info: Info, access_filter=None) -> Type | None
await Type.resolve_nodes(info: Info, node_ids: Iterable[str], access_filter=None, **kwargs) -> list[Type | None]
await Type.resolve_list(info: Info, filters=UNSET, **kwargs) -> ListResult[Type]
await Type.resolve_connection(info: Info, **kwargs) -> OptimizedListConnection[Type]
Type.from_schema(schema, **kwargs) -> Type
await resolve_mutation_node(info, Type, id, *, field=None, access_filter=None) -> Type | None
await resolve_mutation_nodes(info, Type, ids, *, field=None, access_filter=None) -> list[Type | None]
```

`resolve_node` / `resolve_nodes` accept `target_field_path=` (nested payload
selection) and `acquire_lock=` (default `True`). Prefer `resolve_mutation_node`
after mutation writes when the lock is already held.

## Optimizer

| Symbol | Description |
|---|---|
| `QueryOptimizer` | Selection set → one optimized SQLAlchemy query |
| `QueryResult` | Frozen `{items, selected_fields, total_count}` |
| `QueryAnalyzer` | Per-query diagnostics; env `QUERY_ANALYZER_ENABLED`; `on_report=` hook |
| `optimize_field` | Decorator attaching optimizer hints to computed fields |
| `PrefetchRelated` | `(relationship, fields=None, filter_current_user=False, filter=None, access_filter=None, max_items=unset)` |
| `SelectColumns` | `(*fields: str)` — undefer same-row scalars |
| `AnnotateExists` | Correlated EXISTS → bool attr |
| `AnnotateAnyExists` | OR of EXISTS over relationships |
| `AnnotateCount` | Correlated COUNT |
| `AnnotateCustom` | Custom SQL expression (+ optional mapper) |
| `AnnotateAncestry` | Recursive parent-walk CTE (`value_mode` `"ids"` / `"chain"`) |
| `FieldPath` | Immutable field-path helper |
| `FieldSelection` / `LeafSelection` / `RelayConnectionSelection` | Typed selection-tree nodes |
| `parse_selection_tree` | Parse raw selection dict → typed tree |
| `extract_at_path` | Drill into selection by path |
| `selection_to_model_fields` | Tree → model field dict |
| `build_recursive_dependency_tree` | Nested self-relation dependency dict |
| `merge_dependency_trees` / `normalize_dependency_fields` | Merge/normalize dependency trees |
| `source_path_to_dependency_tree` | Dotted path → nested `{field: True}` tree |

### `QueryOptimizer.optimize_query`

```python
await optimizer.optimize_query(
    model,
    *,
    node_ids=None,
    filters=None,
    return_selected_fields=False,
    filter_context_user=False,
    apply_access_control=True,
    order=None,
    limit=None,
    offset=None,
    return_total_count=False,
    target_field_path=None,
    strawberry_type=None,
    exclude_prefetch=None,
) -> QueryResult
```

## Filtering

| Symbol | Description |
|---|---|
| `AccessControlFilter` | Base for model-keyed row ACL (`*AccessFilter` name enforced) |
| `RelationAccessFilter` | `FieldExtension`: edge-local ACL; optional `foreign_key=` |
| `MaxItems` | `FieldExtension`: per-edge nested to-many cap (`None` = unlimited) |
| `FilterBuilder` | Filter inputs / dicts → SQL WHERE |
| `FilterOperators` | Lookup → SQLAlchemy operator registry |
| `IDFilter` | `exact`, `in_`, `not_in_`, `isnull` |
| `StringFilter` | string operators including `icontains`, … |
| `IntFilter` | numeric comparisons + `range` |
| `BooleanFilter` | `exact`, `isnull` |
| `DateFilter` | date comparisons (SQL `Date` columns) |
| `DateTimeFilter` | datetime comparisons |
| `EnumFilter` | enum `exact` / `in_` / … |
| `JSONFilter` | JSONB containment / key operators |

```python
RelationAccessFilter(access_filter, *, foreign_key: str | None = None)
MaxItems(max_items: int | None)  # None = unlimited
```

## Mapping

| Symbol | Description |
|---|---|
| `map_sqlalchemy_to_type` | Instance + selection → Strawberry type |
| `map_sqlalchemy_list_to_types` | List mapping helper |

## Permissions

| Symbol | Description |
|---|---|
| `IsAuthenticated` | Require logged-in user |
| `RolePermission` | `RolePermission(role=...)` |
| `OwnerPermission` | `OwnerPermission(owner_field="user_id", resource_key=None)` |
| `ObjectAccessPermission` | Membership in an access collection field |
| `BasePermissionResolver` | ABC: operation → permission list |
| `ResourceInstances` | Loaded-resource bag for mutation checks |
| `HasId` / `IdentityLike` / `UserLike` / `PermissionContextLike` / `ModelRegistryLike` | Protocols |
| `extract_global_ids_from_info` | Decode GlobalIDs from input dict |
| `map_ids_to_models` | IDs + loaders → `ResourceInstances` |
| `fetch_and_check_permissions` | Run permission list against bag |
| `prepare_mutation_resources` | Decode → load → check |

```python
await prepare_mutation_resources(
    info,
    input_data,
    *,
    loaders: Mapping[str, Callable[[UUID], Awaitable[Any]]],
    permissions: Sequence[Any],
    id_fields: list[str] | None = None,
) -> ResourceInstances
```

## Repository

| Symbol | Description |
|---|---|
| `BaseRepository` | Async CRUD, soft-delete, relation add/remove, deletion reports |
| `BaseDeletionHandler` | Cascade/cleanup hooks around delete |
| `DeletionReport` / `DeletionFailure` / `DeletionPartialFailure` | Soft-failure reporting for delete |

### `BaseRepository` ClassVars

`model_cls`, `schema_cls`, `relation_models`, `soft_delete_field`

### Methods

```python
get_by_id(id, options=None, *, include_deleted=False) -> SchemaT
get_by_ids(ids, options=None, *, include_deleted=False) -> list[SchemaT]
create(schema, should_commit=True) -> SchemaT
update(schema, should_commit=True, instance=None) -> SchemaT
delete(id, should_commit=True, instance=None, *, strict=False) -> DeletionReport
soft_delete(id, should_commit=True, instance=None) -> SchemaT
add_related(id, relation_name, related_ids, should_commit=True) -> SchemaT
remove_related(id, relation_name, related_ids, should_commit=True) -> SchemaT
apply_not_deleted(stmt) -> Select
```

## Schema

| Symbol | Description |
|---|---|
| `BaseSchema` | Pydantic base: `dump_for_db`, `to_type`, `from_input` |
| `schema_from_input` | GraphQL input → any Pydantic model |

```python
schema_from_input(model_cls, input, **kwargs) -> BaseModel
BaseSchema.from_input(input, **kwargs) -> Self
schema.dump_for_db(exclude=None, **kwargs) -> dict
schema.to_type(target_cls, **kwargs) -> T
```

## Postgres RLS

| Symbol | Description |
|---|---|
| `apply_rls_context` | Batch-set transaction-local `app.*` GUCs |
| `set_rls_guc` | Set one GUC |
| `clear_rls_context` | Clear named GUCs |

```python
await set_rls_guc(session, "company_id", str(company_id), *, prefix="app")
await apply_rls_context(session, values: Mapping[str, Any], *, prefix="app")
await clear_rls_context(session, names: list[str], *, prefix="app")
```

## Utils

| Symbol | Description |
|---|---|
| `camel_to_snake` | String or dict key conversion |

---

## Submodule-only exports

### `strawberry_alchemy.filtering`

All filter symbols are also re-exported at the package root (including
`DateFilter`).

### `strawberry_alchemy.optimizer`

| Symbol | Description |
|---|---|
| `QueryEvent` / `QueryReport` | Analyzer event / report types |
| `ResolvedDependencies` | Resolved hint dependency structure |
| `get_prefetch_map` | Collect prefetch map from a Strawberry type |

### `strawberry_alchemy.mapping`

| Symbol | Description |
|---|---|
| `register_global_id_type` / `clear_global_id_type_registry` | Encode-side GlobalID registry |
| `create_global_id_from_field` | Build GlobalID from registered field |
| `map_sqlalchemy_to_type_with_path` | Mapping at a nested path |
| `get_graphql_type_from_sqlalchemy` | Resolve GraphQL type for an instance |
| `extract_fields_at_path` / `extract_nested_fields` | Selection-tree helpers |

### `strawberry_alchemy.repository`

| Symbol | Description |
|---|---|
| `DependentMap` | Type alias `dict[str, list[uuid.UUID]]` |

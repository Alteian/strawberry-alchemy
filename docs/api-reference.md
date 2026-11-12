# API Reference

Everything importable from the top-level `strawberry_alchemy` package, grouped by
module. Submodule paths are shown for the few names that are not re-exported at the
top level.

## Top-level exports

```python
from strawberry_alchemy import (
    # enums & exceptions
    Ordering,              # strawberry.enum: ASC | DESC
    NotFoundError,         # Exception raised by BaseRepository.get_by_id / update / delete

    # models
    Base,                  # SQLAlchemy DeclarativeBase: UUID pk + created_at/updated_at (PostgreSQL)
    SoftDeleteMixin,       # optional deleted_at column for soft-delete repositories

    # types
    BaseNodeType,          # Relay Node with id/created_at/updated_at + resolver classmethods
    ListResult,            # @strawberry.type: items + total_count
    OptimizedListConnection,  # Relay Connection with total_count
    Edge,                  # re-exported from strawberry.relay
    PageInfo,              # re-exported from strawberry.relay
    SliceMetadata,         # cursor-slice math helper (from_arguments, fetch_limit)

    # optimizer
    QueryOptimizer,        # selection-set -> one optimized SQLAlchemy query
    QueryResult,           # frozen dataclass: items, selected_fields, total_count
    QueryAnalyzer,         # per-query diagnostics (env: QUERY_ANALYZER_ENABLED; on_report hook)
    FieldPath, FieldSelection, LeafSelection, RelayConnectionSelection,
    optimize_field,        # decorator for computed-field hints
    PrefetchRelated,       # hint: load relationship (optionally filtered) + fields
    SelectColumns,         # hint: un-defer scalar columns of the current model
    AnnotateExists,        # hint: correlated EXISTS subquery
    AnnotateAnyExists,     # hint: OR of EXISTS over several relationships
    AnnotateCount,         # hint: correlated COUNT subquery
    AnnotateCustom,        # hint: custom SQL expression + optional mapper
    AnnotateAncestry,      # hint: recursive parent-walk CTE (ids | chain)
    build_recursive_dependency_tree,
    merge_dependency_trees,
    normalize_dependency_fields,
    source_path_to_dependency_tree,
    extract_at_path,
    parse_selection_tree,
    selection_to_model_fields,

    # filtering
    AccessControlFilter,   # per-model row-level security base (must be named *AccessFilter)
    FilterBuilder,         # Strawberry inputs / dicts -> SQL WHERE
    FilterOperators,       # LOOKUP_OPERATORS registry
    IDFilter, StringFilter, IntFilter, BooleanFilter, DateTimeFilter, EnumFilter,
    JSONFilter,            # jsonb_contains / has_key / path / … (Postgres JSONB)

    # mapping
    map_sqlalchemy_to_type,
    map_sqlalchemy_list_to_types,

    # permissions
    IsAuthenticated, RolePermission, OwnerPermission, ObjectAccessPermission,
    BasePermissionResolver,
    ResourceInstances,
    HasId, IdentityLike, UserLike, PermissionContextLike, ModelRegistryLike,
    extract_global_ids_from_info,
    fetch_and_check_permissions,
    map_ids_to_models,
    prepare_mutation_resources,  # GlobalID parse → load → permission bag

    # repository
    BaseRepository,
    BaseDeletionHandler,
    DeletionReport, DeletionFailure, DeletionPartialFailure,

    # schema
    BaseSchema,
    schema_from_input,     # GraphQL input → Pydantic/BaseSchema (GlobalID → UUID)

    # utils
    camel_to_snake,

    # postgres RLS session GUCs
    apply_rls_context,
    clear_rls_context,
    set_rls_guc,
)
```

Submodule-only helpers (not re-exported at the package root):

```python
from strawberry_alchemy.mapping import register_global_id_type, clear_global_id_type_registry
```

See [Postgres RLS](postgres-rls.md) for policy DDL and session wiring.

## Types

### `BaseNodeType`

```python
@strawberry.type
class BaseNodeType(Node):
    id: NodeID[uuid.UUID]
    created_at: datetime | None = strawberry.UNSET
    updated_at: datetime | None = strawberry.UNSET

    access_filter: ClassVar[type[AccessControlFilter] | AccessControlFilter]  # required
    model_class: ClassVar[type[Any]]                     # derived from access_filter

    @classmethod
    def from_schema(cls, schema, **kwargs) -> Self              # schema -> type
    @classmethod
    async def resolve_node(cls, node_id: str, *, info: Info, access_filter=None) -> Self | None
    @classmethod
    async def resolve_nodes(cls, info: Info, node_ids: Iterable[str], access_filter=None, **kwargs) -> list[Self | None]
    @classmethod
    async def resolve_list(cls, info: Info, filters=strawberry.UNSET, **kwargs) -> ListResult[Self]
    @classmethod
    async def resolve_connection(cls, info: Info, **kwargs) -> OptimizedListConnection[Self]
```

`resolve_list` / `resolve_connection` accept `limit`, `offset`, `filters`, `order`,
`access_filter` (optional per-call override of the ClassVar), and any
`QueryOptimizer.optimize_query` keyword arguments.

### `ListResult[T]`

```python
@strawberry.type
class ListResult[T]:
    items: list[T]
    total_count: int | None = strawberry.UNSET
```

### `OptimizedListConnection[NodeType]`

```python
@strawberry.type
class OptimizedListConnection[NodeType](relay.Connection[NodeType]):
    edges: list[Edge[NodeType]]
    page_info: PageInfo
    total_count: int

    @classmethod
    async def resolve_connection(
        cls, optimizer, model, graphql_type, info, *,
        filters=None, order=None, after=None, before=None,
        first=None, last=None, return_total_count=False,
        strawberry_type=None, exclude_prefetch=None,
    ) -> OptimizedListConnection[NodeType]
```

### `SliceMetadata`

```python
class SliceMetadata:
    start: int
    end: int | None
    requested_count: int | None
    fetch_limit: int | None           # property: requested_count + 1

    @classmethod
    def from_arguments(cls, info, before=None, after=None, first=None, last=None, max_results=None) -> SliceMetadata
```

## Optimizer

### `QueryOptimizer`

```python
class QueryOptimizer:
    def __init__(self, info: Info, session: AsyncSession, *, analyzer: QueryAnalyzer | None = None)

    def register_access_filter(self, model_class: type, filter_class: type[AccessControlFilter] | AccessControlFilter) -> None
    def register_access_filter_by_name(self, model_name: str, filter_class: type[AccessControlFilter] | AccessControlFilter) -> None
    def get_access_filter(self, model: type) -> Any | None
    async def apply_access_control(self, query, model) -> Any
    async def optimize_query(self, model, *, node_ids=None, filters=None,
        return_selected_fields=False, filter_context_user=False,
        apply_access_control=True, order=None, limit=None, offset=None,
        return_total_count=False, target_field_path=None,
        strawberry_type=None, exclude_prefetch=None) -> QueryResult
    def process_selected_fields(self, selected_fields: list) -> dict
    def extract_model_fields(self, selected_fields: dict, level: int = 0) -> dict
    def process_order(self, model, order_input) -> tuple[list, dict]
```

### `QueryResult`

```python
@dataclass(frozen=True)
class QueryResult:
    items: list = []
    selected_fields: dict = {}
    total_count: int = 0
```

### Optimizer hints

```python
@dataclass(frozen=True)
class PrefetchRelated:
    relationship: str
    fields: list[str] | dict[str, Any] | None = None
    filter_current_user: bool = False
    filter: Callable[[type], Any] | None = None
    has_custom_loading: bool            # property

class SelectColumns:                    # SelectColumns("s3_key", "variants")
    fields: tuple[str, ...]

@dataclass(frozen=True)
class AnnotateExists:
    relationship: str
    filter_current_user: bool = False
    to_attr: str = ""                   # default attr: _<relationship>_exists
    filter: Callable[[type], Any] | None = None

@dataclass(frozen=True)
class AnnotateAnyExists:
    relationships: list[str]
    filter_current_user: bool = False
    to_attr: str = ""                   # default attr: _<r1>_<r2>_any_exists
    filter: Callable[[type], Any] | None = None

@dataclass(frozen=True)
class AnnotateCount:
    relationship: str
    filter_current_user: bool = False
    to_attr: str = ""                   # default attr: _<relationship>_count
    filter: Callable[[type], Any] | None = None

@dataclass(frozen=True)
class AnnotateCustom:
    relationship: str
    expression: Callable[..., Any] | None   # (model, related_model, rel_prop[, user_id]) -> SQL expr
    to_attr: str = ""
    mapper: Callable[[Any], Any] | None = None
    filter_current_user: bool = False

@dataclass(frozen=True)
class AnnotateAncestry:                # recursive CTE; value_mode "ids"|"chain"
    relationship: str
    parent_field: str = "parent_id"
    id_field: str = "id"
    to_attr: str = ""
    include_self: bool = True
    root_first: bool = True
    value_mode: str = "ids"
    cte_name: str = "ancestry"
```

### `optimize_field`

```python
def optimize_field(*args: str | PrefetchRelated | SelectColumns | AnnotateExists
                   | AnnotateAnyExists | AnnotateCount | AnnotateCustom | AnnotateAncestry,
                   **kwargs: list[str] | dict[str, Any]) -> Callable
```

### Field-tree helpers

```python
def normalize_dependency_fields(fields: list[str] | dict[str, Any]) -> dict[str, Any]
def merge_dependency_trees(base: dict, extra: dict) -> dict
def build_recursive_dependency_tree(relationship: str, *, fields: list[str] | None = None, depth: int = 1) -> dict
def source_path_to_dependency_tree(source_path: str) -> dict
def get_prefetch_map(strawberry_type: type) -> dict[str, list[OptimizerHint]]
```

### `QueryAnalyzer`

```python
class QueryAnalyzer:
    def __init__(self, *, log_sql: bool = True, log_level: int = logging.INFO,
                 on_report: Callable[[QueryReport], None] | None = None)
    def begin(self, model) / end(self) / reset(self)
    # end() stamps wall-clock end time used by report().total_duration_ms
    def record_selected_fields / record_deferred / record_relationship /
         record_load_strategy / record_annotation /
         record_query(..., duration_ms=0.0) / record_result / add_warning
    def report(self) -> QueryReport
    def log_report(self) -> QueryReport  # also invokes on_report when set
```

`QueryReport` fields: `model_name`, `total_duration_ms`, `query_count`, `queries`
(each `QueryEvent` has `duration_ms` / `row_count`), `requested_fields`,
`deferred_fields`, `relationships_loaded`, `annotations`, `load_strategies`,
`warnings`, `result_count`, `total_count`; plus `summary()` and `as_dict()`.
Pass `on_report=` to push reports into OTel/metrics without subclassing.

## Filtering

### `FilterBuilder`

```python
class FilterBuilder:
    def __init__(self, custom_filters: dict[type, dict[str, Any]] | None = None)
    async def build_filters(self, model, filters: dict[str, Any]) -> BinaryExpression | None
    async def build_field_filter(self, model, field, value, lookup="exact", path_prefix="") -> BinaryExpression | None
    def build_filter_dict(self, filters) -> dict[str, Any]
    def process_filter_object(self, filter_obj, filter_dict, add_filter, parent_key="")
    async def parse_filter_value(self, value, field) -> Any
    alias_map: dict[str, AliasedClass | type]           # relationship aliases created while building
```

### Filter inputs

All inputs default every field to `strawberry.UNSET`:

- `IDFilter` — `exact: GlobalID`, `in_`, `not_in_`, `isnull`
- `StringFilter` — `exact`, `iexact`, `contains`, `icontains`, `startswith`,
  `istartswith`, `endswith`, `iendswith`, `in_`, `not_in_`, `isnull`
- `IntFilter` — `exact`, `gt`, `ge`, `lt`, `le`, `in_`, `not_in_`, `isnull`, `range`
- `BooleanFilter` — `exact`, `isnull`
- `DateTimeFilter` — `exact`, `ge`, `gt`, `lt`, `le`, `in_`, `not_in_`, `isnull`, `range`
- `EnumFilter[EnumType]` — `exact`, `in_`, `not_in_`, `isnull`
- `JSONFilter` — `jsonb_contains`, `jsonb_contained_by`, `jsonb_has_key`,
  `jsonb_has_any`, `jsonb_has_all`, `jsonb_path` (Postgres JSONB columns).
  Nested localized-string style keys (e.g. `title={cs: StringFilter(...)}`)
  compile to `column['cs'].astext` lookups.

### `FilterOperators`

```python
class FilterOperators:
    LOOKUP_OPERATORS = {
        "exact", "iexact", "contains", "icontains", "in", "not_in",
        "gt", "ge", "lt", "le", "startswith", "istartswith",
        "endswith", "iendswith", "range", "isnull",
        "jsonb_contains", "jsonb_contained_by", "jsonb_has_key",
        "jsonb_has_any", "jsonb_has_all", "jsonb_path",
    }
```

### `AccessControlFilter`

```python
class AccessControlFilter(metaclass=AccessControlMeta):   # subclass names must end with 'AccessFilter'
    model_class: ClassVar[type[Any]]                      # required on subclasses

    @staticmethod
    async def apply_filter(query, model, context_user) -> query
```

## Repository

### `BaseRepository[ModelT, SchemaT, DeletionHandlerT]`

```python
class BaseRepository:
    relation_models: ClassVar[dict[str, type]] = {}
    soft_delete_field: ClassVar[str | None] = None   # e.g. "deleted_at"

    def __init__(self, session: AsyncSession, model_cls, schema_cls, *, deletion_handler=None)

    async def get_by_id(self, id: uuid.UUID, options=None, *, include_deleted=False) -> SchemaT
    async def get_by_ids(self, ids, options=None, *, include_deleted=False) -> list[SchemaT]
    async def create(self, schema, should_commit=True) -> SchemaT
    async def update(self, schema, should_commit=True, instance=None) -> SchemaT
    async def delete(self, id, should_commit=True, instance=None, *, strict=False) -> DeletionReport
    async def soft_delete(self, id, should_commit=True, instance=None) -> SchemaT
    async def add_related(self, id, relation_name, related_ids, should_commit=True) -> SchemaT
    async def remove_related(self, id, relation_name, related_ids, should_commit=True) -> SchemaT
```

### `BaseDeletionHandler[ModelT]` / `DeletionReport`

```python
class DeletionReport:
    entity_id: uuid.UUID | None
    failures: list[DeletionFailure]
    def record(...) / extend(...) / summary() -> str
    @property
    def has_failures(self) -> bool

class DeletionPartialFailure(RuntimeError):  # raised when delete(..., strict=True) and failures exist
    report: DeletionReport

class BaseDeletionHandler:
    def reset_report(self, entity_id=None) -> DeletionReport
    @property
    def report(self) -> DeletionReport
    async def collect_dependents(self, session, entity_id, instance) -> DependentMap
    async def pre_delete / cleanup_external / handle_cascade / post_delete ...
```

## Schema

```python
class BaseSchema(BaseModel):
    # model_config: from_attributes=True, validate_assignment=True, arbitrary_types_allowed=True
    def dump_for_db(self, exclude: set[str] | None = None, **kwargs) -> dict[str, Any]
    def to_type[T](self, target_cls: type[T], **kwargs) -> T
    @classmethod
    def from_input(cls, input, **kwargs) -> Self   # GraphQL input → schema (GlobalID → UUID)

def schema_from_input(model_cls: type[BaseModel], input, **kwargs) -> BaseModel
```

## Mapping

```python
async def map_sqlalchemy_to_type(instance, info, target_type, selected_fields) -> T | None
async def map_sqlalchemy_list_to_types(instances, info, target_type, selected_fields) -> list[T]
async def map_sqlalchemy_to_type_with_path(instance, info, target_type, selected_fields, field_path="") -> T | None
def get_graphql_type_from_sqlalchemy(info, instance) -> type | None
def extract_fields_at_path(selected_fields, path) -> dict
def extract_nested_fields(selected_fields, field_path) -> dict
def create_global_id_from_field(field_name, value) -> GlobalID
def register_global_id_type(field_name, type_name) -> None   # strawberry_alchemy.mapping
def clear_global_id_type_registry() -> None
```

Dict / JSONB scalars are trimmed to keys requested in the selection tree when mapping.

## Permissions

```python
class IsAuthenticated:                                  # has_permission(info, **kwargs)
class RolePermission(role=...)                          # user.role == role
class OwnerPermission(owner_field="user_id", resource_key=None)
class ObjectAccessPermission(access_field="allowed_user_ids", resource_key=None)

class BasePermissionResolver(ABC):
    def resolve(self, operation: str, *, data: dict | None = None, **kwargs) -> list

async def fetch_and_check_permissions(info, permissions, resource_instances=None) -> None   # raises PermissionError
def extract_global_ids_from_info(data, id_fields=None) -> dict[str, UUID | str | None]
async def map_ids_to_models(ids, loaders, bag=None) -> ResourceInstances
async def prepare_mutation_resources(info, ids, *, loaders, permissions) -> ResourceInstances

class ResourceInstances:        # add / add_list / get / get_id / all / __contains__
```

Protocols: `HasId`, `IdentityLike` (stable `id`-only identity contract), `UserLike`
(id + role), `PermissionContextLike` (`current_user`, `identity`), `ModelRegistryLike`.

## Utils

```python
def camel_to_snake(data: str | dict) -> str | dict   # "camelCaseString" -> "camel_case_string"

class NotFoundError(Exception): ...
```

## Enums

```python
@strawberry.enum
class Ordering(Enum):
    ASC = "ASC"
    DESC = "DESC"
```

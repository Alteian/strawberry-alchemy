from importlib.metadata import version as _version

__version__ = _version("strawberry-alchemy")

from strawberry_alchemy.enums import Ordering
from strawberry_alchemy.exceptions import NotFoundError
from strawberry_alchemy.filtering import (
    AccessControlFilter,
    BooleanFilter,
    DateTimeFilter,
    EnumFilter,
    FilterBuilder,
    FilterOperators,
    IDFilter,
    IntFilter,
    StringFilter,
)
from strawberry_alchemy.mapping import (
    map_sqlalchemy_list_to_types,
    map_sqlalchemy_to_type,
)
from strawberry_alchemy.models import Base
from strawberry_alchemy.optimizer import (
    AnnotateAncestry,
    AnnotateAnyExists,
    AnnotateCount,
    AnnotateCustom,
    AnnotateExists,
    PrefetchRelated,
    QueryAnalyzer,
    QueryOptimizer,
    QueryResult,
    build_recursive_dependency_tree,
    merge_dependency_trees,
    normalize_dependency_fields,
    optimize_field,
    source_path_to_dependency_tree,
)
from strawberry_alchemy.permissions import (
    BasePermissionResolver,
    HasId,
    IdentityLike,
    IsAuthenticated,
    ModelRegistryLike,
    ObjectAccessPermission,
    OwnerPermission,
    PermissionContextLike,
    ResourceInstances,
    RolePermission,
    UserLike,
    extract_global_ids_from_info,
    fetch_and_check_permissions,
    map_ids_to_models,
)
from strawberry_alchemy.repository import (
    BaseDeletionHandler,
    BaseRepository,
)
from strawberry_alchemy.schema import BaseSchema
from strawberry_alchemy.types import (
    BaseNodeType,
    Edge,
    ListResult,
    OptimizedListConnection,
    PageInfo,
    SliceMetadata,
)
from strawberry_alchemy.utils import (
    camel_to_snake,
)

__all__ = (
    "__version__",
    "AccessControlFilter",
    "AnnotateAncestry",
    "AnnotateAnyExists",
    "AnnotateCount",
    "AnnotateCustom",
    "AnnotateExists",
    "Base",
    "BaseDeletionHandler",
    "BaseNodeType",
    "BasePermissionResolver",
    "BaseRepository",
    "BaseSchema",
    "BooleanFilter",
    "DateTimeFilter",
    "Edge",
    "EnumFilter",
    "FilterBuilder",
    "FilterOperators",
    "HasId",
    "IdentityLike",
    "IDFilter",
    "IntFilter",
    "IsAuthenticated",
    "ListResult",
    "ModelRegistryLike",
    "NotFoundError",
    "ObjectAccessPermission",
    "OptimizedListConnection",
    "Ordering",
    "OwnerPermission",
    "PageInfo",
    "PermissionContextLike",
    "PrefetchRelated",
    "QueryAnalyzer",
    "QueryOptimizer",
    "QueryResult",
    "ResourceInstances",
    "RolePermission",
    "SliceMetadata",
    "StringFilter",
    "UserLike",
    "camel_to_snake",
    "extract_global_ids_from_info",
    "fetch_and_check_permissions",
    "map_ids_to_models",
    "map_sqlalchemy_list_to_types",
    "map_sqlalchemy_to_type",
    "optimize_field",
    "build_recursive_dependency_tree",
    "merge_dependency_trees",
    "normalize_dependency_fields",
    "source_path_to_dependency_tree",
)

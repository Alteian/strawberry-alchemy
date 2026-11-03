from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class HasId(Protocol):
    id: UUID | str | int


@runtime_checkable
class IdentityLike(Protocol):
    """Minimal identity contract used by permissions and access filters (``id`` only)."""

    id: UUID | str | int


# NOTE: backwards compatibiltiy
@runtime_checkable
class UserLike(Protocol):
    id: UUID | str | int
    role: str


@runtime_checkable
class PermissionContextLike(Protocol):
    @property
    def current_user(self) -> UserLike | None: ...

    @property
    def identity(self) -> IdentityLike | None: ...


@runtime_checkable
class ModelRegistryLike(Protocol):
    def get_model(self, label: str) -> type[Any] | None: ...

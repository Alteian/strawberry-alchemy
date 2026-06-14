from abc import ABC, abstractmethod
from typing import Any


class BasePermissionResolver(ABC):
    @abstractmethod
    def resolve(
        self,
        operation: str,
        *,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Any]: ...

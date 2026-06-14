from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class ResourceInstances:
    _instances: dict[str, Any] = field(default_factory=dict)

    def add(self, key: str, instance: Any) -> None:
        self._instances[key] = instance

    def add_list(self, key: str, instances: list[Any]) -> None:
        self._instances[key] = instances

    def get(self, key: str) -> Any | None:
        return self._instances.get(key)

    def get_id(self, key: str) -> UUID | str | int | None:
        inst = self._instances.get(key)
        return getattr(inst, "id", None) if inst is not None else None

    def all(self) -> dict[str, Any]:
        return dict(self._instances)

    def __contains__(self, key: str) -> bool:
        return key in self._instances

    def __repr__(self) -> str:
        keys = ", ".join(self._instances.keys())
        return f"ResourceInstances({keys})"

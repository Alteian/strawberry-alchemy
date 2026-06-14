from typing import Any


class AccessControlMeta(type):
    def __init__(
        cls: "type[AccessControlFilter]",
        name: str,
        bases: tuple[type, ...],
        dct: dict[str, Any],
    ) -> None:
        if name != "AccessControlFilter" and not name.endswith("AccessFilter"):
            raise TypeError(f"Subclass {name} must end with 'AccessFilter'")
        super().__init__(name, bases, dct)


class AccessControlFilter(metaclass=AccessControlMeta):
    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        raise NotImplementedError("Subclasses must implement the apply_filter method")

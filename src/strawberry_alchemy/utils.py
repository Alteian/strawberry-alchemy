import re
from functools import lru_cache

_CAMEL_RE1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_RE2 = re.compile(r"([a-z0-9])([A-Z])")


@lru_cache(maxsize=512)
def _camel_str_to_snake(name: str) -> str:
    return _CAMEL_RE2.sub(r"\1_\2", _CAMEL_RE1.sub(r"\1_\2", name)).lower()


def camel_to_snake(data: str | dict) -> str | dict:
    if isinstance(data, str):
        return _camel_str_to_snake(data)
    if isinstance(data, dict):
        return {
            _camel_str_to_snake(key): (camel_to_snake(value) if isinstance(value, dict) else value)
            for key, value in data.items()
        }
    return data

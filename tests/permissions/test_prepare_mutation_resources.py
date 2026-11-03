from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from strawberry.relay import GlobalID

from strawberry_alchemy import IsAuthenticated, prepare_mutation_resources


class _Ctx:
    def __init__(self, user: object | None) -> None:
        self.current_user = user
        self.identity = user


class _Info:
    def __init__(self, user: object | None) -> None:
        self.context = _Ctx(user)


@pytest.mark.asyncio
async def test_prepare_mutation_resources_loads_and_checks() -> None:
    post_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    post = SimpleNamespace(id=post_id, user_id=user.id)

    async def load_post(value):  # noqa: ANN001
        assert value == post_id
        return post

    bag = await prepare_mutation_resources(
        _Info(user),  # type: ignore[arg-type]
        {"post_id": GlobalID(type_name="PostType", node_id=str(post_id))},
        loaders={"post_id": load_post},
        permissions=[IsAuthenticated()],
    )
    assert bag.get("post_id") is post


@pytest.mark.asyncio
async def test_prepare_mutation_resources_denies_anonymous() -> None:
    post_id = uuid4()

    async def load_post(value):  # noqa: ANN001
        return SimpleNamespace(id=value)

    with pytest.raises(PermissionError):
        await prepare_mutation_resources(
            _Info(None),  # type: ignore[arg-type]
            {"post_id": GlobalID(type_name="PostType", node_id=str(post_id))},
            loaders={"post_id": load_post},
            permissions=[IsAuthenticated()],
        )

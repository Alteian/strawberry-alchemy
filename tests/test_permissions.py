"""Tests for the permissions module."""

from __future__ import annotations

import pytest

from strawberry_alchemy.permissions import (
    BasePermissionResolver,
    IsAuthenticated,
    ObjectAccessPermission,
    OwnerPermission,
    ResourceInstances,
    RolePermission,
    extract_global_ids_from_info,
    fetch_and_check_permissions,
    map_ids_to_models,
)


class FakeUser:
    def __init__(self, *, id: str = "u1", role: str = "user"):  # noqa: A002
        self.id = id
        self.role = role


class FakeContext:
    def __init__(self, user: FakeUser | None = None):
        self._user = user

    @property
    def current_user(self):
        return self._user


class FakeInfo:
    """Minimal stand-in for ``strawberry.Info``."""

    def __init__(self, user: FakeUser | None = None):
        self.context = FakeContext(user)


class TestResourceInstances:
    def test_add_and_get(self):
        bag = ResourceInstances()
        bag.add("folder", {"id": "f1"})
        assert bag.get("folder") == {"id": "f1"}

    def test_contains(self):
        bag = ResourceInstances()
        bag.add("doc", object())
        assert "doc" in bag
        assert "other" not in bag

    def test_add_list(self):
        bag = ResourceInstances()
        bag.add_list("items", [1, 2, 3])
        assert bag.get("items") == [1, 2, 3]

    def test_all(self):
        bag = ResourceInstances()
        bag.add("a", 1)
        bag.add("b", 2)
        assert bag.all() == {"a": 1, "b": 2}

    def test_get_id(self):
        class Obj:
            id = "x1"

        bag = ResourceInstances()
        bag.add("obj", Obj())
        assert bag.get_id("obj") == "x1"
        assert bag.get_id("missing") is None

    def test_repr(self):
        bag = ResourceInstances()
        bag.add("a", 1)
        assert "a" in repr(bag)


class TestIsAuthenticated:
    def test_authenticated(self):
        perm = IsAuthenticated()
        info = FakeInfo(user=FakeUser())
        assert perm.has_permission(info) is True

    def test_unauthenticated(self):
        perm = IsAuthenticated()
        info = FakeInfo(user=None)
        assert perm.has_permission(info) is False


class TestRolePermission:
    def test_correct_role(self):
        perm = RolePermission(role="admin")
        info = FakeInfo(user=FakeUser(role="admin"))
        assert perm.has_permission(info) is True

    def test_wrong_role(self):
        perm = RolePermission(role="admin")
        info = FakeInfo(user=FakeUser(role="user"))
        assert perm.has_permission(info) is False

    def test_no_user(self):
        perm = RolePermission(role="admin")
        info = FakeInfo(user=None)
        assert perm.has_permission(info) is False


class TestOwnerPermission:
    def test_owner_matches(self):
        class Res:
            user_id = "u1"

        perm = OwnerPermission()
        bag = ResourceInstances()
        bag.add("res", Res())
        info = FakeInfo(user=FakeUser(id="u1"))
        assert perm.has_permission(info, resource_instances=bag) is True

    def test_owner_mismatch(self):
        class Res:
            user_id = "u2"

        perm = OwnerPermission()
        bag = ResourceInstances()
        bag.add("res", Res())
        info = FakeInfo(user=FakeUser(id="u1"))
        assert perm.has_permission(info, resource_instances=bag) is False

    def test_no_bag(self):
        perm = OwnerPermission()
        info = FakeInfo(user=FakeUser())
        assert perm.has_permission(info) is False

    def test_specific_resource_key(self):
        class Res:
            user_id = "u1"

        perm = OwnerPermission(resource_key="target")
        bag = ResourceInstances()
        bag.add("target", Res())
        info = FakeInfo(user=FakeUser(id="u1"))
        assert perm.has_permission(info, resource_instances=bag) is True


class TestObjectAccessPermission:
    def test_user_in_access_list(self):
        class Res:
            allowed_user_ids = ["u1", "u2"]

        perm = ObjectAccessPermission()
        bag = ResourceInstances()
        bag.add("doc", Res())
        info = FakeInfo(user=FakeUser(id="u1"))
        assert perm.has_permission(info, resource_instances=bag) is True

    def test_user_not_in_access_list(self):
        class Res:
            allowed_user_ids = ["u9"]

        perm = ObjectAccessPermission()
        bag = ResourceInstances()
        bag.add("doc", Res())
        info = FakeInfo(user=FakeUser(id="u1"))
        assert perm.has_permission(info, resource_instances=bag) is False

    def test_no_access_field(self):
        class Res:
            pass

        perm = ObjectAccessPermission()
        bag = ResourceInstances()
        bag.add("doc", Res())
        info = FakeInfo(user=FakeUser(id="u1"))
        assert perm.has_permission(info, resource_instances=bag) is False


class TestFetchAndCheckPermissions:
    @pytest.mark.asyncio
    async def test_all_pass(self):
        info = FakeInfo(user=FakeUser())
        await fetch_and_check_permissions(info, [IsAuthenticated()])

    @pytest.mark.asyncio
    async def test_failure_raises(self):
        info = FakeInfo(user=None)
        with pytest.raises(PermissionError, match="Authentication required"):
            await fetch_and_check_permissions(info, [IsAuthenticated()])


class TestExtractGlobalIds:
    def test_auto_detect_id_fields(self):
        data = {"folder_id": "raw-uuid", "name": "test"}
        result = extract_global_ids_from_info(data)
        assert "folder_id" in result
        assert "name" not in result

    def test_explicit_fields(self):
        data = {"custom": "val"}
        result = extract_global_ids_from_info(data, id_fields=["custom"])
        assert "custom" in result


class TestMapIdsToModels:
    @pytest.mark.asyncio
    async def test_maps_via_loader(self):
        class FakeInstance:
            id = "loaded"

        async def loader(id_val):
            return FakeInstance()

        bag = await map_ids_to_models({"folder_id": "some-uuid"}, {"folder_id": loader})
        assert bag.get("folder_id") is not None

    @pytest.mark.asyncio
    async def test_skips_none_ids(self):
        async def loader(id_val):
            raise AssertionError("should not be called")

        bag = await map_ids_to_models({"folder_id": None}, {"folder_id": loader})
        assert bag.get("folder_id") is None


class TestBasePermissionResolver:
    def test_abstract(self):
        with pytest.raises(TypeError):
            BasePermissionResolver()  # type: ignore[abstract]

    def test_concrete_subclass(self):
        class MyResolver(BasePermissionResolver):
            def resolve(self, operation, *, data=None, **kw):
                return [IsAuthenticated()]

        resolver = MyResolver()
        perms = resolver.resolve("test")
        assert len(perms) == 1
        assert isinstance(perms[0], IsAuthenticated)

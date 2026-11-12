from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import strawberry
from pydantic import BaseModel
from strawberry.relay import GlobalID

from strawberry_alchemy.schema.base import BaseSchema, schema_from_input


@strawberry.input
class NoteInput:
    id: GlobalID
    title: str | None = strawberry.UNSET
    parent_id: GlobalID | None = strawberry.UNSET
    extra_flag: bool | None = strawberry.UNSET


class CreateNoteSchema(BaseSchema):
    id: UUID | None = None
    title: str | None = None
    parent_id: UUID | None = None


class UpdateNoteSchema(BaseSchema):
    id: UUID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET
    parent_id: UUID | None = strawberry.UNSET


class PlainNoteModel(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    id: UUID
    title: str | None = None


def _gid(node_id: UUID | str, type_name: str = "NoteType") -> GlobalID:
    return GlobalID(type_name=type_name, node_id=str(node_id))


def test_from_input_required_global_id_becomes_uuid() -> None:
    note_id = uuid4()
    payload = NoteInput(id=_gid(note_id), title="hello")

    schema = CreateNoteSchema.from_input(payload)

    assert schema.id == note_id
    assert isinstance(schema.id, UUID)
    assert schema.title == "hello"


def test_from_input_omitted_optional_global_id_uses_model_defaults() -> None:
    note_id = uuid4()
    payload = NoteInput(id=_gid(note_id))

    created = CreateNoteSchema.from_input(payload)
    updated = UpdateNoteSchema.from_input(payload)

    assert created.parent_id is None
    assert "parent_id" not in created.model_dump(exclude_unset=True)

    assert updated.parent_id is strawberry.UNSET
    assert "parent_id" not in updated.model_dump(exclude_unset=True)


def test_from_input_optional_global_id_none_is_kept() -> None:
    note_id = uuid4()
    payload = NoteInput(id=_gid(note_id), parent_id=None)

    schema = UpdateNoteSchema.from_input(payload)

    assert schema.parent_id is None
    assert "parent_id" in schema.model_dump(exclude_unset=True)


def test_from_input_optional_global_id_provided_becomes_uuid() -> None:
    note_id = uuid4()
    parent_id = uuid4()
    payload = NoteInput(id=_gid(note_id), parent_id=_gid(parent_id))

    schema = UpdateNoteSchema.from_input(payload)

    assert schema.parent_id == parent_id
    assert isinstance(schema.parent_id, UUID)


def test_from_input_kwargs_win_and_decode_global_ids() -> None:
    note_id = uuid4()
    override_id = uuid4()
    actor_id = uuid4()
    payload = NoteInput(id=_gid(note_id), title="from-input")

    schema = CreateNoteSchema.from_input(
        payload,
        id=_gid(override_id),
        title="from-kwarg",
        parent_id=actor_id,
    )

    assert schema.id == override_id
    assert schema.title == "from-kwarg"
    assert schema.parent_id == actor_id


def test_from_input_ignores_fields_not_on_schema() -> None:
    note_id = uuid4()
    payload = NoteInput(id=_gid(note_id), title="x", extra_flag=True)

    schema = CreateNoteSchema.from_input(payload)

    assert schema.title == "x"
    assert not hasattr(schema, "extra_flag")


def test_from_input_invalid_global_id_and_non_uuid_node_id_raise() -> None:
    note_id = uuid4()
    payload = NoteInput(id=_gid(note_id))

    with pytest.raises(ValueError, match="Invalid GlobalID"):
        CreateNoteSchema.from_input(payload, parent_id=SimpleNamespace(node_id=None))

    with pytest.raises(ValueError, match="not a UUID"):
        CreateNoteSchema.from_input(payload, parent_id=_gid("not-a-uuid"))


def test_schema_from_input_works_for_plain_basemodel() -> None:
    note_id = uuid4()
    payload = NoteInput(id=_gid(note_id), title="plain")

    model = schema_from_input(PlainNoteModel, payload)

    assert isinstance(model, PlainNoteModel)
    assert model.id == note_id
    assert model.title == "plain"

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any, ClassVar
from uuid import UUID, uuid4

import strawberry
from pydantic import BaseModel

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.mapping.sqlalchemy_to_gql import UNSET
from strawberry_alchemy.schema.base import BaseSchema
from strawberry_alchemy.types.base_node import BaseNodeType


class _DummyModel:
    pass


class _DummyAccessFilter(AccessControlFilter):
    model_class = _DummyModel


class _ThreadSchema(BaseModel):
    id: UUID
    subject: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@strawberry.type
class ThreadType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = _DummyAccessFilter

    subject: str | None = None


class _AuthorSchema(BaseModel):
    id: UUID
    name: str


class _ChapterSchema(BaseModel):
    id: UUID
    title: str
    book: Any = None


class _BookSchema(BaseModel):
    id: UUID
    title: str
    author: _AuthorSchema | None = None
    chapters: list[_ChapterSchema] | None = None
    metadata: dict[str, object] | None = None


class AuthorSchema(BaseSchema):
    id: UUID
    name: str


class BookSchema(BaseSchema):
    id: UUID
    title: str
    author: AuthorSchema | None = None
    metadata: dict[str, object] | None = None


@strawberry.type
class AuthorType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = _DummyAccessFilter

    name: str | None = None


@strawberry.type
class ChapterType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = _DummyAccessFilter

    title: str | None = None
    book: Annotated[BookType, strawberry.lazy(__name__)] | None = None


@strawberry.type
class BookType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = _DummyAccessFilter

    title: str | None = None
    author: AuthorType | None = None
    chapters: list[ChapterType] | None = None
    metadata: dict | None = None


def test_from_schema_missing_audit_timestamps_become_none_not_unset() -> None:
    schema = _ThreadSchema(id=str(uuid4()), subject="hello")

    mapped = ThreadType.from_schema(schema)

    assert mapped.created_at is not UNSET
    assert mapped.created_at is None
    assert mapped.updated_at is not UNSET
    assert mapped.updated_at is None


def test_from_schema_explicit_unset_kwargs_become_none() -> None:
    schema = _ThreadSchema(
        id=str(uuid4()),
        subject="hello",
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )

    mapped = ThreadType.from_schema(
        schema,
        created_at=strawberry.UNSET,
        updated_at=strawberry.UNSET,
    )

    assert mapped.created_at is None
    assert mapped.updated_at is None


def test_from_schema_preserves_provided_timestamps() -> None:
    now = datetime.now(tz=UTC)
    schema = _ThreadSchema(
        id=str(uuid4()),
        subject="hello",
        created_at=now,
        updated_at=now,
    )

    mapped = ThreadType.from_schema(schema)

    assert mapped.created_at == now
    assert mapped.updated_at == now


def test_direct_constructor_normalizes_non_nullable_unset_date_field() -> None:
    @strawberry.type
    class BookingLike(BaseNodeType):
        access_filter: ClassVar[type[AccessControlFilter]] = _DummyAccessFilter

        check_in_date: date

    mapped = BookingLike(id=uuid4(), check_in_date=strawberry.UNSET)

    assert mapped.check_in_date is not UNSET
    assert mapped.check_in_date is None


def test_from_schema_converts_nested_to_one_schema() -> None:
    author = _AuthorSchema(id=uuid4(), name="Ada")
    book = _BookSchema(id=uuid4(), title="Notes", author=author)

    mapped = BookType.from_schema(book)

    assert isinstance(mapped.author, AuthorType)
    assert mapped.author.name == "Ada"
    assert mapped.author.id == author.id


def test_to_type_converts_nested_to_one_schema() -> None:
    author = AuthorSchema(id=uuid4(), name="Grace")
    book = BookSchema(id=uuid4(), title="Systems", author=author)

    mapped = book.to_type(BookType)

    assert isinstance(mapped.author, AuthorType)
    assert mapped.author.name == "Grace"


def test_from_schema_converts_nested_list_of_schemas() -> None:
    chapters = [
        _ChapterSchema(id=uuid4(), title="One"),
        _ChapterSchema(id=uuid4(), title="Two"),
    ]
    book = _BookSchema(id=uuid4(), title="Anthology", chapters=chapters)

    mapped = BookType.from_schema(book)

    assert mapped.chapters is not None
    assert len(mapped.chapters) == 2
    assert all(isinstance(chapter, ChapterType) for chapter in mapped.chapters)
    assert [chapter.title for chapter in mapped.chapters] == ["One", "Two"]


def test_from_schema_missing_and_none_nested_relation_become_none() -> None:
    without_author = _BookSchema(id=uuid4(), title="Solo")
    with_none_author = _BookSchema(id=uuid4(), title="Unset", author=None)

    mapped_missing = BookType.from_schema(without_author)
    mapped_none = BookType.from_schema(with_none_author)

    assert mapped_missing.author is None
    assert mapped_none.author is None
    assert not isinstance(mapped_missing.author, dict)
    assert not isinstance(mapped_none.author, dict)


def test_from_schema_converts_lazy_annotated_nested_field() -> None:
    book_schema = _BookSchema(id=uuid4(), title="Lazy Nest")
    chapter = _ChapterSchema(id=uuid4(), title="Intro", book=book_schema)

    mapped = ChapterType.from_schema(chapter)

    assert isinstance(mapped.book, BookType)
    assert mapped.book.title == "Lazy Nest"


def test_from_schema_kwarg_override_wins_and_exclude_skips() -> None:
    author = _AuthorSchema(id=uuid4(), name="FromSchema")
    book = _BookSchema(id=uuid4(), title="Overrides", author=author)
    override = AuthorType(id=uuid4(), name="FromKwarg")

    with_override = BookType.from_schema(book, author=override)
    with_exclude = BookType.from_schema(book, exclude={"author"})

    assert with_override.author is override
    assert with_override.author.name == "FromKwarg"
    assert with_exclude.author is None


def test_from_schema_cycle_does_not_stack_overflow() -> None:
    book = _BookSchema(id=uuid4(), title="Cycle", chapters=[])
    chapter = _ChapterSchema(id=uuid4(), title="Loop", book=book)
    book.chapters = [chapter]

    mapped = BookType.from_schema(book)

    assert mapped.chapters is not None
    assert len(mapped.chapters) == 1
    assert isinstance(mapped.chapters[0], ChapterType)
    assert mapped.chapters[0].title == "Loop"
    assert mapped.chapters[0].book is None


def test_from_schema_leaves_dict_scalar_fields_alone() -> None:
    meta = {"pages": 12, "tags": ["draft"]}
    book = _BookSchema(id=uuid4(), title="Meta", metadata=meta)

    mapped = BookType.from_schema(book)

    assert mapped.metadata == meta
    assert isinstance(mapped.metadata, dict)

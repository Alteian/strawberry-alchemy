import uuid
from collections.abc import Sequence
from typing import Any, ClassVar, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from strawberry import UNSET

from strawberry_alchemy.exceptions import NotFoundError
from strawberry_alchemy.schema.base import BaseSchema

from .deletion import BaseDeletionHandler


class BaseRepository[
    ModelT,
    SchemaT: BaseSchema = BaseSchema,
    DeletionHandlerT: BaseDeletionHandler = BaseDeletionHandler,
]:
    relation_models: ClassVar[dict[str, type[Any]]] = {}

    def __init__(
        self,
        session: AsyncSession,
        model_cls: type[ModelT],
        schema_cls: type[SchemaT],
        *,
        deletion_handler: DeletionHandlerT | None = None,
    ) -> None:
        self.session = session
        self.model_cls = model_cls
        self.schema_cls = schema_cls
        self.deletion_handler = deletion_handler

    @property
    def _model_id_attr(self) -> Any:
        return cast("Any", self.model_cls).id

    async def get_by_id(self, id: uuid.UUID, options: Sequence[Any] | None = None) -> SchemaT:
        stmt = select(self.model_cls).where(self._model_id_attr == id)
        if options:
            stmt = stmt.options(*options)

        result = await self.session.execute(stmt)
        db_obj = result.scalar_one_or_none()
        if db_obj is None:
            raise NotFoundError(f"{self.model_cls.__name__}: {id}")

        return self.schema_cls.model_validate(db_obj)

    async def get_by_ids(
        self,
        ids: Sequence[uuid.UUID],
        options: Sequence[Any] | None = None,
    ) -> list[SchemaT]:
        stmt = select(self.model_cls).where(self._model_id_attr.in_(ids))
        if options:
            stmt = stmt.options(*options)

        result = await self.session.execute(stmt)
        db_objs = result.scalars().all()
        return [self.schema_cls.model_validate(obj) for obj in db_objs]

    async def _process_relations(self, db_obj: ModelT, schema: SchemaT, is_persistent: bool = False) -> None:
        for rel_name, rel_model in self.relation_models.items():
            rel_data = getattr(schema, rel_name, UNSET)
            if rel_data is UNSET or rel_data is None:
                continue

            if is_persistent:
                await self.session.refresh(db_obj, attribute_names=[rel_name])

            if isinstance(rel_data, list):
                items_with_ids: dict[Any, Any] = {}
                new_items: list[Any] = []

                for item in rel_data:
                    item_id = getattr(item, "id", UNSET)
                    if item_id is not UNSET and item_id is not None:
                        items_with_ids[item_id] = item
                    else:
                        new_items.append(rel_model(**item.dump_for_db(exclude={"id", "created_at"})))

                loaded: list[Any] = []
                if items_with_ids:
                    stmt = select(rel_model).where(rel_model.id.in_(items_with_ids.keys()))
                    loaded = list((await self.session.execute(stmt)).scalars().all())

                    found_ids = {obj.id for obj in loaded}
                    for item_id, item in items_with_ids.items():
                        if item_id not in found_ids:
                            new_items.append(rel_model(**item.dump_for_db()))

                    if is_persistent:
                        for obj in loaded:
                            schema_item = items_with_ids.get(obj.id)
                            if schema_item is not None:
                                for key, value in schema_item.dump_for_db(exclude={"id", "created_at"}).items():
                                    setattr(obj, key, value)

                setattr(db_obj, rel_name, loaded + new_items)
            else:
                if is_persistent:
                    existing_rel = getattr(db_obj, rel_name, None)
                    if existing_rel is not None:
                        for key, value in rel_data.dump_for_db(exclude={"id", "created_at"}).items():
                            setattr(existing_rel, key, value)
                    else:
                        setattr(db_obj, rel_name, rel_model(**rel_data.dump_for_db(exclude={"id", "created_at"})))
                else:
                    setattr(db_obj, rel_name, rel_model(**rel_data.dump_for_db(exclude={"id", "created_at"})))

    async def create(self, schema: SchemaT, should_commit: bool = True) -> SchemaT:
        try:
            db_obj = self.model_cls(**schema.dump_for_db(exclude=set(self.relation_models.keys())))
            await self._process_relations(db_obj, schema)
            self.session.add(db_obj)
            await self.session.flush()

            result = self.schema_cls.model_validate(db_obj)
            if should_commit:
                await self.session.commit()
            return result
        except IntegrityError as e:
            await self.session.rollback()
            raise ValueError(f"Integrity Error creating {self.model_cls.__name__}: {e}") from e

    async def update(
        self,
        schema: SchemaT,
        should_commit: bool = True,
        instance: ModelT | None = None,
    ) -> SchemaT:
        try:
            target_id = getattr(schema, "id", None)
            if instance is None:
                stmt = select(self.model_cls).where(self._model_id_attr == target_id)
                db_obj = (await self.session.execute(stmt)).scalar_one_or_none()
            else:
                db_obj = await self.session.merge(instance)

            if db_obj is None:
                raise NotFoundError(f"{self.model_cls.__name__}: {target_id} not found")

            for key, value in schema.dump_for_db(
                exclude={"id", "created_at"} | set(self.relation_models.keys())
            ).items():
                setattr(db_obj, key, value)

            await self._process_relations(db_obj, schema, is_persistent=True)

            result = self.schema_cls.model_validate(db_obj)
            if should_commit:
                await self.session.commit()
            return result
        except IntegrityError as e:
            await self.session.rollback()
            raise ValueError(
                f"Invalid data for {self.model_cls.__name__}: {getattr(schema, 'id', '?')}. Error: {e}"
            ) from e

    async def delete(self, id: uuid.UUID, should_commit: bool = True, instance: ModelT | None = None) -> None:
        db_obj = (
            await self.session.merge(instance)
            if instance
            else (
                await self.session.execute(select(self.model_cls).where(self._model_id_attr == id))
            ).scalar_one_or_none()
        )
        if db_obj is None:
            raise NotFoundError(f"{self.model_cls.__name__}: {id}")

        handler = self.deletion_handler
        dependents: dict[str, list[uuid.UUID]] = {}

        if handler:
            dependents = await handler.collect_dependents(self.session, id, db_obj)
            await handler.pre_delete(self.session, id, db_obj, dependents)
            await handler.cleanup_external(self.session, id, db_obj, dependents)
            await handler.handle_cascade(self.session, id, dependents)

        await self.session.delete(db_obj)

        if handler:
            await handler.post_delete(self.session, id, dependents)

        if should_commit:
            await self.session.commit()

    async def add_related(
        self,
        id: uuid.UUID,
        relation_name: str,
        related_ids: list[uuid.UUID],
        should_commit: bool = True,
    ) -> SchemaT:
        if relation_name not in self.relation_models:
            raise ValueError(
                f"Relation '{relation_name}' is not configured in {self.__class__.__name__}.relation_models"
            )
        related_model = self.relation_models[relation_name]
        stmt = (
            select(self.model_cls)
            .options(selectinload(getattr(self.model_cls, relation_name)))
            .where(self._model_id_attr == id)
        )
        parent_obj = (await self.session.execute(stmt)).scalar_one_or_none()

        if parent_obj is None:
            raise NotFoundError(f"{self.model_cls.__name__}: {id}")

        rel_stmt = select(related_model).where(related_model.id.in_(related_ids))
        related_items = (await self.session.execute(rel_stmt)).scalars().all()
        if related_items:
            collection = getattr(parent_obj, relation_name)
            existing_ids = {item.id for item in collection}
            new_items = [item for item in related_items if item.id not in existing_ids]
            collection.extend(new_items)

        result = self.schema_cls.model_validate(parent_obj)
        if should_commit:
            await self.session.commit()
        return result

    async def remove_related(
        self,
        id: uuid.UUID,
        relation_name: str,
        related_ids: list[uuid.UUID],
        should_commit: bool = True,
    ) -> SchemaT:
        if relation_name not in self.relation_models:
            raise ValueError(
                f"Relation '{relation_name}' is not configured in {self.__class__.__name__}.relation_models"
            )
        stmt = (
            select(self.model_cls)
            .options(selectinload(getattr(self.model_cls, relation_name)))
            .where(self._model_id_attr == id)
        )
        parent_obj = (await self.session.execute(stmt)).scalar_one_or_none()

        if parent_obj is None:
            raise NotFoundError(f"{self.model_cls.__name__}: {id}")

        collection = getattr(parent_obj, relation_name)
        target_ids = set(related_ids)
        setattr(parent_obj, relation_name, [item for item in collection if item.id not in target_ids])

        result = self.schema_cls.model_validate(parent_obj)
        if should_commit:
            await self.session.commit()
        return result

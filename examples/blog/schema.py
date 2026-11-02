from __future__ import annotations

import strawberry

from .mutations import Mutation
from .queries import Query

schema = strawberry.Schema(query=Query, mutation=Mutation)

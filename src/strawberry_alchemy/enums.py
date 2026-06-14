from enum import Enum

import strawberry


@strawberry.enum
class Ordering(Enum):
    ASC = "ASC"
    DESC = "DESC"

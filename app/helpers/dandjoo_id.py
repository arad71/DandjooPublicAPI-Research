import datetime
import random
from typing import Any, ClassVar


class DandjooId:
    """
    This class has been partially copied from DandjooCuration so submission can generate "persistent ids" in the same
    format Curation would, for unmappable survey submission.
    """
    DANDJOO_ID_VALUE_LENGTH: ClassVar[int] = 16
    value: str

    @classmethod
    def map_to_char(cls, num):
        "Maps any number in the range 0-61 to a single character. Good for date/time elements"
        # This string defines the allowable characters in an ID, and it MUST be at least 60 chars long.
        DANDJOO_ID_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz1234567890"
        return DANDJOO_ID_CHARS[num]

    @classmethod
    def new_id(cls):
        now = datetime.datetime.now()
        return "%d%c%c%c%c%c%0.5x%0.2x" % (now.year, DandjooId.map_to_char(now.month), DandjooId.map_to_char(now.day),
                                           DandjooId.map_to_char(now.hour), DandjooId.map_to_char(now.minute),
                                           DandjooId.map_to_char(now.second), now.microsecond, random.getrandbits(8))

    @classmethod
    def is_valid(cls, v: Any) -> bool:
        if isinstance(v, DandjooId) and len(v.value) == DandjooId.DANDJOO_ID_VALUE_LENGTH:
            return True
        elif isinstance(v, str) and len(v) == DandjooId.DANDJOO_ID_VALUE_LENGTH:
            return True
        return False

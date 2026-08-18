import re

from app.helpers.dandjoo_id import DandjooId


def test_new_dandjoo_id():
    new_id = DandjooId.new_id()

    assert isinstance(new_id, str)
    assert len(new_id) == 16
    assert re.fullmatch(r"2[0-9]{3}[A-Za-z0-9]{5}[0-9a-f]{7}", new_id) is not None

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
import json
import pytest

from app.audit.canonical import canonicalize, canonicalize_datetime
from app.audit.errors import AuditCanonicalizationError
from pydantic import BaseModel


class SampleEnum(str, Enum):
    ALPHA = "ALPHA"
    BETA = "BETA"


class SampleModel(BaseModel):
    name: str
    amount: Decimal
    status: SampleEnum


def test_canonicalize_datetime_microsecond_precision():
    dt = datetime(2026, 8, 18, 18, 46, 12, 123456, tzinfo=timezone.utc)
    res = canonicalize_datetime(dt)
    assert res == "2026-08-18T18:46:12.123456+00:00"


def test_canonicalize_datetime_zero_microsecond_precision():
    dt = datetime(2026, 8, 18, 18, 46, 12, 0, tzinfo=timezone.utc)
    res = canonicalize_datetime(dt)
    assert res == "2026-08-18T18:46:12.000000+00:00"


def test_canonicalize_datetime_tz_conversion():
    tz_east = timezone(timedelta(hours=5))
    dt = datetime(2026, 8, 18, 23, 46, 12, 500000, tzinfo=tz_east)
    res = canonicalize_datetime(dt)
    assert res == "2026-08-18T18:46:12.500000+00:00"


def test_canonicalize_deterministic_key_sorting():
    dict_a = {"b": 2, "a": 1, "c": {"y": 20, "x": 10}}
    dict_b = {"a": 1, "c": {"x": 10, "y": 20}, "b": 2}
    bytes_a = canonicalize(dict_a)
    bytes_b = canonicalize(dict_b)
    assert bytes_a == bytes_b
    assert bytes_a.decode("utf-8") == '{"a":1,"b":2,"c":{"x":10,"y":20}}'


def test_canonicalize_decimal_representation():
    payload = {"price": Decimal("100.50"), "qty": Decimal("2.000")}
    res = canonicalize(payload).decode("utf-8")
    assert res == '{"price":"100.50","qty":"2.000"}'


def test_canonicalize_pydantic_model():
    model = SampleModel(name="Test", amount=Decimal("50.25"), status=SampleEnum.ALPHA)
    res = canonicalize(model).decode("utf-8")
    assert res == '{"amount":"50.25","name":"Test","status":"ALPHA"}'


def test_canonicalize_float_conversion():
    res = canonicalize({"value": 12.34}).decode("utf-8")
    assert res == '{"value":"12.34"}'

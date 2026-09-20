from unittest.mock import Mock

import pytest

from energy_server.redis_store import PointConflictError, RedisStoreDriftError, RedisTimeSeriesStore


def test_get_points_in_range_applies_limit_in_redis_call():
    store = RedisTimeSeriesStore()
    store.r = Mock()
    store.r.zrangebyscore.return_value = ["1000", "2000"]
    store.r.hmget.return_value = ["10.5", "20.5"]

    points = store.get_points_in_range("meter-1", "power", 0, 3000, limit=2)

    store.r.zrangebyscore.assert_called_once_with(
        "energy:ts:meter-1:power",
        0,
        3000,
        start=0,
        num=2,
    )
    store.r.hmget.assert_called_once_with(
        "energy:val:meter-1:power",
        ["1000", "2000"],
    )
    assert points == [(1000, 10.5), (2000, 20.5)]


def test_create_point_if_absent_writes_when_missing():
    store = RedisTimeSeriesStore()
    store.r = Mock()

    presence_pipe = Mock()
    presence_pipe.execute.return_value = [False, None, None]
    store.r.pipeline.return_value = presence_pipe

    store.overwrite_point = Mock()
    store.create_point_if_absent("meter-1", "power", 1000, 10.5)

    store.overwrite_point.assert_called_once_with("meter-1", "power", 1000, 10.5)


def test_create_point_if_absent_accepts_existing_same_value():
    store = RedisTimeSeriesStore()
    store.r = Mock()

    presence_pipe = Mock()
    presence_pipe.execute.return_value = [True, 1000.0, "10.5"]
    store.r.pipeline.return_value = presence_pipe

    store.set_point = Mock()
    store.create_point_if_absent("meter-1", "power", 1000, 10.5)

    store.set_point.assert_not_called()


def test_create_point_if_absent_raises_on_existing_different_value():
    store = RedisTimeSeriesStore()
    store.r = Mock()

    presence_pipe = Mock()
    presence_pipe.execute.return_value = [True, 1000.0, "10.5"]
    store.r.pipeline.return_value = presence_pipe

    with pytest.raises(PointConflictError, match="different value"):
        store.create_point_if_absent("meter-1", "power", 1000, 11.0)


def test_get_points_in_range_without_limit_uses_full_redis_range():
    store = RedisTimeSeriesStore()
    store.r = Mock()
    store.r.zrangebyscore.return_value = ["1000", "2000", "3000"]
    store.r.hmget.return_value = ["10.5", "20.5", "30.5"]

    points = store.get_points_in_range("meter-1", "power", 0, 3000)

    store.r.zrangebyscore.assert_called_once_with("energy:ts:meter-1:power", 0, 3000)
    assert points == [(1000, 10.5), (2000, 20.5), (3000, 30.5)]


def test_get_points_in_range_negative_limit_uses_full_redis_range():
    store = RedisTimeSeriesStore()
    store.r = Mock()
    store.r.zrangebyscore.return_value = ["1000", "2000", "3000"]
    store.r.hmget.return_value = ["10.5", "20.5", "30.5"]

    points = store.get_points_in_range("meter-1", "power", 0, 3000, limit=-2)

    store.r.zrangebyscore.assert_called_once_with("energy:ts:meter-1:power", 0, 3000)
    assert points == [(1000, 10.5), (2000, 20.5), (3000, 30.5)]


def test_get_points_in_range_raises_when_hash_value_is_missing():
    store = RedisTimeSeriesStore()
    store.r = Mock()
    store.r.zrangebyscore.return_value = ["1000"]
    store.r.hmget.return_value = [None]

    with pytest.raises(RedisStoreDriftError, match="Point value drift"):
        store.get_points_in_range("meter-1", "power", 0, 3000)


def test_point_exists_raises_when_hash_and_sorted_set_drift():
    store = RedisTimeSeriesStore()
    store.r = Mock()
    presence_pipe = Mock()
    presence_pipe.execute.return_value = [True, None]
    store.r.pipeline.return_value = presence_pipe

    with pytest.raises(RedisStoreDriftError, match="Point presence drift"):
        store.point_exists("meter-1", "power", 1000)


def test_delete_existing_point_returns_false_when_point_is_missing():
    store = RedisTimeSeriesStore()
    store.r = Mock()
    presence_pipe = Mock()
    presence_pipe.execute.return_value = [False, None]
    store.r.pipeline.return_value = presence_pipe

    assert store.delete_existing_point("meter-1", "power", 1000) is False


def test_delete_existing_point_raises_when_delete_counts_drift():
    store = RedisTimeSeriesStore()
    store.r = Mock()

    presence_pipe = Mock()
    presence_pipe.execute.return_value = [True, 1000.0]
    delete_pipe = Mock()
    delete_pipe.execute.return_value = [1, 0]
    store.r.pipeline.side_effect = [presence_pipe, delete_pipe]

    with pytest.raises(RedisStoreDriftError, match="Point delete drift"):
        store.delete_existing_point("meter-1", "power", 1000)

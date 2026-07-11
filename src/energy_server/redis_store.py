import redis

from .config import REDIS_HOST, REDIS_PORT


class RedisStoreDriftError(RuntimeError):
    """Raised when Redis index and value structures disagree for the same point."""


class RedisTimeSeriesStore:
    def __init__(self) -> None:
        self.r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    def _zkey(self, meter_id: str, stream: str) -> str:
        return f"energy:ts:{meter_id}:{stream}"

    def _hkey(self, meter_id: str, stream: str) -> str:
        return f"energy:val:{meter_id}:{stream}"

    def set_point(self, meter_id: str, stream: str, ts_ms: int, value: float) -> None:
        zkey = self._zkey(meter_id, stream)
        hkey = self._hkey(meter_id, stream)
        ts_field = str(ts_ms)
        pipe = self.r.pipeline()
        pipe.zadd(zkey, {ts_field: ts_ms})
        pipe.hset(hkey, ts_field, str(value))
        pipe.execute()

    def get_point(self, meter_id: str, stream: str, ts_ms: int) -> float | None:
        hkey = self._hkey(meter_id, stream)
        v = self.r.hget(hkey, str(ts_ms))
        if v is None:
            return None
        return float(v)

    def _point_presence(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        zkey = self._zkey(meter_id, stream)
        hkey = self._hkey(meter_id, stream)
        ts_field = str(ts_ms)
        pipe = self.r.pipeline()
        pipe.hexists(hkey, ts_field)
        pipe.zscore(zkey, ts_field)
        hash_exists, sorted_score = pipe.execute()
        sorted_exists = sorted_score is not None

        if hash_exists != sorted_exists:
            raise RedisStoreDriftError(
                f"Point presence drift for meter_id={meter_id!r}, stream={stream!r}, timestamp_ms={ts_ms}: "
                f"hash_exists={hash_exists}, sorted_set_exists={sorted_exists}"
            )

        return hash_exists

    def exists_point(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        return self._point_presence(meter_id, stream, ts_ms)

    def delete_point(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        if not self._point_presence(meter_id, stream, ts_ms):
            return False

        zkey = self._zkey(meter_id, stream)
        hkey = self._hkey(meter_id, stream)
        ts_field = str(ts_ms)
        pipe = self.r.pipeline()
        pipe.zrem(zkey, ts_field)
        pipe.hdel(hkey, ts_field)
        zrem_count, hdel_count = pipe.execute()

        if zrem_count != 1 or hdel_count != 1:
            raise RedisStoreDriftError(
                f"Point delete drift for meter_id={meter_id!r}, stream={stream!r}, timestamp_ms={ts_ms}: "
                f"zrem_count={zrem_count}, hdel_count={hdel_count}"
            )

        return True

    def query_range(
        self,
        meter_id: str,
        stream: str,
        start_ms: int,
        end_ms: int,
        limit: int = 0,
    ) -> list[tuple[int, float]]:
        zkey = self._zkey(meter_id, stream)
        hkey = self._hkey(meter_id, stream)

        zrange_kwargs: dict[str, int] = {}
        if limit > 0:
            zrange_kwargs = {"start": 0, "num": limit}

        ts_fields = self.r.zrangebyscore(zkey, start_ms, end_ms, **zrange_kwargs)

        if not ts_fields:
            return []

        values = self.r.hmget(hkey, ts_fields)
        points = []
        for ts_str, v in zip(ts_fields, values):
            if v is None:
                continue
            points.append((int(ts_str), float(v)))
        return points
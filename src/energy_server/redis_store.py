import redis
from config import REDIS_HOST, REDIS_PORT

class RedisTimeSeriesStore:
    def __init__(self):
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

    def get_point(self, meter_id: str, stream: str, ts_ms: int):
        hkey = self._hkey(meter_id, stream)
        v = self.r.hget(hkey, str(ts_ms))
        if v is None:
            return None
        return float(v)

    def exists_point(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        hkey = self._hkey(meter_id, stream)
        return self.r.hexists(hkey, str(ts_ms))

    def delete_point(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        zkey = self._zkey(meter_id, stream)
        hkey = self._hkey(meter_id, stream)
        ts_field = str(ts_ms)
        pipe = self.r.pipeline()
        pipe.zrem(zkey, ts_field)
        pipe.hdel(hkey, ts_field)
        zrem_count, hdel_count = pipe.execute()
        return (zrem_count > 0) or (hdel_count > 0)

    def query_range(self, meter_id: str, stream: str, start_ms: int, end_ms: int, limit: int = 0):
        zkey = self._zkey(meter_id, stream)
        hkey = self._hkey(meter_id, stream)

        ts_fields = self.r.zrangebyscore(zkey, start_ms, end_ms)
        if limit and limit > 0:
            ts_fields = ts_fields[:limit]

        if not ts_fields:
            return []

        values = self.r.hmget(hkey, ts_fields)
        points = []
        for ts_str, v in zip(ts_fields, values):
            if v is None:
                continue
            points.append((int(ts_str), float(v)))
        return points
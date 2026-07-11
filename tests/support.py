from energy_server.generated import energy_pb2


class FakeRedisStore:
    """In-memory fake for RedisTimeSeriesStore."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str, int], float] = {}

    def _key(self, meter_id: str, stream: str, ts_ms: int) -> tuple[str, str, int]:
        return meter_id, stream, ts_ms

    def set_point(self, meter_id: str, stream: str, ts_ms: int, value: float) -> None:
        self.data[self._key(meter_id, stream, ts_ms)] = float(value)

    def get_point(self, meter_id: str, stream: str, ts_ms: int) -> float | None:
        return self.data.get(self._key(meter_id, stream, ts_ms))

    def exists_point(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        return self._key(meter_id, stream, ts_ms) in self.data

    def delete_point(self, meter_id: str, stream: str, ts_ms: int) -> bool:
        return self.data.pop(self._key(meter_id, stream, ts_ms), None) is not None

    def query_range(
        self,
        meter_id: str,
        stream: str,
        start_ms: int,
        end_ms: int,
        limit: int = 0,
    ) -> list[tuple[int, float]]:
        points = []
        for (m_id, s, ts), value in self.data.items():
            if m_id == meter_id and s == stream and start_ms <= ts <= end_ms:
                points.append((ts, value))
        points.sort(key=lambda item: item[0])
        if limit > 0:
            points = points[:limit]
        return points


def make_entry(
    meter_id: str = "m-1",
    stream: str = "power",
    timestamp_ms: int = 1000,
    value: float = 12.5,
) -> energy_pb2.Entry:
    return energy_pb2.Entry(
        key=energy_pb2.EntryKey(
            meter_id=meter_id,
            stream=stream,
            timestamp_ms=timestamp_ms,
        ),
        value=value,
    )


def make_key(
    meter_id: str = "m-1",
    stream: str = "power",
    timestamp_ms: int = 1000,
) -> energy_pb2.EntryKey:
    return energy_pb2.EntryKey(
        meter_id=meter_id,
        stream=stream,
        timestamp_ms=timestamp_ms,
    )

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

_GEN_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _GEN_PARENT not in sys.path:
    sys.path.insert(0, _GEN_PARENT)

from generated import energy_pb2, energy_pb2_grpc  # noqa: E402


def _dt_to_timestamp(dt: datetime) -> Timestamp:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def _dt_to_millis(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


class EnergyClient:
    def __init__(self, host: str = "localhost", port: int = 50051) -> None:
        self._channel = grpc.insecure_channel(f"{host}:{port}")
        self._stub = energy_pb2_grpc.EnergyStoreStub(self._channel)

    def __enter__(self) -> "EnergyClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._channel.close()

    def set_entry(self, meter_id: str, stream: str, dt: datetime, value: float) -> tuple[bool, str]:
        request = energy_pb2.SetEntryRequest(
            entry=energy_pb2.Entry(
                key=energy_pb2.EntryKey(
                    meter_id=meter_id,
                    stream=stream,
                    timestamp_ms=_dt_to_timestamp(dt),
                ),
                value=value,
            )
        )
        reply = self._stub.SetEntry(request)
        return reply.ok, reply.message

    def get_entry(self, meter_id: str, stream: str, dt: datetime) -> tuple[bool, float | None]:
        request = energy_pb2.GetEntryRequest(
            key=energy_pb2.EntryKey(
                meter_id=meter_id,
                stream=stream,
                timestamp_ms=_dt_to_timestamp(dt),
            )
        )
        reply = self._stub.GetEntry(request)
        if not reply.found:
            return False, None
        return True, reply.entry.value

    def update_entry(self, meter_id: str, stream: str, dt: datetime, value: float) -> tuple[bool, str]:
        request = energy_pb2.UpdateEntryRequest(
            entry=energy_pb2.Entry(
                key=energy_pb2.EntryKey(
                    meter_id=meter_id,
                    stream=stream,
                    timestamp_ms=_dt_to_timestamp(dt),
                ),
                value=value,
            )
        )
        reply = self._stub.UpdateEntry(request)
        return reply.ok, reply.message

    def delete_entry(self, meter_id: str, stream: str, dt: datetime) -> tuple[bool, str]:
        request = energy_pb2.DeleteEntryRequest(
            key=energy_pb2.EntryKey(
                meter_id=meter_id,
                stream=stream,
                timestamp_ms=_dt_to_timestamp(dt),
            )
        )
        reply = self._stub.DeleteEntry(request)
        return reply.ok, reply.message

    def query_range(
        self,
        meter_id: str,
        stream: str,
        start_dt: datetime,
        end_dt: datetime,
        limit: int = 0,
    ) -> list[tuple[int, float]]:
        request = energy_pb2.QueryRangeRequest(
            meter_id=meter_id,
            stream=stream,
            start_ms=_dt_to_millis(start_dt),
            end_ms=_dt_to_millis(end_dt),
            limit=limit,
        )
        reply = self._stub.QueryRange(request)
        return [(pt.timestamp_ms, pt.value) for pt in reply.points]

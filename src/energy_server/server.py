import argparse
from concurrent import futures
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Callable, Protocol, TypeAlias

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from .config import GRPC_PORT
from .generated import energy_pb2, energy_pb2_grpc
from .redis_store import PointConflictError, RedisTimeSeriesStore

Point: TypeAlias = tuple[int, float]
OutFn = Callable[[str], Any]
DEFAULT_MAX_WORKERS = 10


class TimeSeriesStore(Protocol):
    def set_point(self, meter_id: str, stream: str, ts_ms: int, value: float) -> None: ...

    def set_point_idempotent(self, meter_id: str, stream: str, ts_ms: int, value: float) -> None: ...

    def get_point(self, meter_id: str, stream: str, ts_ms: int) -> float | None: ...

    def exists_point(self, meter_id: str, stream: str, ts_ms: int) -> bool: ...

    def delete_point(self, meter_id: str, stream: str, ts_ms: int) -> bool: ...

    def query_range(
        self,
        meter_id: str,
        stream: str,
        start_ms: int,
        end_ms: int,
        limit: int = 0,
    ) -> list[Point]: ...

try:
    APP_VERSION = version("energy-grpc-timeseries")
except PackageNotFoundError:
    APP_VERSION = "dev"


def _timestamp_to_milliseconds(timestamp: Timestamp) -> int:
    return timestamp.seconds * 1_000 + timestamp.nanos // 1_000_000


def _timestamp_from_milliseconds(timestamp_ms: int) -> Timestamp:
    seconds, milliseconds = divmod(timestamp_ms, 1_000)
    return Timestamp(seconds=seconds, nanos=milliseconds * 1_000_000)


def _build_entry(meter_id: str, stream: str, timestamp_ms: int, value: float) -> energy_pb2.Entry:
    return energy_pb2.Entry(
        key=energy_pb2.EntryKey(
            meter_id=meter_id,
            stream=stream,
            timestamp_ms=_timestamp_from_milliseconds(timestamp_ms),
        ),
        value=value,
    )


def _default_grpc_server_factory() -> grpc.Server:
    return grpc.server(futures.ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS))


class EnergyStoreServicer(energy_pb2_grpc.EnergyStoreServicer):
    def __init__(self, store: TimeSeriesStore | None = None) -> None:
        self.store: TimeSeriesStore = store or RedisTimeSeriesStore()

    def GetVersion(self, request: Any, context: Any) -> energy_pb2.VersionReply:
        del request, context
        return energy_pb2.VersionReply(version=APP_VERSION)

    def SetEntry(self, request: Any, context: Any) -> energy_pb2.StatusReply:
        del context
        e = request.entry
        k = e.key
        timestamp_ms = _timestamp_to_milliseconds(k.timestamp_ms)
        try:
            self.store.set_point_idempotent(k.meter_id, k.stream, timestamp_ms, e.value)
        except PointConflictError:
            return energy_pb2.StatusReply(ok=False, message="conflict")

        return energy_pb2.StatusReply(ok=True, message="set")

    def GetEntry(self, request: Any, context: Any) -> energy_pb2.GetEntryReply:
        del context
        k = request.key
        timestamp_ms = _timestamp_to_milliseconds(k.timestamp_ms)
        v = self.store.get_point(k.meter_id, k.stream, timestamp_ms)
        if v is None:
            return energy_pb2.GetEntryReply(found=False)
        entry = _build_entry(k.meter_id, k.stream, timestamp_ms, v)
        return energy_pb2.GetEntryReply(found=True, entry=entry)

    def UpdateEntry(self, request: Any, context: Any) -> energy_pb2.StatusReply:
        del context
        e = request.entry
        k = e.key
        timestamp_ms = _timestamp_to_milliseconds(k.timestamp_ms)
        if not self.store.exists_point(k.meter_id, k.stream, timestamp_ms):
            return energy_pb2.StatusReply(ok=False, message="not_found")
        self.store.set_point(k.meter_id, k.stream, timestamp_ms, e.value)

        return energy_pb2.StatusReply(ok=True, message="updated")

    def DeleteEntry(self, request: Any, context: Any) -> energy_pb2.StatusReply:
        del context
        k = request.key
        timestamp_ms = _timestamp_to_milliseconds(k.timestamp_ms)
        ok = self.store.delete_point(k.meter_id, k.stream, timestamp_ms)
        return energy_pb2.StatusReply(ok=ok, message="deleted" if ok else "not_found")

    def QueryRange(self, request: Any, context: Any) -> energy_pb2.QueryRangeReply:
        del context
        pts = self.store.query_range(
            request.meter_id,
            request.stream,
            request.start_ms,
            request.end_ms,
            request.limit,
        )
        return energy_pb2.QueryRangeReply(
            points=[energy_pb2.QueryPoint(timestamp_ms=ts, value=val) for ts, val in pts]
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="store_true")
    return parser


def serve(
    args: argparse.Namespace | None = None,
    grpc_server_factory: Callable[[], grpc.Server] | None = None,
    register_servicer: Callable[[EnergyStoreServicer, grpc.Server], None] | None = None,
    servicer_factory: Callable[[], EnergyStoreServicer] | None = None,
    port: int | None = None,
    out: OutFn = print,
) -> None:

    args = args or build_parser().parse_args()
    grpc_server_factory = grpc_server_factory or _default_grpc_server_factory
    register_servicer = register_servicer or energy_pb2_grpc.add_EnergyStoreServicer_to_server
    servicer_factory = servicer_factory or EnergyStoreServicer
    port = port if port is not None else GRPC_PORT

    if args.version:
        out(APP_VERSION)
        return

    grpc_server = grpc_server_factory()
    servicer = servicer_factory()
    register_servicer(servicer, grpc_server)
    grpc_server.add_insecure_port(f"[::]:{port}")
    grpc_server.start()
    out(f"gRPC EnergyStore running on port {port}")
    grpc_server.wait_for_termination()

import argparse
from concurrent import futures
from datetime import UTC, datetime
import sys
from typing import Any, Callable, Protocol, TypeAlias
from zoneinfo import ZoneInfo

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf import empty_pb2

from . import __version__
from .config import GRPC_PORT
from .generated import energy_pb2, energy_pb2_grpc
from .redis_store import PointConflictError, RedisTimeSeriesStore

Point: TypeAlias = tuple[int, float]
OutFn = Callable[[str], Any]
DEFAULT_MAX_WORKERS = 10


class TimeSeriesStore(Protocol):
    def set_point(self, meter_id: str, stream: str, ts_ms: int, value: float) -> None: ...

    def set_point_idempotent(self, meter_id: str, stream: str, ts_ms: int, value: float) -> None: ...

    def get_point(self, meter_id: str, stream: str, ts_ms: int) -> float: ...

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

APP_VERSION = __version__
NETHERLANDS_TZ = ZoneInfo("Europe/Amsterdam")


def _timestamp_to_milliseconds(timestamp: Timestamp) -> int:
    return timestamp.seconds * 1_000 + timestamp.nanos // 1_000_000


def _timestamp_from_milliseconds(timestamp_ms: int) -> Timestamp:
    seconds, milliseconds = divmod(timestamp_ms, 1_000)
    return Timestamp(seconds=seconds, nanos=milliseconds * 1_000_000)


def _parse_datetime(value: str) -> datetime:
    normalized_value = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be an ISO 8601 datetime such as 2024-01-15T10:30:00Z"
        ) from exc
    if timestamp.tzinfo is None:
        raise argparse.ArgumentTypeError("must include a timezone, such as Z")
    return timestamp.astimezone(UTC)


def _timestamp_from_datetime(timestamp: datetime) -> Timestamp:
    protobuf_timestamp = Timestamp()
    protobuf_timestamp.FromDatetime(timestamp)
    return protobuf_timestamp


def _format_timestamp(timestamp: Timestamp) -> str:
    return timestamp.ToDatetime(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _format_timestamp_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC).astimezone(NETHERLANDS_TZ).strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )


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


def _client_build_entry(args: argparse.Namespace) -> energy_pb2.Entry:
    return energy_pb2.Entry(
        key=energy_pb2.EntryKey(
            meter_id=args.meter_id,
            stream=args.stream,
            timestamp_ms=_timestamp_from_datetime(args.timestamp),
        ),
        value=args.value,
    )


def _run_client_action(
    args: argparse.Namespace,
    out: OutFn = print,
    err: OutFn = lambda text: print(text, file=sys.stderr),
) -> int:
    try:
        with grpc.insecure_channel(args.target) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
            client = energy_pb2_grpc.EnergyStoreStub(channel)

            if args.action == "set":
                if args.value is None:
                    err("--value is required when --action is set")
                    return 1
                set_reply = client.SetEntry(
                    energy_pb2.SetEntryRequest(entry=_client_build_entry(args))
                )
                out(f"SetEntry: ok={set_reply.ok} message={set_reply.message}")
                return 0

            if args.action == "update":
                if args.value is None:
                    err("--value is required when --action is update")
                    return 1
                update_reply = client.UpdateEntry(
                    energy_pb2.UpdateEntryRequest(entry=_client_build_entry(args))
                )
                out(f"UpdateEntry: ok={update_reply.ok} message={update_reply.message}")
                return 0

            if args.action == "delete":
                delete_reply = client.DeleteEntry(
                    energy_pb2.DeleteEntryRequest(
                        key=energy_pb2.EntryKey(
                            meter_id=args.meter_id,
                            stream=args.stream,
                            timestamp_ms=_timestamp_from_datetime(args.timestamp),
                        )
                    )
                )
                out(f"DeleteEntry: ok={delete_reply.ok} message={delete_reply.message}")
                return 0

            if args.action == "query":
                start = getattr(args, "start", None)
                end = getattr(args, "end", None)
                limit = getattr(args, "limit", 0)
                if start is None or end is None:
                    err("--start and --end are required when --action is query")
                    return 1
                query_reply = client.QueryRange(
                    energy_pb2.QueryRangeRequest(
                        meter_id=args.meter_id,
                        stream=args.stream,
                        start_ms=_timestamp_to_milliseconds(_timestamp_from_datetime(start)),
                        end_ms=_timestamp_to_milliseconds(_timestamp_from_datetime(end)),
                        limit=limit,
                    )
                )
                out(f"QueryRange: found {len(query_reply.points)} points")
                for point in query_reply.points:
                    out(f"  timestamp={_format_timestamp_ms(point.timestamp_ms)} value={point.value}")
                return 0

            if args.action == "version":
                version_reply = client.GetVersion(empty_pb2.Empty())
                out(f"Version: {version_reply.version}")
                return 0

            # Default to "get"
            get_reply = client.GetEntry(
                energy_pb2.GetEntryRequest(
                    key=energy_pb2.EntryKey(
                        meter_id=args.meter_id,
                        stream=args.stream,
                        timestamp_ms=_timestamp_from_datetime(args.timestamp),
                    )
                )
            )
            out(f"GetEntry: found={get_reply.found}")
            if get_reply.found:
                out(
                    "Entry:"
                    f" meter_id={get_reply.entry.key.meter_id}"
                    f" stream={get_reply.entry.key.stream}"
                    f" timestamp={_format_timestamp(get_reply.entry.key.timestamp_ms)}"
                    f" value={get_reply.entry.value}"
                )
            return 0
    except grpc.RpcError as exc:
        err(f"gRPC request failed: {exc.code().name} {exc.details()}")
        return 1
    except grpc.FutureTimeoutError:
        err(f"Could not connect to gRPC server at {args.target}")
        return 1


class EnergyStoreServicer(energy_pb2_grpc.EnergyStoreServicer):
    def __init__(self, store: TimeSeriesStore | None = None):
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
    parser.add_argument("--target", default="localhost:50051")
    parser.add_argument("--meter-id", default="demo-meter")
    parser.add_argument("--stream", default="consumed_kwh")
    parser.add_argument(
        "--timestamp",
        type=_parse_datetime,
        default=_parse_datetime("2024-08-30T05:20:00Z"),
        help="ISO 8601 datetime with timezone for get, set, update, or delete actions",
    )
    parser.add_argument("--action", choices=["serve", "get", "set", "update", "delete", "query", "version"], default="serve")
    parser.add_argument("--value", type=float, help="Value for set or update action")
    parser.add_argument(
        "--start",
        type=_parse_datetime,
        help="Inclusive ISO 8601 start datetime with timezone for query action",
    )
    parser.add_argument(
        "--end",
        type=_parse_datetime,
        help="Inclusive ISO 8601 end datetime with timezone for query action",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of results for query action (0 = no limit)")
    return parser


def serve(
    args: argparse.Namespace | None = None,
    grpc_server_factory: Callable[[], grpc.Server] | None = None,
    register_servicer: Callable[[EnergyStoreServicer, grpc.Server], None] | None = None,
    servicer_factory: Callable[[], EnergyStoreServicer] | None = None,
    port: int | None = None,
    out: OutFn = print,
) -> int:

    args = args or build_parser().parse_args()
    grpc_server_factory = grpc_server_factory or _default_grpc_server_factory
    register_servicer = register_servicer or energy_pb2_grpc.add_EnergyStoreServicer_to_server
    servicer_factory = servicer_factory or EnergyStoreServicer
    port = port if port is not None else GRPC_PORT

    if getattr(args, "version", False):
        out(APP_VERSION)
        return 0

    action = getattr(args, "action", "serve")
    if action in {"get", "set", "update", "delete", "query", "version"}:
        return _run_client_action(args, out=out)

    grpc_server = grpc_server_factory()
    servicer = servicer_factory()
    register_servicer(servicer, grpc_server)
    grpc_server.add_insecure_port(f"[::]:{port}")
    grpc_server.start()
    out(f"gRPC EnergyStore running on port {port}")
    grpc_server.wait_for_termination()
    return 0

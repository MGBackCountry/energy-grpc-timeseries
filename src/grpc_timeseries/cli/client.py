import argparse
import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import grpc
from google.protobuf import empty_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from .. import __version__
from ..generated import energy_pb2, energy_pb2_grpc
from ..service.energy_store_service import APP_VERSION

NETHERLANDS_TZ = ZoneInfo("Europe/Amsterdam")


def _timestamp_to_milliseconds(timestamp: Timestamp) -> int:
    return timestamp.seconds * 1_000 + timestamp.nanos // 1_000_000


def _timestamp_from_milliseconds(timestamp_ms: int) -> Timestamp:
    seconds, milliseconds = divmod(timestamp_ms, 1_000)
    protobuf_timestamp = Timestamp()
    protobuf_timestamp.seconds = seconds
    protobuf_timestamp.nanos = milliseconds * 1_000_000
    return protobuf_timestamp


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
    out=print,
    err=lambda text: print(text, file=sys.stderr),
) -> int:
    try:
        with grpc.insecure_channel(args.target) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
            client = energy_pb2_grpc.EnergyStoreStub(channel)

            match args.action:
                case "get":
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

                case "set":
                    if args.value is None:
                        err("--value is required when --action is set")
                        return 1
                    set_reply = client.SetEntry(
                        energy_pb2.SetEntryRequest(entry=_client_build_entry(args))
                    )
                    out(f"SetEntry: ok={set_reply.ok} message={set_reply.message}")
                    return 0

                case "update":
                    if args.value is None:
                        err("--value is required when --action is update")
                        return 1
                    update_reply = client.UpdateEntry(
                        energy_pb2.UpdateEntryRequest(entry=_client_build_entry(args))
                    )
                    out(f"UpdateEntry: ok={update_reply.ok} message={update_reply.message}")
                    return 0

                case "delete":
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

                case "query":
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

                case "version":
                    version_reply = client.GetVersion(empty_pb2.Empty())
                    out(f"Version: {version_reply.version}")
                    return 0

                case _:
                    err(f"Unsupported action: {args.action}")
                    return 1

            raise AssertionError("unreachable action branch")
    except grpc.RpcError as exc:
        err(f"gRPC request failed: {exc.code().name} {exc.details()}")
        return 1
    except grpc.FutureTimeoutError:
        err(f"Could not connect to gRPC server at {args.target}")
        return 1


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


__all__ = [
    "APP_VERSION",
    "__version__",
    "_build_entry",
    "_client_build_entry",
    "_format_timestamp",
    "_format_timestamp_ms",
    "_parse_datetime",
    "_run_client_action",
    "_timestamp_from_datetime",
    "_timestamp_from_milliseconds",
    "_timestamp_to_milliseconds",
    "build_parser",
]

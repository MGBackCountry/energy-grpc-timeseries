#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

import grpc
from google.protobuf.timestamp_pb2 import Timestamp


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "src" / "energy_server" / "generated"))

from energy_server.generated import energy_pb2, energy_pb2_grpc


def timestamp_from_milliseconds(timestamp_ms: int) -> Timestamp:
    seconds, milliseconds = divmod(timestamp_ms, 1_000)
    return Timestamp(seconds=seconds, nanos=milliseconds * 1_000_000)


def build_entry(
    meter_id: str,
    stream: str,
    timestamp_ms: int,
    value: float,
) -> energy_pb2.Entry:
    return energy_pb2.Entry(
        key=energy_pb2.EntryKey(
            meter_id=meter_id,
            stream=stream,
            timestamp_ms=timestamp_from_milliseconds(timestamp_ms),
        ),
        value=value,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local gRPC client for the energy server.")
    parser.add_argument("--target", default="localhost:50051")
    parser.add_argument("--meter-id", default="demo-meter")
    parser.add_argument("--stream", default="consumed_kwh")
    parser.add_argument("--timestamp-ms", type=int, default=1_725_000_000_000)
    parser.add_argument( "--action", choices=["get", "set", 'update'], default="get")
    parser.add_argument("--value", type=float, help="Value for set or update action")
    return parser


def set_client_entry(args, client: energy_pb2_grpc.EnergyStoreStub):
    return client.SetEntry(
        energy_pb2.SetEntryRequest(
            entry=build_entry(
                args.meter_id,
                args.stream,
                args.timestamp_ms,
                args.value
            )
        )
    )

def update_client_entry(args, client: energy_pb2_grpc.EnergyStoreStub):
    return client.UpdateEntry(
        energy_pb2.UpdateEntryRequest(
            entry=build_entry(
                args.meter_id,
                args.stream,
                args.timestamp_ms,
                args.value
            )
        )
    )

def get_client_entry(args, client: energy_pb2_grpc.EnergyStoreStub):
    return client.GetEntry(
        key=energy_pb2.EntryKey(
            meter_id=args.meter_id,
            stream=args.stream,
            timestamp_ms=timestamp_from_milliseconds(args.timestamp_ms)
        )
    )


def main() -> int:
    args = build_parser().parse_args()
    if args.action in {"set", "update"} and args.value is None:
        print("--value is required when --action is set or update")
        return 1

    try:
        with grpc.insecure_channel(args.target) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
            client = energy_pb2_grpc.EnergyStoreStub(channel)

            if args.action == "set":
                set_reply = set_client_entry(args, client)
                print(f"SetEntry: ok={set_reply.ok} message={set_reply.message}")
            elif args.action == "update":
                update_reply = update_client_entry(args, client)
                print(f"UpdateEntry: ok={update_reply.ok} message={update_reply.message}")
            elif args.action == "get":
                get_reply = get_client_entry(args, client)
                print(f"GetEntry: found={get_reply.found}")
                if get_reply.found:
                    print(
                        "Entry:"
                        f" meter_id={get_reply.entry.key.meter_id}"
                        f" stream={get_reply.entry.key.stream}"
                        f" timestamp_ms={get_reply.entry.key.timestamp_ms}"
                        f" value={get_reply.entry.value}"
                    )
    except grpc.RpcError as exc:
        print(f"gRPC request failed: {exc.code().name} {exc.details()}", file=sys.stderr)
        return 1
    except grpc.FutureTimeoutError:
        print(f"Could not connect to gRPC server at {args.target}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

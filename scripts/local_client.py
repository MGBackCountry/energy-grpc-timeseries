import argparse
import sys
from pathlib import Path

import grpc


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "src" / "energy_server" / "generated"))

import energy_pb2
import energy_pb2_grpc


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
            timestamp_ms=timestamp_ms,
        ),
        value=value,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local gRPC client for the energy server.")
    parser.add_argument("--target", default="localhost:50051")
    parser.add_argument("--meter-id", default="demo-meter")
    parser.add_argument("--stream", default="consumed_kwh")
    parser.add_argument("--timestamp-ms", type=int, default=1_725_000_000_000)
    parser.add_argument("--initial-value", type=float, default=12.5)
    parser.add_argument("--updated-value", type=float, default=18.75)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        with grpc.insecure_channel(args.target) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
            client = energy_pb2_grpc.EnergyStoreStub(channel)

            set_reply = client.SetEntry(
                energy_pb2.SetEntryRequest(
                    entry=build_entry(
                        args.meter_id,
                        args.stream,
                        args.timestamp_ms,
                        args.initial_value,
                    )
                )
            )
            print(f"SetEntry: ok={set_reply.ok} message={set_reply.message}")

            update_reply = client.UpdateEntry(
                energy_pb2.UpdateEntryRequest(
                    entry=build_entry(
                        args.meter_id,
                        args.stream,
                        args.timestamp_ms,
                        args.updated_value,
                    )
                )
            )
            print(f"UpdateEntry: ok={update_reply.ok} message={update_reply.message}")

            get_reply = client.GetEntry(
                energy_pb2.GetEntryRequest(
                    key=energy_pb2.EntryKey(
                        meter_id=args.meter_id,
                        stream=args.stream,
                        timestamp_ms=args.timestamp_ms,
                    )
                )
            )
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

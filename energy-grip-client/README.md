# energy-grpc-client

Standalone Python gRPC client for the energy-grpc-timeseries server.

## Location

This scaffold is stored inside the current cloned repository at:

`energy-grip-client`

## Quick start

```bash
cd energy-grip-client
uv sync
make gen-protos
python examples/demo.py
```

Start the server separately from the main repository root:

```bash
cd ..
docker compose up -d
```

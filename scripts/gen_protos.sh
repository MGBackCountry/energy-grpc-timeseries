#!/usr/bin/env bash
set -e

python -m grpc_tools.protoc \
  -I./protos \
  --python_out=./src/grpc_timeseries/generated \
  --grpc_python_out=./src/grpc_timeseries/generated \
  ./protos/energy.proto
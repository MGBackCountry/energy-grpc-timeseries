# Use bash for slightly stricter shell behavior in recipes
SHELL := /bin/bash

# Core settings
UV := uv
PYTHON := python
MODULE := energy_server

# Paths
PROTO_DIR := protos
GEN_DIR := src/energy_server/generated
STAMP := $(GEN_DIR)/.protos.stamp
PROTO_FILES := $(wildcard $(PROTO_DIR)/*.proto)

# Docker
DOCKER_IMAGE := energy-server
DOCKERFILE := docker/Dockerfile.python

.PHONY: help install gen-protos run dev watch clean \
        test test-server test-grpc test-one \
        docker-build docker-run

help:
	@echo "Available targets:"
	@echo "  install       Install deps with uv"
	@echo "  gen-protos    Regenerate protobuf/grpc bindings when .proto files changed"
	@echo "  run           Run the gRPC server"
	@echo "  dev           Regenerate protos, then run server"
	@echo "  watch         Watch protos/ and regenerate on change (requires watchfiles)"
	@echo "  clean         Remove generated protobuf outputs (keeps __init__.py)"
	@echo "  test          Run full pytest suite"
	@echo "  test-server   Run lightweight servicer tests"
	@echo "  test-grpc     Run gRPC integration tests"
	@echo "  test-one      Run one test via TEST=path::test_name"
	@echo "  docker-build  Build python service image"
	@echo "  docker-run    Start Redis + gRPC stack via compose"

install:
	$(UV) sync

# Regenerate only when proto inputs changed
gen-protos: $(STAMP)

$(STAMP): $(PROTO_FILES)
	@echo "Protos changed -> regenerating..."
	$(UV) run $(PYTHON) -m grpc_tools.protoc \
		-I $(PROTO_DIR) \
		--python_out=$(GEN_DIR) \
		--grpc_python_out=$(GEN_DIR) \
		$(PROTO_DIR)/*.proto
	@touch $(STAMP)

run:
	$(UV) run $(PYTHON) -m $(MODULE)

dev: gen-protos run

watch:
	$(UV) run watchfiles --filter python 'make gen-protos' $(PROTO_DIR)

clean:
	@echo "Cleaning generated protobuf files (keeping __init__.py)..."
	find $(GEN_DIR) -type f -name "*.py" ! -name "__init__.py" -delete
	find $(GEN_DIR) -type f -name "*.pyi" -delete
	find $(GEN_DIR) -type f -name "*.pyc" -delete
	rm -f $(STAMP)

test:
	$(UV) run pytest

test-server:
	$(UV) run pytest tests/test_server_integration.py

test-grpc:
	$(UV) run pytest tests/test_grpc_client_integration.py

# Usage:
#   make test-one TEST=tests/test_server_integration.py::test_query_range_applies_limit
test-one:
	@test -n "$(TEST)" || (echo "ERROR: Provide TEST=path::test_name"; exit 1)
	$(UV) run pytest "$(TEST)"

docker-build:
	docker build -f $(DOCKERFILE) -t $(DOCKER_IMAGE) .

docker-run:
	docker compose up
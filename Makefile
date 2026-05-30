PYTHON := python
MODULE := energy_server
PROTO_DIR := ./protos
GEN_DIR := ./generated/energy_server
STAMP := $(GEN_DIR)/.protos.stamp

.PHONY: install gen-protos run dev clean docker-build docker-run test

install:
	uv sync

# ----------------------------------------
# gRPC proto generation only when .proto files change
# ----------------------------------------

gen-protos: $(STAMP)

$(STAMP): $(shell find $(PROTO_DIR) -name "*.proto")
	@echo "Protos changed → regenerating..."
	uv run $(PYTHON) -m grpc_tools.protoc \
		-I $(PROTO_DIR) \
		--python_out=$(GEN_DIR) \
		--grpc_python_out=$(GEN_DIR) \
		$(PROTO_DIR)/*.proto
	touch $(STAMP)

# ----------------------------------------
# Run server
# ----------------------------------------

run:
	$(PYTHON) -m $(MODULE)

# ----------------------------------------
# Development (regen + run)
# ----------------------------------------

dev: gen-protos run

# ----------------------------------------
# Watch mode (auto-regenerate protos)
# ----------------------------------------

watch:
	watchfiles --filter python 'make gen-protos' $(PROTO_DIR)

# ----------------------------------------
# Cleaning
# ----------------------------------------

clean:
	@echo "Cleaning generated files (keeping __init__.py)..."
	find $(GEN_DIR) -type f -name "*.py" ! -name "__init__.py" -delete
	rm -f $(STAMP)

# ----------------------------------------
# Docker
# ----------------------------------------

docker-build:
	docker build -f docker/Dockerfile.python -t energy-server .

docker-run:
	docker compose up

# ----------------------------------------
# Testing (prepare for later)
# ----------------------------------------

test:
	pytest


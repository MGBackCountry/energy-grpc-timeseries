from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib


def _version_from_pyproject() -> str:
	pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
	with pyproject_path.open("rb") as handle:
		data = tomllib.load(handle)
	return data["project"]["version"]


try:
	__version__ = version("energy-grpc-timeseries")
except PackageNotFoundError:
	# Running from source (for example via `uv run scripts/local_client.py`).
	__version__ = _version_from_pyproject()

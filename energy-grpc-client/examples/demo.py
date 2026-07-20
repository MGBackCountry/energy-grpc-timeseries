import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from client.energy_client import EnergyClient  # noqa: E402

METER = "home"
STREAM = "consumed_kwh"
# Example timestamps for demo purposes.
T1 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
T2 = datetime(2024, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
T3 = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


def main() -> None:
    with EnergyClient() as client:
        print(client.set_entry(METER, STREAM, T1, 1.5))
        print(client.set_entry(METER, STREAM, T2, 2.3))
        print(client.get_entry(METER, STREAM, T2))
        print(client.update_entry(METER, STREAM, T2, 9.9))
        print(client.query_range(METER, STREAM, T1, T3))
        print(client.delete_entry(METER, STREAM, T1))


if __name__ == "__main__":
    main()

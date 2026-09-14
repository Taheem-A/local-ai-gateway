"""Print recent Local AI Gateway operational metrics as JSON."""

from __future__ import annotations

import argparse
import json

from app.observability import summary


def main() -> None:
    """Parse the reporting window and print the corresponding SQLite summary."""

    parser = argparse.ArgumentParser(description="Show recent Local AI Gateway metrics.")
    parser.add_argument("--days", type=int, default=30, help="Number of days to summarize.")
    args = parser.parse_args()

    print(json.dumps(summary(args.days), indent=2))


if __name__ == "__main__":
    main()

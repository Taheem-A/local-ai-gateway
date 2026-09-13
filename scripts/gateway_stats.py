from __future__ import annotations

import argparse
import json

from app.observability import summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    data = summary(args.days)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()

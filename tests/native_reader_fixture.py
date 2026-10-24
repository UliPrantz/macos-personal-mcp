"""Framed worker failure fixture. Never imports/accesses native adapters."""

import json
import sys
import time


def main() -> None:
    for line in sys.stdin:
        request: dict[str, dict[str, str]] = json.loads(line)
        query = request["request"]["query"]
        if query == "hang":
            time.sleep(60)
        if query == "oversize":
            sys.stdout.write("x" * 2_000_001 + "\n")
        elif query == "exit":
            return
        else:
            sys.stdout.write('{"code":"fixture_failure","message":"Synthetic failure"}\n')
        sys.stdout.flush()


if __name__ == "__main__":
    main()

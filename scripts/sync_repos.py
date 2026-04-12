import argparse
from pathlib import Path

from benchmark_lib import (
    BenchmarkError,
    default_participants_csv,
    default_repos_dir,
    read_participants,
    sync_participants,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clone/fetch/pull participant repos.")
    parser.add_argument(
        "--participants",
        type=Path,
        default=default_participants_csv(),
        help="participants.csv path",
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=default_repos_dir(),
        help="directory to store clones",
    )
    parser.add_argument(
        "--allow-dirty-repos",
        action="store_true",
        help="allow syncing repos even if clone working tree is dirty",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="optional path for sync report json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        participants = read_participants(args.participants)
        records = sync_participants(
            participants=participants,
            repos_dir=args.repos_dir,
            allow_dirty=args.allow_dirty_repos,
        )
    except BenchmarkError as exc:
        print("ERROR:", exc)
        return 1
    for record in records:
        print(
            "{alias}: {status} branch={branch} commit={commit}".format(
                alias=record.get("alias"),
                status=record.get("status"),
                branch=record.get("branch"),
                commit=record.get("commit"),
            )
        )
        if record.get("error"):
            print("  error:", record["error"])
    if args.json_out:
        write_json(args.json_out, records)
        print("sync report:", args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


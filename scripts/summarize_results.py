import argparse
from pathlib import Path

from benchmark_lib import BenchmarkError, write_summary_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate summary files from results.json.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="run directory containing results.json and run_config.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results_path = args.run_dir / "results.json"
    config_path = args.run_dir / "run_config.json"
    if not results_path.exists():
        print("ERROR: results.json not found:", results_path)
        return 1
    if not config_path.exists():
        print("ERROR: run_config.json not found:", config_path)
        return 1
    try:
        import json

        results = json.loads(results_path.read_text(encoding="utf-8"))
        run_config = json.loads(config_path.read_text(encoding="utf-8"))
        expected_traces = int(run_config["expected_traces"])
        write_summary_files(args.run_dir, results, expected_traces)
    except (ValueError, KeyError, BenchmarkError) as exc:
        print("ERROR:", exc)
        return 1
    print("summary regenerated:", args.run_dir / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

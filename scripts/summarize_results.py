import argparse
import json
from pathlib import Path

from benchmark_lib import BenchmarkError, parse_score_config, write_summary_files


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
        results = json.loads(results_path.read_text(encoding="utf-8"))
        run_config = json.loads(config_path.read_text(encoding="utf-8"))
        expected_traces = int(run_config["expected_traces"])
        score_config = None
        if all(
            key in run_config
            for key in (
                "score_util_weight",
                "score_throughput_weight",
                "score_avg_libc_throughput_ops",
                "score_avg_libc_throughput_kops",
            )
        ):
            score_config = {
                "util_weight": float(run_config["score_util_weight"]),
                "throughput_weight": float(run_config["score_throughput_weight"]),
                "avg_libc_throughput_ops": float(run_config["score_avg_libc_throughput_ops"]),
                "avg_libc_throughput_kops": float(run_config["score_avg_libc_throughput_kops"]),
            }
        elif run_config.get("benchmark_base"):
            config_path = Path(str(run_config["benchmark_base"])) / "config.h"
            if config_path.exists():
                score_config = parse_score_config(config_path)
        write_summary_files(args.run_dir, results, expected_traces, score_config=score_config)
    except (ValueError, KeyError, BenchmarkError) as exc:
        print("ERROR:", exc)
        return 1
    print("summary regenerated:", args.run_dir / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

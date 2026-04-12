import argparse
import shutil
from pathlib import Path
from typing import Dict, List

from benchmark_lib import (
    BenchmarkError,
    copy_tree_filtered,
    default_benchmark_base,
    default_participants_csv,
    default_repos_dir,
    default_runs_dir,
    detect_harness_diffs,
    ensure_dir,
    format_completed_process,
    git_output,
    init_base_result,
    parse_default_trace_count,
    parse_mdriver_output,
    read_participants,
    result_from_attempts,
    run_command,
    sync_participants,
    timestamp_string,
    write_json,
    write_summary_files,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run malloc benchmark comparisons.")
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
        "--benchmark-base",
        type=Path,
        default=default_benchmark_base(),
        help="reference malloc-lab harness directory",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=default_runs_dir(),
        help="directory to store run outputs",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="number of repeated runs per participant",
    )
    parser.add_argument(
        "--mode",
        choices=["repo", "strict"],
        default="repo",
        help="repo: run each participant lab as-is, strict: use only participant mm.c on reference harness",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="skip clone/fetch/pull and use existing repos dir",
    )
    parser.add_argument(
        "--allow-dirty-repos",
        action="store_true",
        help="allow syncing repos even if clone working tree is dirty",
    )
    parser.add_argument(
        "--fail-on-harness-diff",
        action="store_true",
        help="mark participant as failed when reference harness diff is detected",
    )
    return parser.parse_args()


def build_worktree(
    mode: str,
    benchmark_base: Path,
    source_lab_dir: Path,
    source_mm_path: Path,
    worktree_root: Path,
) -> Path:
    work_lab_name = source_lab_dir.name or benchmark_base.name
    work_lab_dir = worktree_root / work_lab_name
    if mode == "repo":
        copy_tree_filtered(source_lab_dir, work_lab_dir)
    else:
        copy_tree_filtered(benchmark_base, work_lab_dir)
        shutil.copy2(source_mm_path, work_lab_dir / "mm.c")
    return work_lab_dir


def run_single_attempt(work_lab_dir: Path, log_path: Path) -> Dict[str, object]:
    log_chunks: List[str] = []
    clean = run_command(["make", "clean"], cwd=work_lab_dir, check=False)
    log_chunks.append(format_completed_process(["make", "clean"], clean))
    if clean.returncode != 0:
        log_path.write_text("".join(log_chunks), encoding="utf-8")
        return {"status": "BUILD_FAIL", "error": "make clean failed"}
    build = run_command(["make"], cwd=work_lab_dir, check=False)
    log_chunks.append(format_completed_process(["make"], build))
    if build.returncode != 0:
        log_path.write_text("".join(log_chunks), encoding="utf-8")
        return {"status": "BUILD_FAIL", "error": "make failed"}
    mdriver = run_command(["./mdriver", "-v", "-g"], cwd=work_lab_dir, check=False)
    log_chunks.append(format_completed_process(["./mdriver", "-v", "-g"], mdriver))
    log_path.write_text("".join(log_chunks), encoding="utf-8")
    if mdriver.returncode != 0:
        return {"status": "RUN_FAIL", "error": "mdriver returned non-zero"}
    parsed = parse_mdriver_output(mdriver.stdout)
    if parsed.get("correct") is None or parsed.get("perfidx") is None:
        return {"status": "RUN_FAIL", "error": "failed to parse mdriver output"}
    parsed["status"] = "OK"
    return parsed


def run_participant(
    participant,
    sync_record: Dict[str, object],
    benchmark_base: Path,
    run_dir: Path,
    repeat: int,
    mode: str,
    expected_traces: int,
    fail_on_harness_diff: bool,
) -> Dict[str, object]:
    participant_dir = run_dir / participant.alias
    ensure_dir(participant_dir)
    write_json(participant_dir / "sync.json", sync_record)
    base_result = init_base_result(participant, sync_record, mode=mode)
    if sync_record.get("status") != "SYNCED":
        base_result["status"] = sync_record.get("status")
        base_result["error"] = sync_record.get("error")
        return base_result
    repo_dir = Path(str(sync_record["repo_dir"]))
    source_mm_path = repo_dir / participant.mm_path
    source_lab_dir = source_mm_path.parent
    if not source_mm_path.exists():
        base_result["status"] = "PARTICIPANT_ERROR"
        base_result["error"] = "mm_path not found: {}".format(source_mm_path)
        return base_result
    if not source_lab_dir.exists():
        base_result["status"] = "PARTICIPANT_ERROR"
        base_result["error"] = "lab directory not found: {}".format(source_lab_dir)
        return base_result
    harness_diffs = detect_harness_diffs(source_lab_dir, benchmark_base)
    write_json(participant_dir / "harness_diffs.json", harness_diffs)
    base_result["harness_diff_count"] = len(harness_diffs)
    if harness_diffs and fail_on_harness_diff:
        base_result["status"] = "HARNESS_DIFF"
        base_result["error"] = "reference harness mismatch detected"
        return base_result
    attempts: List[Dict[str, object]] = []
    for attempt_number in range(1, repeat + 1):
        attempt_root = participant_dir / "attempts" / "attempt-{:02d}".format(attempt_number)
        worktree_root = attempt_root / "worktree"
        ensure_dir(worktree_root)
        work_lab_dir = build_worktree(
            mode=mode,
            benchmark_base=benchmark_base,
            source_lab_dir=source_lab_dir,
            source_mm_path=source_mm_path,
            worktree_root=worktree_root,
        )
        attempt_result = run_single_attempt(work_lab_dir, participant_dir / "attempt-{:02d}.log".format(attempt_number))
        attempt_result["attempt"] = attempt_number
        attempts.append(attempt_result)
        if attempt_result["status"] in {"BUILD_FAIL", "RUN_FAIL"}:
            break
    result = result_from_attempts(base_result, attempts, expected_traces)
    return result


def main() -> int:
    args = parse_args()
    try:
        if args.repeat < 1:
            raise BenchmarkError("--repeat must be at least 1")
        participants = read_participants(args.participants)
        benchmark_base = args.benchmark_base.resolve()
        expected_traces = parse_default_trace_count(benchmark_base / "config.h")
        if args.skip_sync:
            sync_records = []
            for participant in participants:
                repo_dir = args.repos_dir / participant.alias
                if not repo_dir.exists() or not (repo_dir / ".git").exists():
                    sync_records.append(
                        {
                            "alias": participant.alias,
                            "repo_dir": str(repo_dir),
                            "repo_url": participant.repo_url,
                            "branch": participant.branch,
                            "requested_branch": participant.branch,
                            "commit": None,
                            "dirty": None,
                            "status": "SYNC_FAIL",
                            "error": "repo clone not found and --skip-sync used",
                            "steps": [],
                        }
                    )
                else:
                    branch = git_output(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
                    commit = git_output(repo_dir, ["rev-parse", "HEAD"])
                    sync_records.append(
                        {
                            "alias": participant.alias,
                            "repo_dir": str(repo_dir),
                            "repo_url": participant.repo_url,
                            "branch": branch,
                            "requested_branch": participant.branch,
                            "commit": commit,
                            "dirty": None,
                            "status": "SYNCED",
                            "steps": [],
                        }
                    )
        else:
            sync_records = sync_participants(
                participants=participants,
                repos_dir=args.repos_dir,
                allow_dirty=args.allow_dirty_repos,
            )
        run_dir = args.runs_dir / timestamp_string()
        ensure_dir(run_dir)
        write_json(
            run_dir / "run_config.json",
            {
                "mode": args.mode,
                "repeat": args.repeat,
                "participants_csv": str(args.participants),
                "repos_dir": str(args.repos_dir),
                "benchmark_base": str(benchmark_base),
                "expected_traces": expected_traces,
                "skip_sync": args.skip_sync,
                "fail_on_harness_diff": args.fail_on_harness_diff,
            },
        )
        results: List[Dict[str, object]] = []
        sync_by_alias = {record["alias"]: record for record in sync_records}
        for participant in participants:
            sync_record = sync_by_alias[participant.alias]
            result = run_participant(
                participant=participant,
                sync_record=sync_record,
                benchmark_base=benchmark_base,
                run_dir=run_dir,
                repeat=args.repeat,
                mode=args.mode,
                expected_traces=expected_traces,
                fail_on_harness_diff=args.fail_on_harness_diff,
            )
            results.append(result)
        write_summary_files(run_dir, results, expected_traces)
    except BenchmarkError as exc:
        print("ERROR:", exc)
        return 1
    print("run directory:", run_dir)
    print("summary:", run_dir / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

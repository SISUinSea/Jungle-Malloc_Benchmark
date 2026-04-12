import csv
import hashlib
import json
import re
import shlex
import shutil
import statistics
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional


COMPARE_IGNORE_NAMES = {"mm.c", "README.md", ".DS_Store"}
COPY_IGNORE_NAMES = {"mdriver", "__pycache__", "docs"}
COPY_IGNORE_PATTERNS = ("*.o", "*~", "*.pyc")
TOTAL_RE = re.compile(r"^\s*Total\s+(\d+)%\s+(\d+)\s+([0-9.]+)\s+(\d+)\s*$")
CORRECT_RE = re.compile(r"^correct:(\d+)\s*$")
PERFIDX_RE = re.compile(r"^perfidx:([0-9.]+)\s*$")
PERF_LINE_RE = re.compile(
    r"^Perf index = ([0-9.]+) \(util\) \+ ([0-9.]+) \(thru\) = ([0-9.]+)/100\s*$"
)


class BenchmarkError(RuntimeError):
    pass


@dataclass
class Participant:
    alias: str
    repo_url: str
    branch: str
    mm_path: str
    enabled: bool


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_participants_csv() -> Path:
    return repo_root() / "participants.csv"


def default_repos_dir() -> Path:
    return repo_root() / "repos"


def default_runs_dir() -> Path:
    return repo_root() / "runs"


def default_benchmark_base() -> Path:
    return repo_root() / "benchmark_base" / "malloc-lab"


def timestamp_string() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_string(args: Iterable[str]) -> str:
    return shlex.join(list(args))


def run_command(args: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise BenchmarkError(
            "command failed: {}\nstdout:\n{}\nstderr:\n{}".format(
                command_string(args),
                completed.stdout,
                completed.stderr,
            )
        )
    return completed


def parse_enabled(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"", "true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise BenchmarkError("invalid enabled value: {}".format(value))


def read_participants(csv_path: Path) -> List[Participant]:
    if not csv_path.exists():
        raise BenchmarkError("participants file not found: {}".format(csv_path))
    participants: List[Participant] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"alias", "repo_url", "branch", "mm_path", "enabled"}
        if reader.fieldnames is None or set(reader.fieldnames) != required:
            raise BenchmarkError(
                "participants.csv header must be exactly: {}".format(",".join(sorted(required)))
            )
        for index, row in enumerate(reader, start=2):
            alias = (row.get("alias") or "").strip()
            repo_url = (row.get("repo_url") or "").strip()
            branch = (row.get("branch") or "").strip()
            mm_path = (row.get("mm_path") or "").strip()
            enabled = parse_enabled(row.get("enabled") or "")
            if not any([alias, repo_url, branch, mm_path, row.get("enabled")]):
                continue
            if not alias:
                raise BenchmarkError("line {}: alias is required".format(index))
            if not repo_url:
                raise BenchmarkError("line {}: repo_url is required".format(index))
            if not mm_path:
                raise BenchmarkError("line {}: mm_path is required".format(index))
            participants.append(
                Participant(
                    alias=alias,
                    repo_url=repo_url,
                    branch=branch,
                    mm_path=mm_path,
                    enabled=enabled,
                )
            )
    enabled_participants = [participant for participant in participants if participant.enabled]
    if not enabled_participants:
        raise BenchmarkError("no enabled participants found in {}".format(csv_path))
    aliases = [participant.alias for participant in enabled_participants]
    if len(set(aliases)) != len(aliases):
        raise BenchmarkError("participant aliases must be unique")
    return enabled_participants


def git_output(repo_dir: Path, args: List[str]) -> str:
    return run_command(["git"] + args, cwd=repo_dir, check=True).stdout.strip()


def git_status_dirty(repo_dir: Path) -> bool:
    return bool(git_output(repo_dir, ["status", "--porcelain"]))


def detect_default_branch(repo_dir: Path) -> str:
    try:
        head_ref = git_output(repo_dir, ["symbolic-ref", "refs/remotes/origin/HEAD", "--short"])
        if head_ref.startswith("origin/"):
            return head_ref.split("/", 1)[1]
    except BenchmarkError:
        pass
    current = git_output(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    if current and current != "HEAD":
        return current
    raise BenchmarkError("could not determine default branch for {}".format(repo_dir))


def ensure_branch(repo_dir: Path, branch: str) -> str:
    current = git_output(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    if current == branch:
        return current
    switch = run_command(["git", "switch", branch], cwd=repo_dir, check=False)
    if switch.returncode == 0:
        return branch
    create = run_command(
        ["git", "switch", "-c", branch, "--track", "origin/{}".format(branch)],
        cwd=repo_dir,
        check=False,
    )
    if create.returncode == 0:
        return branch
    raise BenchmarkError(
        "failed to switch to branch {}\nstdout:\n{}\nstderr:\n{}\nstdout:\n{}\nstderr:\n{}".format(
            branch,
            switch.stdout,
            switch.stderr,
            create.stdout,
            create.stderr,
        )
    )


def sync_repo(participant: Participant, repos_dir: Path, allow_dirty: bool = False) -> Dict[str, object]:
    ensure_dir(repos_dir)
    repo_dir = repos_dir / participant.alias
    steps: List[str] = []
    if repo_dir.exists():
        if not (repo_dir / ".git").exists():
            raise BenchmarkError("existing path is not a git repo: {}".format(repo_dir))
        remote_url = git_output(repo_dir, ["remote", "get-url", "origin"])
        if remote_url != participant.repo_url:
            raise BenchmarkError(
                "origin URL mismatch for {}: expected {}, found {}".format(
                    participant.alias,
                    participant.repo_url,
                    remote_url,
                )
            )
        if git_status_dirty(repo_dir) and not allow_dirty:
            raise BenchmarkError("repo is dirty: {}".format(repo_dir))
        run_command(["git", "fetch", "--all", "--prune"], cwd=repo_dir, check=True)
        steps.append("fetch")
    else:
        run_command(["git", "clone", participant.repo_url, str(repo_dir)], check=True)
        run_command(["git", "fetch", "--all", "--prune"], cwd=repo_dir, check=True)
        steps.append("clone")
    branch = participant.branch or detect_default_branch(repo_dir)
    ensure_branch(repo_dir, branch)
    if git_status_dirty(repo_dir) and not allow_dirty:
        raise BenchmarkError("repo became dirty before pull: {}".format(repo_dir))
    run_command(["git", "pull", "--ff-only", "origin", branch], cwd=repo_dir, check=True)
    commit = git_output(repo_dir, ["rev-parse", "HEAD"])
    current_branch = git_output(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    return {
        "alias": participant.alias,
        "repo_dir": str(repo_dir),
        "repo_url": participant.repo_url,
        "branch": current_branch,
        "requested_branch": participant.branch,
        "commit": commit,
        "dirty": git_status_dirty(repo_dir),
        "status": "SYNCED",
        "steps": steps,
    }


def sync_participants(
    participants: List[Participant],
    repos_dir: Path,
    allow_dirty: bool = False,
) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for participant in participants:
        try:
            records.append(sync_repo(participant, repos_dir, allow_dirty=allow_dirty))
        except BenchmarkError as exc:
            message = str(exc)
            status = "DIRTY_REPO" if "dirty" in message.lower() else "SYNC_FAIL"
            records.append(
                {
                    "alias": participant.alias,
                    "repo_dir": str(repos_dir / participant.alias),
                    "repo_url": participant.repo_url,
                    "branch": participant.branch,
                    "requested_branch": participant.branch,
                    "commit": None,
                    "dirty": None,
                    "status": status,
                    "error": message,
                    "steps": [],
                }
            )
    return records


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_compare_path(relative_path: Path) -> bool:
    parts = relative_path.parts
    if any(part in COPY_IGNORE_NAMES for part in parts):
        return False
    if relative_path.name in COMPARE_IGNORE_NAMES:
        return False
    if relative_path.suffix in {".o", ".pyc"}:
        return False
    return True


def load_reference_paths(benchmark_base: Path) -> List[Path]:
    paths: List[Path] = []
    for path in benchmark_base.rglob("*"):
        if path.is_file():
            relative = path.relative_to(benchmark_base)
            if should_compare_path(relative):
                paths.append(relative)
    return sorted(paths)


def detect_harness_diffs(lab_dir: Path, benchmark_base: Path) -> List[Dict[str, object]]:
    diffs: List[Dict[str, object]] = []
    for relative in load_reference_paths(benchmark_base):
        reference_path = benchmark_base / relative
        candidate_path = lab_dir / relative
        if not candidate_path.exists():
            diffs.append(
                {
                    "path": str(relative),
                    "type": "missing",
                    "reference_sha256": sha256_file(reference_path),
                    "candidate_sha256": None,
                }
            )
            continue
        reference_hash = sha256_file(reference_path)
        candidate_hash = sha256_file(candidate_path)
        if reference_hash != candidate_hash:
            diffs.append(
                {
                    "path": str(relative),
                    "type": "modified",
                    "reference_sha256": reference_hash,
                    "candidate_sha256": candidate_hash,
                }
            )
    return diffs


def copy_tree_filtered(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(*COPY_IGNORE_PATTERNS, *COPY_IGNORE_NAMES),
    )


def parse_default_trace_count(config_path: Path) -> int:
    count = 0
    reading = False
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("#define DEFAULT_TRACEFILES"):
            reading = True
        if reading:
            count += len(re.findall(r'"([^"]+)"', line))
            if line and not line.endswith("\\"):
                break
    if count == 0:
        raise BenchmarkError("failed to read DEFAULT_TRACEFILES from {}".format(config_path))
    return count


def parse_mdriver_output(output: str) -> Dict[str, Optional[float]]:
    correct: Optional[int] = None
    perfidx: Optional[float] = None
    perfidx_from_line: Optional[float] = None
    util_percent: Optional[int] = None
    total_ops: Optional[int] = None
    total_secs: Optional[float] = None
    total_kops: Optional[int] = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        match = CORRECT_RE.match(line)
        if match:
            correct = int(match.group(1))
            continue
        match = PERFIDX_RE.match(line)
        if match:
            perfidx = float(match.group(1))
            continue
        match = PERF_LINE_RE.match(line)
        if match:
            perfidx_from_line = float(match.group(3))
            continue
        match = TOTAL_RE.match(raw_line)
        if match:
            util_percent = int(match.group(1))
            total_ops = int(match.group(2))
            total_secs = float(match.group(3))
            total_kops = int(match.group(4))
    if perfidx is None and perfidx_from_line is not None:
        perfidx = perfidx_from_line
    return {
        "correct": correct,
        "perfidx": perfidx,
        "util_percent": util_percent,
        "total_ops": total_ops,
        "total_secs": total_secs,
        "total_kops": total_kops,
    }


def median_or_none(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def stable_value_or_none(values: List[int]) -> Optional[int]:
    if not values:
        return None
    return int(values[0])


def sort_results(results: List[Dict[str, object]]) -> List[Dict[str, object]]:
    status_rank = {
        "OK": 0,
        "INCORRECT": 1,
        "UNSTABLE": 2,
        "HARNESS_DIFF": 3,
        "BUILD_FAIL": 4,
        "RUN_FAIL": 5,
        "PARTICIPANT_ERROR": 6,
        "DIRTY_REPO": 7,
        "SYNC_FAIL": 8,
    }
    return sorted(
        results,
        key=lambda result: (
            status_rank.get(str(result.get("status")), 99),
            -(float(result.get("perfidx")) if result.get("perfidx") is not None else -1.0),
            -(float(result.get("throughput_kops")) if result.get("throughput_kops") is not None else -1.0),
            str(result.get("alias")),
        ),
    )


def render_harness_label(diff_count: int) -> str:
    if diff_count == 0:
        return "MATCH"
    return "DIFF({})".format(diff_count)


def to_csv_rows(results: List[Dict[str, object]], expected_traces: int) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    rank = 1
    for result in sort_results(results):
        ranked = result.get("status") == "OK"
        correct = result.get("correct")
        correct_label = ""
        if correct is not None:
            correct_label = "{}/{}".format(correct, expected_traces)
        row = {
            "rank": rank if ranked else "",
            "alias": result.get("alias", ""),
            "status": result.get("status", ""),
            "harness": render_harness_label(int(result.get("harness_diff_count", 0))),
            "correct": correct_label,
            "util_percent": "" if result.get("util_percent") is None else result.get("util_percent"),
            "throughput_kops": "" if result.get("throughput_kops") is None else result.get("throughput_kops"),
            "perfidx": "" if result.get("perfidx") is None else result.get("perfidx"),
            "branch": result.get("branch", ""),
            "commit": result.get("commit", ""),
            "repo_url": result.get("repo_url", ""),
            "mode": result.get("mode", ""),
        }
        rows.append(row)
        if ranked:
            rank += 1
    return rows


def write_summary_files(run_dir: Path, results: List[Dict[str, object]], expected_traces: int) -> None:
    rows = to_csv_rows(results, expected_traces)
    csv_path = run_dir / "summary.csv"
    md_path = run_dir / "summary.md"
    json_path = run_dir / "results.json"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "rank",
            "alias",
            "status",
            "harness",
            "correct",
            "util_percent",
            "throughput_kops",
            "perfidx",
            "branch",
            "commit",
            "repo_url",
            "mode",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    md_lines = [
        "# Benchmark Summary",
        "",
        "| rank | alias | status | harness | correct | util(%) | Kops | perfidx | branch | commit |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        md_lines.append(
            "| {rank} | {alias} | {status} | {harness} | {correct} | {util_percent} | {throughput_kops} | {perfidx} | {branch} | {commit} |".format(
                **row
            )
        )
    md_lines.append("")
    md_lines.append("expected_traces: {}".format(expected_traces))
    md_lines.append("")
    md_lines.append("generated_at: {}".format(datetime.now().isoformat(timespec="seconds")))
    md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    write_json(json_path, results)


def format_completed_process(command: List[str], completed: subprocess.CompletedProcess) -> str:
    return "\n".join(
        [
            "$ {}".format(command_string(command)),
            completed.stdout.rstrip(),
            completed.stderr.rstrip(),
            "[exit {}]".format(completed.returncode),
            "",
        ]
    ).strip() + "\n"


def result_from_attempts(
    base_result: Dict[str, object],
    attempts: List[Dict[str, object]],
    expected_traces: int,
) -> Dict[str, object]:
    result = dict(base_result)
    result["attempts"] = attempts
    successful = [attempt for attempt in attempts if attempt.get("status") == "OK"]
    if not attempts:
        return result
    if not successful:
        result["status"] = attempts[0]["status"]
        result["correct"] = None
        result["util_percent"] = None
        result["throughput_kops"] = None
        result["perfidx"] = None
        return result
    correct_values = [int(attempt["correct"]) for attempt in successful if attempt.get("correct") is not None]
    util_values = [int(attempt["util_percent"]) for attempt in successful if attempt.get("util_percent") is not None]
    kops_values = [int(attempt["total_kops"]) for attempt in successful if attempt.get("total_kops") is not None]
    perf_values = [float(attempt["perfidx"]) for attempt in successful if attempt.get("perfidx") is not None]
    unstable = len(successful) != len(attempts) or len(set(correct_values)) > 1
    if unstable:
        status = "UNSTABLE"
    elif correct_values and correct_values[0] < expected_traces:
        status = "INCORRECT"
    else:
        status = "OK"
    result["status"] = status
    result["correct"] = stable_value_or_none(correct_values)
    result["util_percent"] = int(median_or_none([float(value) for value in util_values])) if util_values else None
    result["throughput_kops"] = int(median_or_none([float(value) for value in kops_values])) if kops_values else None
    result["perfidx"] = median_or_none(perf_values)
    return result


def init_base_result(
    participant: Participant,
    sync_record: Dict[str, object],
    mode: str,
    harness_diff_count: int = 0,
) -> Dict[str, object]:
    return {
        "alias": participant.alias,
        "repo_url": participant.repo_url,
        "branch": sync_record.get("branch") or participant.branch,
        "commit": sync_record.get("commit"),
        "mode": mode,
        "status": sync_record.get("status"),
        "harness_diff_count": harness_diff_count,
    }

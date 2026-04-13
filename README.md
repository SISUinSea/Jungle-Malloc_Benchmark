# Malloc Lab Benchmark

동일한 로컬 머신 환경에서 여러 `malloc lab` 구현의 점수를 비교하는 도구다.

기본 모드는 `repo` 이다.

- 각 참가자의 repo를 clone/fetch/pull 한다.
- 각 참가자의 `malloc-lab` 작업 디렉터리를 별도 실행 디렉터리에 복사한다.
- `make clean && make && ./mdriver -v -g` 를 반복 실행한다.
- `correct`, `score`, `perfidx`, `Total util`, `Total Kops`를 집계한다.
- 기준 harness와 `mdriver.c`, `config.h`, `Makefile`, support files, `traces/` 차이도 검사한다.

`strict` 모드도 지원한다.

- 참가자 repo에서 `mm.c`만 가져온다.
- 나머지는 이 저장소의 `benchmark_base/malloc-lab` 기준 harness를 사용한다.

## 파일 구조

- `participants.csv`: 참가자 목록
- `benchmark_base/malloc-lab`: 기준 harness
- `repos/`: clone 보관 디렉터리
- `runs/`: 실행 결과 디렉터리
- `scripts/sync_repos.py`: repo 동기화만 수행
- `scripts/run_benchmarks.py`: 동기화 + 빌드 + 실행 + 집계
- `scripts/summarize_results.py`: 기존 run 결과 재집계

## 참가자 목록 작성

`participants.csv` 에 GitHub 링크를 넣는다.

```csv
alias,repo_url,branch,mm_path,enabled
haegeon,https://github.com/user1/malloc-lab.git,main,malloc-lab/mm.c,true
minsu,git@github.com:user2/malloc-lab.git,main,malloc-lab/mm.c,true
```

컬럼 의미:

- `alias`: 결과 표시에 쓸 짧은 이름
- `repo_url`: Git clone 이 가능한 주소
- `branch`: 비워 두면 remote 기본 브랜치 사용
- `mm_path`: repo 내부의 `mm.c` 경로. 보통 `malloc-lab/mm.c`
- `enabled`: `true` 인 행만 실행

`repo_url` 은 GitHub URL 외에 로컬 경로도 가능하다. 이건 네트워크 없이 로컬 검증할 때 유용하다.

## 실행 방법

repo 전체를 같은 머신에서 비교하는 기본 모드:

```bash
python3 scripts/run_benchmarks.py
```

엄격하게 `mm.c` 만 공통 harness에 주입하는 모드:

```bash
python3 scripts/run_benchmarks.py --mode strict
```

반복 횟수 변경:

```bash
python3 scripts/run_benchmarks.py --repeat 5
```

느린 구현이나 무한 루프처럼 보이는 구현 때문에 `mdriver`가 오래 걸릴 때는 timeout 조정:

```bash
python3 scripts/run_benchmarks.py --run-timeout 20 --build-timeout 30
```

harness 차이가 있으면 경고만 하지 말고 바로 실패 처리:

```bash
python3 scripts/run_benchmarks.py --fail-on-harness-diff
```

repo 동기화만 먼저 수행:

```bash
python3 scripts/sync_repos.py
```

이미 생성된 run 디렉터리 재집계:

```bash
python3 scripts/summarize_results.py --run-dir runs/20260412-120000
```

## 결과물

각 실행은 `runs/<timestamp>/` 아래에 저장된다.

- `run_config.json`
- `results.json`
- `summary.csv`
- `summary.md`
- `<alias>/`
  - `sync.json`
  - `harness_diffs.json`
  - `attempt-01.log`
  - `attempt-02.log`
  - ...

`summary.md` 에는 아래 항목이 포함된다.

- rank
- alias
- status
- harness
- correct
- util(%)
- Kops
- score
- perfidx
- branch
- commit
- repo_url

`score` 는 현재 `config.h`의 `UTIL_WEIGHT`, `AVG_LIBC_THRUPUT` 기준으로 계산되는 점수이며, `perfidx`와 같은 값이다.

## 상태값

- `OK`: 반복 실행이 안정적이고 `correct == 전체 trace 수`
- `INCORRECT`: 실행은 되었지만 correctness를 모두 통과하지 못함
- `UNSTABLE`: 반복 실행 중 correctness 또는 실행 상태가 흔들림
- `BUILD_FAIL`: `make` 실패
- `RUN_FAIL`: `mdriver` 실행 실패 또는 출력 파싱 실패
- `HARNESS_DIFF`: 기준 harness와 차이가 있어서, `--fail-on-harness-diff` 옵션으로 실패 처리됨
- `DIRTY_REPO`: clone 디렉터리가 dirty 상태라 안전하게 갱신할 수 없음
- `SYNC_FAIL`: clone/fetch/pull 실패
- `PARTICIPANT_ERROR`: `mm_path` 또는 lab 경로가 잘못됨

## 컨테이너 사용

이 저장소에는 원본 환경을 따라간 `.devcontainer/` 설정이 포함되어 있다.

- VSCode에서 이 저장소를 열고
- `Dev Containers: Reopen in Container`

로 열면, 같은 개발 환경에서 이 스크립트를 실행할 수 있다.

## 주의

- 원본 `malloc_lab_docker` 리포는 참조용이다.
- 이 도구는 원본 리포 안에서 빌드하지 않는다.
- clone 자체에서도 빌드하지 않고, 항상 `runs/` 아래의 복사본에서 실행한다.

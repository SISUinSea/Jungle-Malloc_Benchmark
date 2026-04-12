# Malloc Lab 점수 비교 자동화 계획

## 0. 전제

- 이 문서는 **계획만** 다룬다.
- 원본 분석 대상 리포는 `/Users/sisu/Projects/jungle/malloc_lab_docker` 이다.
- 원본 리포에서는 **절대로 구현 작업하지 않는다.**
- 실제 구현은 이 문서 검토 후 사용자가 `구현해도 좋아`라고 명시적으로 승인한 뒤에만 시작한다.

---

## 1. 현재 malloc lab 환경 분석

### 1.1 분석 대상 경로

- 원본 리포: `/Users/sisu/Projects/jungle/malloc_lab_docker`
- 실습 코드 경로: `/Users/sisu/Projects/jungle/malloc_lab_docker/malloc-lab`
- 현재 원본 리포 상태:
  - `git rev-parse HEAD` 결과: `1623ea6e5e99a2b65f38126f7824da67d24b4830`
  - 현재 remote: `https://github.com/SISUinSea/Jungle-Malloc_Lab.git`
  - 워크트리 dirty 상태:
    - `malloc-lab/mm.c` 수정됨
    - `malloc-lab/docs/` untracked
- 따라서 이후 자동화 구현 시에는 이 리포를 실행용 워크스페이스로 직접 쓰지 않고, **읽기 전용 기준 환경(reference)** 으로만 사용해야 한다.

### 1.2 컨테이너/개발 환경

- `.devcontainer/Dockerfile`
  - 베이스 이미지: `ubuntu:latest`
  - 설치 패키지: `build-essential`, `gcc`, `make`, `gdb`, `git`, `valgrind`, `python3` 등
  - 사용자: `jungle`
- `.devcontainer/devcontainer.json`
  - `remoteUser: jungle`
  - VSCode에서 동일한 C 개발 환경을 사용하도록 설정됨

의미:

- 이미 "같은 환경"을 맞추기 위한 컨테이너 정의가 존재한다.
- 점수 비교 자동화도 가능하면 이 컨테이너 정의를 기준으로 실행하는 것이 가장 자연스럽다.

### 1.3 빌드/실행 구조

- `malloc-lab/Makefile`
  - `make clean`
  - `make`
  - 산출물: `mdriver`
- `.vscode/tasks.json`
  - `make clean` 후 `make` 실행
- `.vscode/launch.json`
  - 디버깅 시 `malloc-lab` 디렉터리에서 `mdriver -V -f short1-bal.rep` 실행

의미:

- 표준 실행 진입점은 `malloc-lab/mdriver` 이다.
- 비교 자동화도 결국 각 후보 코드에 대해 `make clean && make && ./mdriver ...` 흐름을 반복하면 된다.

### 1.4 학생 제출물 경계

- `malloc-lab/README.md`에 따르면 학생이 수정해야 하는 핵심 파일은 `mm.c` 이다.
- `mm.h`에는 `mm_init`, `mm_malloc`, `mm_free`, `mm_realloc`, `team_t team` 인터페이스가 선언되어 있다.

의미:

- 모든 팀원이 같은 starter repo에서 시작했다는 전제를 두면, **각 팀원의 repo를 그대로 clone해서 같은 머신에서 빌드/실행하는 방식도 충분히 타당하다.**
- 다만 `README.md` 기준으로는 원래 학생이 수정해야 하는 파일이 `mm.c` 하나뿐이므로, **더 엄격하게 공정성을 보장하려면** 각 repo에서 `mm.c`만 가져와 동일한 driver/traces/config 위에서 측정하는 방식이 가장 안전하다.
- 팀원 repo 안에 `mdriver.c`, `config.h`, `Makefile`, trace가 우연히 바뀌어 있으면 점수 비교가 왜곡될 수 있으므로, 이 부분은 반드시 표준화해야 한다.

질문:

> 왜 `mm.c`만 추출하는 방식을 굳이 생각했나? 어차피 다 같은 repo에서 시작한 것 아닌가?

답변:

- 맞다. 모두가 같은 starter repo에서 시작했고 실제로 `mm.c`만 수정했다면, **repo 전체를 그대로 받아서 실행해도 된다.**
- 내가 `mm.c` 추출 방식을 먼저 제안한 이유는 "같은 출발점"과 "지금 최종 repo 상태가 완전히 동일한 채점 harness를 유지한다"는 것은 다른 문제이기 때문이다.
- 실제 점수는 `mm.c`만이 아니라 `mdriver.c`, `config.h`, `Makefile`, `traces/`의 영향도 받는다.
- 따라서 자동 비교를 더 엄격하게 만들고 싶다면 `mm.c`만 공통 harness에 꽂는 방식이 유리하다.
- 반대로 구현 단순성을 우선하면 `repo 전체 실행`이 더 낫다.

현재 계획에서의 정리:

- 1차 구현 기본안은 **repo 전체 실행**으로 잡아도 된다.
- 대신 `mdriver.c`, `config.h`, `Makefile`, `traces/`가 기준 harness와 다른지 검사해서 경고하는 안전장치를 두는 것이 좋다.
- 필요하면 이후에 **strict mode** 로 `mm.c`만 추출해 공통 harness에 주입하는 방식을 추가하면 된다.

### 1.5 점수 산출 방식

- `malloc-lab/config.h`
  - 기본 trace: 11개
  - `AVG_LIBC_THRUPUT = 600E3`
  - `UTIL_WEIGHT = .60`
  - `TRACEDIR = "./traces/"`
  - 타이머 방식: `USE_GETTOD = 1`
- `malloc-lab/mdriver.c`
  - `-g`: autograder용 요약 출력
    - `correct:<정답 trace 수>`
    - `perfidx:<점수>`
  - `-v`: trace별 util/ops/secs/Kops 및 Total 출력
  - `-l`: libc malloc도 같이 실행

실제 점수 공식:

```text
avg_mm_throughput = total_ops / total_secs
p1 = UTIL_WEIGHT * avg_mm_util
p2 = (1 - UTIL_WEIGHT) * min(avg_mm_throughput / AVG_LIBC_THRUPUT, 1)
perfindex = (p1 + p2) * 100
```

즉:

- 공간 활용도 비중: 60%
- throughput 비중: 40%
- throughput은 `600 Kops/sec` 기준으로 상한이 걸린다.

질문:

> 이게 무슨 뜻인가? 컴퓨터 성능이 좋아도 어느 정도 이상이면 상한이 있다고 이해하면 되나? 또 어떤 문서에서는 속도 비중이 더 크다고 하던데, 공식 문서와 실제 채점 코드가 다른가?

답변:

- 현재 로컬 채점 코드 기준으로는 **공간 활용도 60%, throughput 40%** 가 맞다.
- 근거는 `config.h`의 `UTIL_WEIGHT .60` 과 `mdriver.c`의 `p1 = UTIL_WEIGHT * avg_mm_util`, `p2 = (1 - UTIL_WEIGHT) * ...` 계산식이다.
- `AVG_LIBC_THRUPUT = 600E3` 이므로, 평균 throughput이 `600 Kops/sec`를 넘는 순간 throughput 항목은 만점 40점을 받는다.
- 따라서 "컴퓨터가 충분히 빨라서 throughput이 기준치를 넘기면, 그 이후로는 더 빨라도 throughput 점수가 더 오르지 않는다"라고 이해하면 된다.
- 단, 이것은 **점수 상한** 이지 실제 raw throughput 값이 같아진다는 뜻은 아니다.
- 예를 들어 `900 Kops/sec`와 `650 Kops/sec`는 raw throughput은 다르지만, throughput 점수 항목은 둘 다 40점이 될 수 있다.
- 그래서 자동 비교 결과에는 `perfidx`만이 아니라 `raw throughput(Kops)`도 반드시 같이 보여줘야 한다.
- 공식 과제 문서와 다르게 보이는 부분이 있더라도, **이 자동화 도구가 따라야 할 기준은 현재 실제로 실행되는 로컬 `mdriver.c`와 `config.h`** 이다.

현재 계획에서의 정리:

- 비교 결과 표에는 `perfidx`와 `throughput(Kops)`를 둘 다 포함한다.
- `perfidx`는 현재 로컬 채점 코드의 실제 계산식을 그대로 따른다.
- 문서 설명보다 실행 코드가 우선이다.

### 1.6 자동화 시 주의할 실제 관찰 사항

- 현재 `mdriver.c` 안에 디버깅 출력이 들어가 있다.
  - 옵션 파싱 루프 내부에 `printf("getopt returned: %d\\n", c);`
- `malloc-lab` 루트에 이미 `mdriver`, `*.o` 같은 빌드 산출물이 존재한다.

의미:

- 결과 파서가 순수한 출력만 가정하면 깨질 수 있다.
- 구현 시에는
  - 파서가 이 노이즈를 무시하거나,
  - 기준 harness를 정리한 뒤 그 버전을 사용해야 한다.

---

## 2. 문제를 해결하기 위한 핵심 방향

사용자가 원하는 목표는 다음 두 가지다.

1. 팀원들의 GitHub repo 링크를 한 파일에 모아 둔다.
2. 그 링크들을 기준으로 최신 상태를 가져와, 같은 환경에서 각자의 malloc lab 점수를 비교한다.

이 목표를 만족시키는 가장 공정한 방식은 아래와 같다.

- 팀원 repo는 **최신 제출물 동기화 소스** 로만 사용한다.
- 실제 측정은 **단일 기준 harness** 에서만 한다.
- 각 repo에서 `mm.c`를 가져와 같은 `mdriver`, 같은 `config.h`, 같은 trace 세트로 빌드/실행한다.
- 실행 환경도 가능하면 Docker/DevContainer 기반으로 고정한다.

이 방식이 필요한 이유:

- repo마다 driver를 수정했을 가능성 배제
- trace 세트 차이 배제
- Makefile 차이 배제
- 로컬 머신 자체는 한 대로 통일
- 패키지/컴파일러 버전도 컨테이너로 최대한 통일

---

## 3. 새로 만들 비교 전용 저장소의 방향

구현은 원본 리포가 아닌 **완전히 별도의 저장소** 에서 진행한다.

권장 디렉터리 구조 초안:

```text
malloc_lab_benchmark/
├── plan.md
├── participants.csv
├── benchmark_base/
│   └── malloc-lab/        # 표준 driver/config/traces/harness
├── repos/                # 팀원 repo clone 보관
├── runs/                 # 실행별 raw log / 요약 결과 저장
├── scripts/
│   ├── sync_repos.py
│   ├── run_benchmarks.py
│   └── summarize_results.py
└── README.md
```

중요 원칙:

- `malloc_lab_docker`는 참조만 하고 직접 수정하지 않는다.
- 실제 비교용 기준 harness는 새 저장소 안에 복제해 둔다.
- 팀원 repo clone도 새 저장소 내부에서 관리한다.
- 실행은 clone 디렉터리 자체가 아니라 `runs/<timestamp>/...` 같은 별도 작업 디렉터리에서 수행한다.

---

## 4. 팀원 GitHub 링크를 넣을 파일

### 4.1 파일명 제안

- 루트에 `participants.csv`

이 파일 하나만 수정하면 되도록 설계한다.

### 4.2 형식 제안

```csv
alias,repo_url,branch,mm_path,enabled
haegeon,https://github.com/user1/malloc-lab.git,main,malloc-lab/mm.c,true
minsu,https://github.com/user2/malloc-lab.git,main,malloc-lab/mm.c,true
```

### 4.3 컬럼 의미

- `alias`
  - 결과 표시에 쓸 짧은 이름
  - 로컬 clone 디렉터리명으로도 사용
- `repo_url`
  - 팀원 GitHub repo 주소
- `branch`
  - 비교 대상으로 쓸 브랜치
  - 비워 두면 기본 브랜치 사용
- `mm_path`
  - repo 내부에서 학생 제출 `mm.c`가 있는 경로
  - 표준 구조면 `malloc-lab/mm.c`
- `enabled`
  - 일시적으로 제외할 때 사용

CSV를 택한 이유:

- 사람이 열어 수정하기 쉽다.
- Python 표준 라이브러리만으로 쉽게 파싱 가능하다.
- 나중에 `branch`, `mm_path` 같은 예외 케이스를 처리할 수 있다.

---

## 5. 자동화 실행 흐름 계획

### 5.1 1단계: 참가자 repo 동기화

입력:

- `participants.csv`

처리:

1. 각 참가자의 `alias`, `repo_url`, `branch`, `mm_path`를 읽는다.
2. 로컬 clone 경로를 `repos/<alias>` 로 정한다.
3. clone이 없으면 새로 clone 한다.
4. clone이 있으면 `fetch` 해서 최신 상태를 가져온다.
5. 지정 브랜치 또는 기본 브랜치로 맞춘 뒤 `pull --ff-only` 로 최신화한다.
6. 각 참가자 repo의 현재 commit hash를 기록한다.

주의 사항:

- clone 디렉터리가 dirty면 자동 비교 신뢰성이 떨어진다.
- 따라서 기본 정책은 아래 둘 중 하나로 정해야 한다.
  - 정책 A: dirty면 실패 처리하고 사용자에게 알려준다.
  - 정책 B: 자동화가 관리하는 clone이라 가정하고 재clone 한다.

권장:

- 1차 구현은 **정책 A(안전 우선)** 로 간다.
- 나중에 필요하면 `--force-refresh` 같은 옵션으로 정책 B를 추가한다.

### 5.2 2단계: 표준 benchmark 작업 디렉터리 생성

각 참가자마다 아래 작업을 한다.

1. `runs/<timestamp>/<alias>/malloc-lab` 작업 디렉터리를 만든다.
2. `benchmark_base/malloc-lab`의 내용을 그 디렉터리로 복사한다.
3. 참가자 repo에서 `mm_path`의 `mm.c`를 찾아 표준 harness의 `mm.c`를 덮어쓴다.
4. 필요하면 참가자 repo의 commit hash와 repo URL을 메타데이터로 저장한다.

왜 이렇게 하는가:

- 팀원 repo 안에서 직접 빌드하면 repo 자체가 더러워진다.
- 이전 참가자의 빌드 산출물이 다음 참가자에게 영향을 줄 수 있다.
- 매 참가자를 독립된 작업 디렉터리에서 실행해야 교차 오염이 없다.

### 5.3 3단계: 빌드

각 참가자 작업 디렉터리에서:

1. `make clean`
2. `make`

기록할 것:

- 빌드 성공 여부
- 빌드 stderr/stdout 로그
- 빌드 실패 시 실패 원인

실패 처리:

- 빌드 실패 참가자는 점수 집계에서 제외하지 말고 **실패 상태** 로 표시한다.
- 표에는 `BUILD_FAIL` 등으로 남겨야 한다.

### 5.4 4단계: 점수 측정

각 참가자 작업 디렉터리에서:

- 기본 실행 후보:

```bash
./mdriver -v -g
```

이 명령에서 얻을 수 있는 정보:

- `-v`:
  - trace별 util/ops/secs/Kops
  - Total util/ops/secs/Kops
- `-g`:
  - `correct:<n>`
  - `perfidx:<score>`

파서가 추출해야 할 최소 필드:

- `correct`
- `perfidx`
- `Total util`
- `Total ops`
- `Total secs`
- `Total Kops`

주의:

- 현재 기준 `mdriver.c`에는 `getopt returned: ...` 라인이 끼어들 수 있으므로, 파서는 이 라인을 무시하도록 설계해야 한다.

### 5.5 5단계: 반복 측정으로 노이즈 완화

같은 머신이어도 throughput은 실행 시점에 따라 약간 흔들릴 수 있다.

따라서 1회 측정으로 끝내지 않고:

- 기본 3회 또는 5회 반복 측정
- 최종 비교값은 `perfidx`와 `Kops`의 **중앙값(median)** 을 사용

권장 집계:

- `util`: 첫 실행값 또는 중앙값
- `throughput(Kops)`: 중앙값
- `perfidx`: 중앙값
- `correct`: 모든 반복에서 동일해야 함

불일치 감지:

- 어떤 참가자가 반복 실행에서 `correct` 값이 달라지면 불안정 구현으로 표시

### 5.6 6단계: 결과 집계 및 출력

최종적으로 보여줘야 하는 항목:

- 순위
- alias
- repo URL
- branch
- commit hash
- correctness (`correct/11`)
- util(%)
- throughput(Kops)
- perf index
- 상태 (`OK`, `BUILD_FAIL`, `RUN_FAIL`, `UNSTABLE` 등)

출력 형태:

- 터미널 표
- `runs/<timestamp>/summary.csv`
- `runs/<timestamp>/summary.md`
- `runs/<timestamp>/<alias>/raw.log`

정렬 기준 권장:

1. `status == OK` 우선
2. `perfidx` 내림차순
3. `throughput` 내림차순

---

## 6. 왜 "repo 전체를 그대로 실행"하지 않고 "mm.c만 추출"해야 하는가

이 부분은 계획에서 명확히 고정해야 한다.

repo 전체 실행 방식의 문제:

- `mdriver.c`를 수정한 repo가 있을 수 있음
- `config.h`를 수정해 trace 또는 가중치를 바꿨을 수 있음
- `Makefile`을 수정해 다른 플래그가 들어갔을 수 있음
- 실수로 trace 파일이 바뀌었을 수 있음

그러면 "같은 머신"이어도 사실상 **다른 시험지** 를 푸는 셈이 된다.

따라서 비교 대상은:

- 팀원 repo의 최신 제출 `mm.c`

비교 기준은:

- 단일 기준 harness (`mdriver.c`, `config.h`, `traces`, `Makefile`)

이렇게 분리해야 점수 비교가 의미를 가진다.

---

## 7. 실행 환경 표준화 방안

### 7.1 1순위: Docker/DevContainer 기반 실행

이유:

- 현재 원본 리포가 이미 Docker/DevContainer 중심으로 설계되어 있다.
- gcc, make, libc, timer 환경 차이를 줄일 수 있다.

계획:

- 새 benchmark 저장소에도 동일하거나 거의 동일한 Docker 환경을 둔다.
- 모든 참가자 코드는 같은 컨테이너 안에서 빌드/실행한다.

### 7.2 2순위: 로컬 직접 실행

Docker를 쓸 수 없는 상황을 대비한 fallback 모드.

단점:

- OS/패키지 버전 차이가 비교 결과에 영향을 줄 수 있다.

정리:

- 기본 모드는 컨테이너
- fallback만 로컬 실행

---

## 8. 구현 시 예상 세부 산출물

구현 승인 후 만들어질 가능성이 높은 것들:

1. `participants.csv`
2. 표준 harness 복제본
3. repo 동기화 스크립트
4. benchmark 실행 스크립트
5. 결과 요약 스크립트
6. 사용법 문서

하지만 현재 단계에서는 **어떤 스크립트도 작성하지 않는다.**

---

## 9. 구현 순서 제안

### Phase 1. 기준 harness 고정

- 원본 `malloc_lab_docker/malloc-lab`에서 비교에 필요한 파일 집합을 확정
- 새 저장소 안으로 복제
- 빌드 산출물(`mdriver`, `*.o`)은 제외
- `mdriver.c`의 디버그 출력 처리 방침 결정

### Phase 2. 참가자 목록 입력

- `participants.csv` 포맷 확정
- 예시 파일 제공
- path/branch 예외 처리 방침 확정

### Phase 3. repo 동기화

- clone / fetch / pull / branch checkout
- commit hash 수집
- dirty 상태 감지

### Phase 4. 단일 참가자 benchmark

- 작업 디렉터리 생성
- 표준 harness 복사
- 참가자 `mm.c` 주입
- `make clean && make`
- `./mdriver -v -g`

### Phase 5. 다중 참가자 benchmark

- 모든 참가자 반복 실행
- raw log 저장
- build/run 실패 처리

### Phase 6. 결과 집계/정렬

- 중앙값 계산
- 순위표 생성
- CSV/Markdown 출력

### Phase 7. 문서화

- 사용법
- 입력 파일 작성법
- 결과 해석법
- 한계점 명시

---

## 10. 검증 기준

구현이 끝났다고 판단하려면 최소한 아래가 만족되어야 한다.

1. `participants.csv`에 repo 링크를 추가하면 별도 수작업 없이 최신 상태 동기화가 된다.
2. 각 repo에서 지정한 `mm.c`를 가져와 동일한 harness에서 빌드한다.
3. 빌드 실패/실행 실패/정상 완료가 구분되어 표시된다.
4. 결과 표에 최소 `correct`, `util`, `throughput`, `perfidx`가 나온다.
5. 같은 참가자를 여러 번 돌렸을 때 반복 측정 결과와 최종 대표값이 저장된다.
6. 원본 `malloc_lab_docker` 리포는 전혀 수정되지 않는다.

---

## 11. 리스크 및 결정해야 할 사항

### 이미 확인된 리스크

- 현재 기준 리포 자체가 dirty 상태다.
- 현재 `mdriver.c`에 디버그 출력이 들어가 있다.
- 팀원 repo마다 기본 브랜치가 다를 수 있다.
- `mm.c` 경로가 다를 수 있다.
- public/private repo 여부에 따라 인증 방식이 달라질 수 있다.

### 구현 전에 확정하면 좋은 결정

1. 참가자 목록 파일 이름을 `participants.csv`로 확정할지
2. 기본 실행 모드를 Docker로 할지
3. 반복 측정 횟수를 3회로 할지 5회로 할지
4. dirty clone 발견 시 실패 처리할지 재clone할지
5. 기준 harness에 포함할 `mdriver.c`를 현재 버전 그대로 둘지, 디버그 출력 없는 정리 버전으로 둘지

---

## 12. 최종 권장안

가장 권장하는 구현 방향은 아래 한 줄로 정리된다.

> 팀원 repo는 최신 `mm.c`를 가져오는 용도로만 쓰고, 실제 점수 측정은 새 저장소 안의 표준 `malloc-lab` harness를 같은 Docker 환경에서 반복 실행해 중앙값 기준으로 비교한다.

이 방향이면 사용자가 원한 두 가지를 모두 만족한다.

- 한 파일(`participants.csv`)에 GitHub 링크를 모을 수 있음
- 같은 머신, 같은 환경, 같은 driver 기준으로 점수를 비교할 수 있음

---

## 13. 현재 이 문서 작성 결과

- 별도 디렉터리에서 Git 저장소 초기화 완료
- 계획 문서 작성 완료
- 구현 작업은 **시작하지 않음**

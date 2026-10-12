# 전역도우미 (jeonyeok_helper)

전역자가 자기 상황을 말하면 **받을 수 있는 혜택, 근거 규정, 신청처**를 한 번에 알려주는 AI 에이전트입니다.

- **규정 Q&A**: 법령, 행정규칙, 법령해석례, 지자체 조례, 국가보훈부 자료를 RAG로 검색해 근거 조문과 함께 답변
- **맞춤 혜택 찾기**: 복무 형태, 기간, 나이, 지역에 맞는 공공서비스 혜택 조회
- **기관 연계**: 소관 기관, 신청 방법, 링크, 연락처 안내
- **전역 로드맵**: 복무 정보를 한 번 고르면 전역 직후부터 취업·학업·연금까지 할 일을 시기별 체크리스트로 정리

자세한 내용은 [기획서](docs/기획서.md), [개발 순서](docs/개발순서.md), [작업 기록](docs/작업기록.md)을 참고하세요.

## 화면

| 첫 화면 | 답변 화면 |
|---|---|
| ![첫 화면](docs/screenshots/home-light.png) | ![답변 화면](docs/screenshots/answer-light.png) |

| 모바일 | 모바일 메뉴 | 다크 모드 |
|---|---|---|
| ![모바일 답변 화면](docs/screenshots/answer-mobile.jpg) | ![모바일 메뉴](docs/screenshots/menu-mobile.jpg) | ![다크 모드 답변 화면](docs/screenshots/answer-dark.png) |

> 데모 모드 화면입니다. 백엔드에 Gemini 키가 없으면 자동으로 데모 모드로 열려 예시 응답을 보여줍니다. `?q=질문` 주소로 들어오면 바로 질문합니다.

## 구조

```
브라우저 ─▶ Next.js (frontend) ─/api/*─▶ FastAPI (backend) ─▶ 슈퍼바이저 (Gemini, LangGraph)
                                                                ├─ 규정 에이전트     (RAG)
                                                                ├─ 혜택 에이전트     (MCP → 공공서비스 API)
                                                                └─ 기관연계 에이전트
                                                             ─▶ 근거 검증 ─▶ 답변 (SSE 스트리밍)
```

| 영역 | 기술 |
|---|---|
| 화면 | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4 |
| LLM | Gemini |
| 에이전트 | LangChain, LangGraph |
| 평가 | 답변 평가 41문항 + 규정 검색 골든셋 69문항 (`jeonyeok-eval`, `--retrieval`) |
| 도구 연동 | MCP |
| RAG | PostgreSQL + pgvector, HyDE, Re-ranking |
| 서버 | FastAPI (SSE), PostgreSQL (벡터 검색·피드백, SQLAlchemy 2.0 + Alembic), SQLite (대화 기록·프로필) |
| 배포 | Docker Compose, GitHub Actions |

## 폴더

```
backend/                      # Python (uv)
├─ src/jeonyeok_helper/
│  ├─ rag/                    # 법령·문서 수집과 검색
│  ├─ benefits/               # 공공서비스 API, 기관 링크, MCP 서버
│  ├─ agents/                 # LangGraph 슈퍼바이저와 워커
│  ├─ api/                    # FastAPI
│  └─ evaluation.py           # 평가
├─ tests/
└─ data/                      # 수집 법령 목록, 기관 목록, 평가 질문
frontend/                     # Next.js
├─ src/app/                   # 페이지, /api/* 프록시
├─ src/components/            # 화면 컴포넌트
└─ src/lib/                   # SSE 처리, 답변 해석, 데모 응답
docs/
docker-compose.yml
```

## 시작하기

### Docker로 한 번에

```bash
cp backend/.env.example backend/.env   # 키 입력
docker compose up --build              # http://localhost:3000
```

### 개발 모드

백엔드 ([uv](https://docs.astral.sh/uv/), Docker 필요):

```bash
docker compose up -d db    # PostgreSQL(pgvector), localhost:5432
cd backend
uv sync
cp .env.example .env
uv run jeonyeok-serve      # http://127.0.0.1:8000
```

프론트엔드 (Node 24):

```bash
cd frontend
npm install
npm run dev                # http://localhost:3000, /api/* 는 API_URL(기본 127.0.0.1:8000)로 전달
```

## 백엔드 명령

| 명령 | 설명 |
|---|---|
| `uv run jeonyeok-rag laws` | `data/laws.yaml`의 법령·행정규칙(훈령·고시) 수집 (LAW_API_OC 필요) |
| `uv run jeonyeok-rag ordinances` | `data/ordinances.yaml` 기준 지자체 조례 수집 (LAW_API_OC 필요) |
| `uv run jeonyeok-rag interpretations` | `data/interpretations.yaml` 기준 국가보훈부·국방부·병무청·법제처 법령해석례 수집 |
| `uv run jeonyeok-rag datasets` | 공공데이터 CSV(보훈 민원·구비서류, 장학금) 수집, 파일이 없으면 data.go.kr에서 내려받음 |
| `uv run jeonyeok-rag files` | `data/raw/`의 PDF·TXT·MD 수집 (HWP는 PDF로 변환, 글자 없는 PDF는 Gemini로 옮겨 적음) |
| `uv run jeonyeok-rag web` | `data/webpages.yaml`의 기관 안내 페이지(국가보훈부·국방부·국민연금·고용24) 수집 |
| `uv run jeonyeok-rag search "질문" [--region 부산]` | HyDE + Re-ranking 검색 결과 확인 (지역을 주면 그 지역 조례 포함) |
| `uv run jeonyeok-mcp` | MCP 서버 (stdio) |
| `uv run jeonyeok-chat` | 터미널에서 에이전트와 대화 |
| `uv run jeonyeok-eval` | 평가 40문항 채점, `data/eval/results/`에 보고서 |
| `uv run jeonyeok-eval --retrieval [--ablation]` | 규정 검색 골든셋(Hit@k·Recall@k·MRR), 검색 설정 비교 |

### API

| API | 설명 |
|---|---|
| `POST /chat` | `{message, thread_id?, user_id?}` → SSE (`thread`, `step`, `answer` / `question`, `error`, `done`) |
| `GET /profile/{user_id}` | 저장된 사용자 프로필 |
| `POST /roadmap` | `{service_type, region?, age?, service_years?}` → 시기별 할 일 목록 (할 일마다 근거 자료와 링크) |
| `POST /feedback` | 답변 피드백 저장 `{rating: up/down, question, answer, comment?}` |
| `GET /feedback/summary` | 피드백 수 (화면 프록시로는 열지 않음) |
| `GET /health` | 상태, 에이전트 준비 여부, 키 설정 여부 |

### MCP 도구

| 도구 | 하는 일 |
|---|---|
| `search_regulations` | 법령·보훈부 자료에서 근거 조문 검색, 지역을 주면 그 지역 조례도 |
| `search_benefits` | 정부24 공공서비스(혜택)에서 전역자 혜택 조회, 지역 필터 |
| `get_benefit_detail` | 혜택의 선정기준, 구비서류, 신청방법 |
| `search_youth_policies` | 온통청년 청년정책 3,000여 건, 지역·나이·키워드 필터, 군 복무 관련 정책 우선 |
| `search_jobs` | 제대군인지원센터(브이넷) 마감 전 채용공고, 지역·키워드 필터 (키 불필요) |
| `search_veteran_jobs` | 국가보훈부 보훈관서 채용정보: 보훈특별고용·공무원 특별채용 마감 전 공고 (키 불필요) |
| `find_stores` | 병무청 나라사랑가게(예비군 훈련 이수자·현역병 할인) 지역별 목록 |
| `find_veterans_office` | 관할 지방보훈청·보훈지청 27곳 주소·전화 ([veterans_offices.yaml](backend/data/veterans_offices.yaml)) |
| `find_hospitals` | 지역별 보훈 위탁병원(국가유공자 진료비 감면) 주소·전화·지도 링크 |
| `find_institutions` | 주제별 기관 사이트·연락처 ([institutions.yaml](backend/data/institutions.yaml)) |

API 키가 없거나 호출이 실패하면 오류 대신 정부24, 온통청년 등 직접 찾아볼 수 있는 기관 링크를 돌려줍니다. Claude Desktop 같은 MCP 클라이언트에는 아래처럼 연결합니다.

```json
{
  "mcpServers": {
    "jeonyeok_helper": {
      "command": "uv",
      "args": ["--directory", "<레포 경로>/backend", "run", "jeonyeok-mcp"]
    }
  }
}
```

### 에이전트 흐름

```
start → profile(복무 정보 추출) → supervisor ─┬→ regulation / benefit / institution → supervisor
                                              ├→ ask_user (정보가 부족하면 되묻기)
                                              └→ respond(답변 초안) → verify(근거 검증)
```

## 테스트

```bash
cd backend && uv run pytest && uv run ruff check .
cd frontend && npm test && npm run lint && npm run typecheck
```

## 필요한 키 (`backend/.env`)

| 키 | 발급처 | 용도 |
|---|---|---|
| `GOOGLE_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) | Gemini |
| `LAW_API_OC` | [국가법령정보센터 Open API](https://open.law.go.kr) | 법령, 조례 수집 |
| `DATA_GO_KR_SERVICE_KEY` | [공공데이터포털](https://www.data.go.kr) | 공공서비스(혜택), 보훈 위탁병원, 나라사랑가게 |
| `YOUTHCENTER_API_KEY` | [온통청년](https://www.youthcenter.go.kr) (마이페이지 > OPEN API) | 청년정책 |

## 안내

이 서비스의 답변은 참고용입니다. 실제 자격과 신청 방법은 소관 기관에 꼭 확인하세요.

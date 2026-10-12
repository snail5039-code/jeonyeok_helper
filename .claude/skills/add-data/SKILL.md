---
name: add-data
description: 전역도우미에 검색 자료를 추가한다 — 사용자가 준 PDF·문서(글자 없는 스캔본 포함), 새 법령·행정규칙, 공공데이터. "이 파일 넣어줘", "자료 추가", "이 법도 넣어", "검색이 잘 안 돼" 같은 요청에 쓴다.
---

# 검색 자료 추가

전역도우미(backend/)의 RAG 자료를 늘리는 절차. 명령은 모두 `backend/`에서 `uv run`으로 실행한다.
키 값(.env)은 절대 출력하지 말고 설정 여부만 확인한다.

## 0. 먼저 확인

- **이미 있는 자료인지**: `data/raw/`의 파일과 MD5 해시를 비교한다
  (`Get-FileHash -Algorithm MD5`). 이름만 다르고 같은 파일인 경우가 있었다.
- **실시간 도구에 이미 있는지**: 장학금·학자금처럼 정부24 API(search_benefits)에 이미 있는
  내용은 파일로 넣지 말고 검색어(keywords)가 닿는지부터 본다.
- 사이트 이용약관 동의가 필요한 파일은 대신 받지 말고 사용자에게 받아 달라고 한다.

## 1. 파일(PDF, TXT, MD)

1. 발행 기관과 연도가 드러나게 이름을 바꿔 `data/raw/`에 복사한다
   (예: `국방전직교육원_2025년_전직교육안내서.pdf`). 이름이 곧 출처 표시(citation)가 된다.
   HWP는 PDF로 바꿔 달라고 한다.
2. 글자 정보가 있는지 확인한다:
   ```bash
   uv run python -c "from pathlib import Path; from jeonyeok_helper.rag.transcribe import has_text; print(has_text(Path('data/raw/파일.pdf')))"
   ```
   - `False`(스캔본, 글자를 도형으로 바꾼 인쇄용 파일)면 `jeonyeok-rag files`가 Gemini로 한 쪽씩
     옮겨 적어 `data/raw/.transcripts/<파일명>.md`에 저장한다 (30쪽에 약 5분). 한 번만 한다.
   - 옮겨 적은 글의 앞부분과 표를 열어 빠진 내용이 없는지 눈으로 확인한다.
3. 수집: 파일 하나만 넣을 때는 전체를 다시 임베딩하지 않도록 이렇게 한다.
   ```bash
   uv run python -c "from pathlib import Path; from jeonyeok_helper.rag.loaders import load_file; from jeonyeok_helper.rag.store import RegulationStore; s=RegulationStore(); print(s.upsert(load_file(Path('data/raw/파일.pdf'))))"
   ```
   폴더 전체는 `uv run jeonyeok-rag files`.

## 2. 법령·행정규칙

1. 질문에 답할 근거 조문이 어느 법에 있는지 찾는다. 큰 법은 관련 조문만 고른다:
   법령을 `LawApiClient(...).load_law(이름)`으로 받아 '군 복무', '병역', '현역' 등으로 걸러 본다.
2. `data/laws.yaml`에 추가한다. 이름은 국가법령정보센터 정식 명칭과 정확히 같아야 하고,
   큰 법은 `articles: [제40조, ...]`로 조문을 고른다. 훈령·고시는 `admin_rules`에.
3. 새로 넣은 것만 수집: `ingest_laws(client, store, [새 항목들])` (전체는 `jeonyeok-rag laws`).
   조례는 `data/ordinances.yaml`, 해석례는 `data/interpretations.yaml` 후 각 명령.

## 3. 확인 (꼭)

1. 그 자료로 답해야 할 질문으로 검색해 상위에 나오는지 본다:
   `uv run jeonyeok-rag search "질문" [--region 부산]`
2. 자료를 크게 늘렸으면 **전체 평가를 다시 돌린다**: `uv run jeonyeok-eval`.
   큰 문서가 법령 근거를 밀어내 24/30까지 떨어진 적이 있다 (검색은 같은 문서 2개까지로 제한 중).
3. `uv run pytest -q`, `uv run ruff check src tests`.

## 4. 기록

- `docs/작업기록.md`의 '한눈에 보기' 자료 수와 해당 날짜 표, README의 자료 목록을 고친다.
- `data/raw/`와 `.transcripts/`는 git에 올라가지 않는다(원본 파일). laws.yaml 같은 목록 파일은 커밋한다.

## 알아 둘 것

- 2026년부터 전남·광주는 '전남광주통합특별시'. 자료마다 '전남광주통합', '(구)광주', 청년정책
  지역 코드 12로 다르게 적혀 있다. 지역 관련 코드는 `benefits/regions.py`에 모여 있다.
- Windows 한글 경로라 Chroma는 `%LOCALAPPDATA%\jeonyeok_helper\chroma`에 저장된다.

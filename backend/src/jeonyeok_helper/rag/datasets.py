"""공공데이터포털 파일데이터(CSV) → 규정 검색용 Document.

    uv run jeonyeok-rag datasets            # data/datasets/의 CSV를 수집 (없으면 내려받기)

- 파일은 data/datasets/<이름>.csv에 둔다 (Git에는 올리지 않음).
- 내려받기: 데이터 상세 페이지 → 첨부파일 ID 조회 → 파일 다운로드. 첨부파일 ID는 데이터가
  갱신될 때마다 바뀌어서 매번 상세 페이지에서 찾는다.
- 행 하나 = 문서 하나. 원본 CSV는 CP949인 경우가 많다.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from langchain_core.documents import Document

from jeonyeok_helper.config import DATA_DIR

DATASETS_DIR = DATA_DIR / "datasets"
PORTAL = "https://www.data.go.kr"


def read_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"CSV 인코딩을 알 수 없습니다: {path.name}")
    return [
        {k.strip(): (v or "").strip() for k, v in row.items() if k}
        for row in csv.DictReader(io.StringIO(text))
    ]


def _lines(row: dict[str, str], fields: list[tuple[str, str]]) -> list[str]:
    """('보여줄 이름', 'CSV 열') 목록에서 값이 있는 것만 '이름: 값' 줄로."""
    skip = {"", "해당없음", "-"}
    return [f"{label}: {row[col]}" for label, col in fields if row.get(col, "") not in skip]


# ---------- 국가보훈부 보훈 관련 민원사무 및 구비서류 목록 ----------


def civil_affair_to_document(row: dict[str, str]) -> Document | None:
    name = row.get("사무명", "")
    if not name:
        return None
    body = _lines(
        row,
        [
            ("개요", "사무개요"),
            ("신청자 자격", "신청자 자격"),
            ("접수 방법", "접수방법"),
            ("수수료", "수수료"),
            ("문의", "문의처"),
            ("근거 법령", "근거법령"),
            ("구비서류", "구비서류"),
        ],
    )
    return Document(
        page_content="\n".join([f"[국가보훈부 민원] {name}", *body]),
        metadata={
            "source_type": "dataset",
            "law_name": name,
            "citation": f"국가보훈부 민원 안내: {name}",
            "url": row.get("정부24 안내 주소", ""),
            "doc_id": f"civil:{row.get('연번', name)}",
        },
    )


# ---------- 한국장학재단 학자금지원정보(대학생) ----------

# 지자체 장학금(약 1,000건)은 운영기관 지역을 안정적으로 알 수 없어 지역 필터를 못 건다.
# 전국 대상(장학재단·공공기관)과 군·보훈 관련 자격이 있는 장학금만 넣는다.
NATIONAL_OPERATORS = {"한국장학재단", "공공기관"}
VETERAN_WORDS = re.compile(r"제대군인|전역|병역|군\s?복무|군인|장병|보훈|국가유공자|참전")


def scholarship_to_document(row: dict[str, str]) -> Document | None:
    name = row.get("상품명", "")
    operator = row.get("운영기관명", "")
    qualification = " ".join(row.get(k, "") for k in ("특정자격 상세내용", "상품명"))
    if not name or not (
        row.get("운영기관구분") in NATIONAL_OPERATORS or VETERAN_WORDS.search(qualification)
    ):
        return None
    period = f"{row.get('모집시작일', '')} ~ {row.get('모집종료일', '')}".strip(" ~")
    body = _lines(
        row,
        [
            ("구분", "학자금유형구분"),
            ("대상 학교", "대학구분"),
            ("성적 기준", "성적기준 상세내용"),
            ("소득 기준", "소득기준 상세내용"),
            ("지원 내용", "지원내역 상세내용"),
            ("특정 자격", "특정자격 상세내용"),
            ("선발 방법", "선발방법 상세내용"),
            ("제출 서류", "제출서류 상세내용"),
        ],
    )
    return Document(
        page_content="\n".join([f"[장학금] {name} ({operator})", *body, f"모집 기간: {period}"]),
        metadata={
            "source_type": "dataset",
            "law_name": name,
            "citation": f"{operator} {name}",
            "url": row.get("홈페이지 주소", ""),
            "enforced_at": row.get("모집시작일", ""),
            "doc_id": f"scholarship:{row.get('번호', '').strip()}:{name}",
        },
    )


# ---------- 국가보훈부 보훈행정용어집 ----------
# '상이처', '전공사상'처럼 안내문에 나오는 보훈 행정 용어 165개의 뜻.


def glossary_to_document(row: dict[str, str]) -> Document | None:
    term, meaning = row.get("표제어", ""), row.get("의미", "")
    if not term or not meaning:
        return None
    body = _lines(row, [("분야", "구분"), ("참조", "참조")])
    return Document(
        page_content="\n".join([f"[보훈행정용어] {term}", meaning, *body]),
        metadata={
            "source_type": "dataset",
            "law_name": f"보훈행정용어 {term}",
            "citation": f"국가보훈부 보훈행정용어집: {term}",
            "url": f"{PORTAL}/data/15043334/fileData.do",
            "doc_id": f"glossary:{row.get('번호', term)}",
        },
    )


@dataclass(frozen=True)
class Dataset:
    name: str
    public_data_pk: str  # data.go.kr/data/<번호>/fileData.do
    title: str
    to_document: Callable[[dict[str, str]], Document | None]


DATASETS = [
    Dataset(
        "mpva_civil",
        "15134958",
        "국가보훈부 보훈 관련 민원사무 및 구비서류",
        civil_affair_to_document,
    ),
    Dataset(
        "scholarship", "15028252", "한국장학재단 학자금지원정보(대학생)", scholarship_to_document
    ),
    Dataset("mpva_glossary", "15043334", "국가보훈부 보훈행정용어집", glossary_to_document),
]


def download(dataset: Dataset, dest: Path, client: httpx.Client | None = None) -> Path:
    """data.go.kr 파일데이터를 내려받는다 (로그인 불필요)."""
    http = client or httpx.Client(timeout=60, follow_redirects=True)
    page = http.get(f"{PORTAL}/data/{dataset.public_data_pk}/fileData.do").text
    m = re.search(r'id="publicDataDetailPk"[^>]*value="([^"]+)"', page)
    if not m:
        raise LookupError(f"데이터 상세 정보를 찾지 못했습니다: {dataset.title}")
    info = http.get(
        f"{PORTAL}/tcs/dss/selectFileDataDownload.do",
        params={
            "publicDataPk": dataset.public_data_pk,
            "fileDetailSn": 1,
            "publicDataDetailPk": m[1],
        },
    ).json()
    file_id = info.get("atchFileId")
    if not file_id:
        raise LookupError(f"포털에서 바로 받을 수 없는 데이터입니다: {dataset.title}")
    resp = http.get(
        f"{PORTAL}/cmm/cmm/fileDownload.do",
        params={"atchFileId": file_id, "fileDetailSn": info.get("fileDetailSn") or 1},
    )
    resp.raise_for_status()
    if not resp.content or resp.headers.get("content-type", "").startswith("text/html"):
        raise LookupError(f"파일을 받지 못했습니다: {dataset.title}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def load_datasets(
    directory: Path = DATASETS_DIR, fetch: bool = True
) -> tuple[list[Document], list[str]]:
    """(문서, 메시지). 파일이 없으면 fetch=True일 때 내려받는다."""
    docs: list[Document] = []
    notes: list[str] = []
    for ds in DATASETS:
        path = directory / f"{ds.name}.csv"
        if not path.exists():
            if not fetch:
                notes.append(f"{ds.title}: 파일 없음 ({path.name})")
                continue
            download(ds, path)
            notes.append(f"{ds.title}: 내려받음")
        rows = read_csv(path)
        made = [d for d in map(ds.to_document, rows) if d is not None]
        docs += made
        notes.append(f"{ds.title}: {len(rows)}행 중 {len(made)}건")
    return docs, notes

"""국가법령정보센터 Open API(DRF)로 법령 본문을 받아 조문 단위 Document로 변환.

- 검색: https://www.law.go.kr/DRF/lawSearch.do?target=law&type=JSON&query=...
- 본문: https://www.law.go.kr/DRF/lawService.do?target=law&type=JSON&MST=...
- 자치법규(조례)는 target=ordin으로 같은 주소를 쓴다.

응답 JSON은 항목이 하나면 dict, 여러 개면 list로 오는 경우가 많아서 `_as_list`로 맞춘다.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from langchain_core.documents import Document

BASE_URL = "https://www.law.go.kr/DRF"


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _collect_text(node: Any) -> list[str]:
    """항/호/목처럼 중첩된 구조에서 '...내용' 필드의 문자열을 순서대로 모은다."""
    texts: list[str] = []
    if isinstance(node, str):
        if node.strip():
            texts.append(node.strip())
    elif isinstance(node, list):
        for item in node:
            texts.extend(_collect_text(item))
    elif isinstance(node, dict):
        for key, val in node.items():
            if key.endswith("내용"):
                texts.extend(_collect_text(val))
        for child in ("항", "호", "목"):
            if child in node:
                texts.extend(_collect_text(node[child]))
    return texts


class LawApiClient:
    def __init__(self, oc: str, client: httpx.Client | None = None):
        if not oc:
            raise RuntimeError("LAW_API_OC가 설정되지 않았습니다. open.law.go.kr에서 신청하세요.")
        self.oc = oc
        self.client = client or httpx.Client(timeout=30)

    def search(self, query: str) -> list[dict]:
        resp = self.client.get(
            f"{BASE_URL}/lawSearch.do",
            params={"OC": self.oc, "target": "law", "type": "JSON", "query": query},
        )
        resp.raise_for_status()
        return _as_list(resp.json().get("LawSearch", {}).get("law"))

    def find_current(self, law_name: str) -> dict | None:
        """이름이 정확히 일치하는 현행 법령 1건. 없으면 None."""
        for item in self.search(law_name):
            if item.get("법령명한글") == law_name and item.get("현행연혁코드", "현행") == "현행":
                return item
        return None

    def fetch(self, mst: str) -> dict:
        resp = self.client.get(
            f"{BASE_URL}/lawService.do",
            params={"OC": self.oc, "target": "law", "type": "JSON", "MST": mst},
        )
        resp.raise_for_status()
        return resp.json()

    def search_ordinances(self, query: str, page: int = 1, display: int = 100) -> list[dict]:
        resp = self.client.get(
            f"{BASE_URL}/lawSearch.do",
            params={
                "OC": self.oc,
                "target": "ordin",
                "type": "JSON",
                "query": query,
                "display": display,
                "page": page,
            },
        )
        resp.raise_for_status()
        return _as_list(resp.json().get("OrdinSearch", {}).get("law"))

    def fetch_ordinance(self, mst: str) -> dict:
        resp = self.client.get(
            f"{BASE_URL}/lawService.do",
            params={"OC": self.oc, "target": "ordin", "type": "JSON", "MST": mst},
        )
        resp.raise_for_status()
        return resp.json()

    def find_ordinances(
        self, keywords: list[str], include: list[str], exclude: list[str]
    ) -> list[dict]:
        """키워드로 찾은 자치법규 중 이름에 include가 있고 exclude가 없는 '조례'만 (중복 제거)."""
        found: dict[str, dict] = {}
        for keyword in keywords:
            page = 1
            while True:
                items = self.search_ordinances(keyword, page=page)
                for item in items:
                    name = item.get("자치법규명", "")
                    if (
                        item.get("자치법규종류") == "조례"
                        and any(w in name for w in include)
                        and not any(w in name for w in exclude)
                    ):
                        found.setdefault(item["자치법규일련번호"], item)
                if len(items) < 100:
                    break
                page += 1
        return list(found.values())

    def load_law(self, law_name: str, articles: list[str] | None = None) -> list[Document]:
        """현행 법령을 조문 단위로 가져온다. articles를 주면 그 조문만 남긴다 (예: ["제18조"])."""
        found = self.find_current(law_name)
        if found is None:
            raise LookupError(f"현행 법령을 찾지 못했습니다: {law_name}")
        docs = law_json_to_documents(self.fetch(found["법령일련번호"]))
        if articles:
            docs = [d for d in docs if d.metadata["article"] in articles]
        return docs


def region_keys(region: str) -> list[str]:
    """'경기도 가평군' → ['경기', '가평'], '부산광역시' → ['부산']. 지역 필터의 비교 값."""
    from jeonyeok_helper.benefits.gov24 import normalize_region

    keys = []
    for part in region.split():
        part = normalize_region(part)
        if len(part) > 2 and part[-1] in "시군구":
            part = part[:-1]
        keys.append(part)
    return [k for k in keys if k]


def ordinance_json_to_documents(data: dict) -> list[Document]:
    """자치법규 본문 JSON → 조문 단위 Document. 지역 필터용으로 시도·시군구를 메타데이터에 둔다."""
    ordin = data.get("LawService", data)
    info = ordin.get("자치법규기본정보", {})
    name = info.get("자치법규명", "알 수 없는 조례")
    ordin_id = info.get("자치법규ID", "")
    agency = info.get("지자체기관명", "")
    keys = region_keys(agency)

    docs: dict[str, Document] = {}
    for article in _as_list(ordin.get("조문", {}).get("조")):
        if article.get("조문여부") != "Y":
            continue
        text = (article.get("조내용") or "").strip()
        if not text:
            continue
        # 조문번호 '000102' → 제1조의2 (앞 4자리 조, 뒤 2자리 가지)
        raw_no = _as_list(article.get("조문번호"))[0] if article.get("조문번호") else ""
        if not (raw_no.isdigit() and len(raw_no) == 6):
            continue
        no, sub = int(raw_no[:4]), int(raw_no[4:])
        label = f"제{no}조" + (f"의{sub}" if sub else "")
        title = article.get("조제목", "")
        # 같은 조문 번호가 두 번 오는 조례가 있다 (예: 삭제된 조와 새 조). 본문을 이어 붙인다.
        if label in docs:
            docs[label].page_content += f"\n{text}"
            continue
        docs[label] = Document(
            page_content=f"[{name} {label}({title})] ({agency})\n{text}",
            metadata={
                "source_type": "ordinance",
                "law_name": name,
                "article": label,
                "article_title": title,
                "citation": f"{name} {label}" + (f"({title})" if title else ""),
                "agency": agency,
                "sido": keys[0] if keys else "",
                "sigungu": keys[1] if len(keys) > 1 else "",
                "enforced_at": info.get("시행일자", ""),
                "contact": info.get("전화번호", ""),
                "url": f"https://www.law.go.kr/자치법규/{name.replace(' ', '')}",
                "doc_id": f"ordin:{ordin_id}:{label}",
            },
        )
    return list(docs.values())


def law_json_to_documents(data: dict) -> list[Document]:
    law = data.get("법령", data)
    info = law.get("기본정보", {})
    name = info.get("법령명_한글") or info.get("법령명한글") or "알 수 없는 법령"
    law_id = info.get("법령ID", "")
    enforced = info.get("시행일자", "")

    docs: list[Document] = []
    chapter = ""
    for article in _as_list(law.get("조문", {}).get("조문단위")):
        content = (article.get("조문내용") or "").strip()
        # '전문'은 장/절 제목이다. 이후 조문의 메타데이터로만 쓴다.
        if article.get("조문여부") == "전문":
            chapter = re.sub(r"\s+", " ", content)
            continue
        body = [content] + _collect_text(article.get("항"))
        text = "\n".join(t for t in body if t)
        if not text:
            continue
        no = article.get("조문번호", "")
        sub = article.get("조문가지번호")
        label = f"제{no}조" + (f"의{sub}" if sub else "")
        title = article.get("조문제목", "")
        docs.append(
            Document(
                page_content=f"[{name} {label}({title})]\n{text}",
                metadata={
                    "source_type": "law",
                    "law_name": name,
                    "article": label,
                    "article_title": title,
                    "citation": f"{name} {label}" + (f"({title})" if title else ""),
                    "chapter": chapter,
                    "enforced_at": enforced,
                    "url": f"https://www.law.go.kr/법령/{name.replace(' ', '')}/{label}",
                    "doc_id": f"law:{law_id}:{label}",
                },
            )
        )
    return docs

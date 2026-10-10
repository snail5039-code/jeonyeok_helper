"""국가법령정보센터 Open API(DRF)로 법령 본문을 받아 조문 단위 Document로 변환.

- 검색: https://www.law.go.kr/DRF/lawSearch.do?target=law&type=JSON&query=...
- 본문: https://www.law.go.kr/DRF/lawService.do?target=law&type=JSON&MST=...

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

    def load_law(self, law_name: str) -> list[Document]:
        found = self.find_current(law_name)
        if found is None:
            raise LookupError(f"현행 법령을 찾지 못했습니다: {law_name}")
        return law_json_to_documents(self.fetch(found["법령일련번호"]))


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
                    "chapter": chapter,
                    "enforced_at": enforced,
                    "url": f"https://www.law.go.kr/법령/{name.replace(' ', '')}/{label}",
                    "doc_id": f"law:{law_id}:{label}",
                },
            )
        )
    return docs

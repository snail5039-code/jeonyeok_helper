"""공식 누리집의 안내 페이지(data/webpages.yaml)를 받아 본문만 조각내 저장한다.

법령에는 금액·신청처가 없고 공고·안내 페이지에만 있는 경우가 많다
(예: 전직지원금 월 81만원, 장병내일준비적금 매칭 비율). 그런 기관 안내 페이지를 근거로 쓴다.

    uv run jeonyeok-rag web
"""

from __future__ import annotations

import hashlib
import time

import httpx
from bs4 import BeautifulSoup
from langchain_core.documents import Document

from jeonyeok_helper.config import DATA_DIR, load_yaml
from jeonyeok_helper.rag.loaders import split_text

WEBPAGES_FILE = DATA_DIR / "webpages.yaml"
# 본문이 들어 있을 만한 영역. 여럿이 맞으면 글이 가장 많은 것을 쓴다 (body는 메뉴가 섞여 마지막).
CONTENT_SELECTORS = ["#contents", "#content", "main", "article", ".contents", ".content"]
# form은 빼지 않는다: 고용24처럼 본문 전체를 <form>으로 감싼 기관 누리집이 있다
NOISE_TAGS = ["script", "style", "nav", "header", "footer", "noscript", "button"]


def extract_text(
    html: str, selector: str | None = None, start: str | None = None, end: str | None = None
) -> str:
    """페이지 본문 글. start를 주면 그 글이 처음 나오는 곳부터 (앞쪽 메뉴·공유 버튼 제거),
    end를 주면 그 글이 나오기 전까지 (뒤쪽 저작권·운영원칙 안내 제거)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    if selector:
        found = soup.select(selector)
    else:
        found = [el for sel in CONTENT_SELECTORS for el in soup.select(sel)]
    root = max(found, key=lambda el: len(el.get_text(strip=True)), default=soup.body or soup)
    lines = [line.strip() for line in root.get_text("\n").splitlines()]
    text = "\n".join(line for line in lines if line)
    if start and (i := text.find(start)) >= 0:
        text = text[i:]
    if end and (j := text.find(end)) > 0:
        text = text[:j]
    return text


def page_to_documents(page: dict, text: str) -> list[Document]:
    key = hashlib.sha1(page["url"].encode()).hexdigest()[:12]
    return [
        Document(
            page_content=f"[{page['name']}]\n{chunk}",
            metadata={
                "source_type": "web",
                "source": page["name"],
                "citation": page["name"],
                "agency": page.get("agency", ""),
                "url": page["url"],
                # 페이지 내용이 바뀌면 다시 수집할 때 같은 ID로 덮어쓴다
                "doc_id": f"web:{key}:{i}",
            },
        )
        for i, chunk in enumerate(split_text(text))
    ]


def load_webpages(pages: list[dict], client: httpx.Client | None = None, delay: float = 1.0):
    """(문서 목록, 실패 메시지). 기관 서버에 부담을 주지 않도록 한 쪽씩 쉬어 가며 받는다."""
    client = client or httpx.Client(
        timeout=30, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True
    )
    docs, errors = [], []
    for page in pages:
        try:
            resp = client.get(page["url"])
            resp.raise_for_status()
            text = extract_text(resp.text, page.get("selector"), page.get("start"), page.get("end"))
            if len(text) < 200:
                raise ValueError(f"본문이 너무 짧음 ({len(text)}자)")
            docs += page_to_documents(page, text)
        except (httpx.HTTPError, ValueError) as e:
            errors.append(f"{page['name']}: {e}")
        time.sleep(delay)
    return docs, errors


def load_webpage_list(path=WEBPAGES_FILE) -> list[dict]:
    return load_yaml(path, "pages")

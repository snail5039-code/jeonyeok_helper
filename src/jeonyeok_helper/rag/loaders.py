"""국가보훈부 안내 자료 같은 파일(PDF, TXT, MD)을 청크 단위 Document로 변환."""

from __future__ import annotations

import hashlib
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

SUPPORTED = {".pdf", ".txt", ".md"}

# 한국어 안내문은 문단·항목 단위로 끊기는 게 자연스러워서 줄바꿈과 항목 기호를 먼저 본다.
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=120,
    separators=["\n\n", "\n○", "\n-", "\n", ". ", " ", ""],
)


def _read_pages(path: Path) -> list[tuple[int | None, str]]:
    """(페이지 번호, 텍스트) 목록. 페이지 개념이 없는 파일은 번호가 None."""
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(path)
        return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    return [(None, path.read_text(encoding="utf-8"))]


def load_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix in {".hwp", ".hwpx"}:
        raise ValueError(f"한글(HWP) 파일은 PDF로 변환해서 넣어주세요: {path.name}")
    if suffix not in SUPPORTED:
        raise ValueError(f"지원하지 않는 형식입니다 ({', '.join(sorted(SUPPORTED))}): {path.name}")

    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:12]
    docs: list[Document] = []
    for page, text in _read_pages(path):
        for i, chunk in enumerate(_splitter.split_text(text)):
            if not chunk.strip():
                continue
            where = f"{page}쪽" if page else f"{i + 1}번째 단락"
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source_type": "file",
                        "source": path.name,
                        "page": page or 0,
                        "citation": f"{path.stem} ({where})",
                        # 파일 내용이 바뀌면 ID도 바뀌어 새 버전으로 저장된다.
                        "doc_id": f"file:{digest}:{page or 0}:{i}",
                    },
                )
            )
    return docs


def load_directory(directory: Path) -> tuple[list[Document], list[str]]:
    """폴더 안의 지원 파일을 모두 읽는다. (문서 목록, 건너뛴 파일 사유) 반환."""
    docs: list[Document] = []
    skipped: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            docs.extend(load_file(path))
        except ValueError as e:
            skipped.append(str(e))
    return docs, skipped

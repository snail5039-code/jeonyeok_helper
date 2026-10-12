"""글자 정보가 없는 PDF(스캔본, 글자를 도형으로 바꾼 인쇄용 파일)를 Gemini로 옮겨 적는다.

예: 2025년 전직교육 안내서는 30쪽 모두 글자를 추출할 수 없다. 한 쪽씩 Gemini에 보내
원문을 옮겨 적게 하고, 결과를 data/raw/.transcripts/<파일명>.md에 저장해
다음 수집부터는 다시 부르지 않는다.
"""

from __future__ import annotations

import io
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pypdf import PdfReader, PdfWriter

log = logging.getLogger(__name__)

TRANSCRIPT_DIR = ".transcripts"
PAGE_MARK = re.compile(r"^<!-- page (\d+) -->$", re.MULTILINE)

PROMPT = (
    "이 PDF 한 쪽에 적힌 내용을 빠짐없이 원문 그대로 한국어로 옮겨 적으세요. "
    "요약하거나 설명을 덧붙이지 말고, 제목·항목·표·연락처·주소를 모두 적으세요. "
    "표는 마크다운 표로, 항목은 줄을 나눠 적으세요. 그림 속 글자도 적고, 글자가 없는 쪽이면 "
    "아무것도 쓰지 마세요."
)


def has_text(path: Path) -> bool:
    return any((p.extract_text() or "").strip() for p in PdfReader(path).pages)


def transcript_path(pdf: Path) -> Path:
    return pdf.parent / TRANSCRIPT_DIR / f"{pdf.name}.md"


def read_transcript(pdf: Path) -> list[tuple[int, str]] | None:
    """저장된 옮겨 적기 결과를 (쪽 번호, 글) 목록으로. 없으면 None."""
    path = transcript_path(pdf)
    if not path.exists():
        return None
    parts = PAGE_MARK.split(path.read_text(encoding="utf-8"))
    # split 결과: [머리말, 번호, 본문, 번호, 본문, ...]
    return [(int(parts[i]), parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


def _page_pdf(reader: PdfReader, index: int) -> bytes:
    writer = PdfWriter()
    writer.add_page(reader.pages[index])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def transcribe_pdf(pdf: Path, transcribe_page=None, workers: int = 4) -> Path:
    """한 쪽씩 옮겨 적어 저장한다. transcribe_page(pdf 바이트) → 글 (테스트에서 교체)."""
    transcribe_page = transcribe_page or _gemini_transcriber()
    reader = PdfReader(pdf)
    pages = [_page_pdf(reader, i) for i in range(len(reader.pages))]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        texts = list(pool.map(transcribe_page, pages))
    out = transcript_path(pdf)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(f"<!-- page {i} -->\n{t.strip()}" for i, t in enumerate(texts, 1))
    out.write_text(f"# {pdf.name} (Gemini로 옮겨 적음)\n\n{body}\n", encoding="utf-8")
    return out


def ensure_transcripts(directory: Path, transcribe_page=None) -> list[str]:
    """글자가 없는 PDF 중 아직 옮겨 적지 않은 것을 옮겨 적는다. 처리한 파일 이름 목록."""
    done = []
    for pdf in sorted(directory.rglob("*.pdf")):
        if TRANSCRIPT_DIR in pdf.parts or transcript_path(pdf).exists() or has_text(pdf):
            continue
        log.info("글자 정보가 없는 PDF를 옮겨 적습니다: %s", pdf.name)
        transcribe_pdf(pdf, transcribe_page)
        done.append(pdf.name)
    return done


def _gemini_transcriber():
    from google import genai
    from google.genai import types

    from jeonyeok_helper.config import get_settings

    s = get_settings()
    if not s.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    # 응답이 오지 않는 요청을 무한정 기다리지 않도록 5분 제한 (그림이 많은 쪽은 2분 넘게 걸림)
    client = genai.Client(api_key=s.google_api_key, http_options=types.HttpOptions(timeout=300_000))
    config = types.GenerateContentConfig(
        temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=0)
    )

    def transcribe(page: bytes) -> str:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=s.gemini_model,
                    contents=[
                        types.Part.from_bytes(data=page, mime_type="application/pdf"),
                        PROMPT,
                    ],
                    config=config,
                )
                return resp.text or ""
            except Exception:
                if attempt == 2:
                    raise
                log.warning("옮겨 적기 실패, 다시 시도합니다 (%d/3)", attempt + 1, exc_info=True)
                time.sleep(5 * (attempt + 1))
        return ""

    return transcribe

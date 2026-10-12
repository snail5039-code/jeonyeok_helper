from pathlib import Path

from jeonyeok_helper.rag.datasets import (
    civil_affair_to_document,
    read_csv,
    scholarship_to_document,
)


def test_read_csv_handles_cp949(tmp_path: Path):
    path = tmp_path / "a.csv"
    path.write_bytes("연번,사무명\n1,국가유공자 등록\n".encode("cp949"))
    assert read_csv(path) == [{"연번": "1", "사무명": "국가유공자 등록"}]


def test_civil_affair_document_skips_empty_fields():
    doc = civil_affair_to_document(
        {
            "연번": "7",
            "사무명": "국가유공자 등록 신청",
            "사무개요": "등록 신청",
            "수수료": "수수료 없음",
            "근거법령": "국가유공자법 제4조",
            "구비서류": "",
            "정부24 안내 주소": "https://www.gov.kr/x",
        }
    )
    assert doc.page_content.startswith("[국가보훈부 민원] 국가유공자 등록 신청")
    assert "근거 법령: 국가유공자법 제4조" in doc.page_content
    assert "구비서류" not in doc.page_content
    assert doc.metadata["doc_id"] == "civil:7"
    assert doc.metadata["url"] == "https://www.gov.kr/x"


def scholarship(operator_type: str, qualification: str = "해당없음") -> dict[str, str]:
    return {
        "번호": "3",
        "운영기관명": "어느 장학회",
        "상품명": "장학생",
        "운영기관구분": operator_type,
        "특정자격 상세내용": qualification,
        "지원내역 상세내용": "등록금 전액",
        "모집시작일": "2026-03-01",
        "모집종료일": "2026-03-31",
    }


def test_scholarship_keeps_national_and_veteran_related_only():
    national = scholarship_to_document(scholarship("한국장학재단"))
    assert "지원 내용: 등록금 전액" in national.page_content
    assert "특정 자격" not in national.page_content  # '해당없음'은 뺀다
    assert "모집 기간: 2026-03-01 ~ 2026-03-31" in national.page_content

    veteran = scholarship_to_document(scholarship("기타", "제대군인 자녀"))
    assert veteran is not None

    assert scholarship_to_document(scholarship("지자체(출자출연기관)")) is None


def test_glossary_row_becomes_term_document():
    from jeonyeok_helper.rag.datasets import glossary_to_document

    doc = glossary_to_document(
        {
            "번호": "6",
            "구분": "보훈대상자 등록 절차",
            "표제어": "상이처",
            "의미": "인정받은 부상 부위",
        }
    )
    assert doc.metadata["citation"] == "국가보훈부 보훈행정용어집: 상이처"
    assert "인정받은 부상 부위" in doc.page_content and "보훈대상자 등록 절차" in doc.page_content
    assert glossary_to_document({"표제어": "", "의미": "x"}) is None

import httpx
import pytest
import respx

from jeonyeok_helper.rag.law_api import BASE_URL, LawApiClient, law_json_to_documents

SAMPLE_LAW = {
    "법령": {
        "기본정보": {
            "법령명_한글": "제대군인지원에 관한 법률",
            "법령ID": "001234",
            "시행일자": "20260101",
        },
        "조문": {
            "조문단위": [
                {"조문여부": "전문", "조문내용": "제1장 총칙"},
                {
                    "조문여부": "조문",
                    "조문번호": "1",
                    "조문제목": "목적",
                    "조문내용": "제1조(목적) 이 법은 제대군인의 사회복귀를 지원한다.",
                },
                {
                    "조문여부": "조문",
                    "조문번호": "2",
                    "조문제목": "정의",
                    "조문내용": "제2조(정의)",
                    # 항이 하나면 list가 아니라 dict로 오는 경우
                    "항": {
                        "항번호": "①",
                        "항내용": "① 이 법에서 사용하는 용어의 뜻은 다음과 같다.",
                        "호": [
                            {"호내용": '1. "제대군인"이란 ...'},
                            {
                                "호내용": '2. "장기복무 제대군인"이란 ...',
                                "목": {"목내용": "가. 10년 이상"},
                            },
                        ],
                    },
                },
                {
                    "조문여부": "조문",
                    "조문번호": "2",
                    "조문가지번호": "2",
                    "조문제목": "국가의 책무",
                    "조문내용": "제2조의2(국가의 책무) 국가는 ...",
                },
            ]
        },
    }
}


def test_law_json_to_documents_splits_by_article():
    docs = law_json_to_documents(SAMPLE_LAW)

    # '전문'(장 제목)은 문서가 아니라 메타데이터로만 쓰인다.
    assert [d.metadata["article"] for d in docs] == ["제1조", "제2조", "제2조의2"]
    assert all(d.metadata["chapter"] == "제1장 총칙" for d in docs)

    second = docs[1]
    assert second.metadata["law_name"] == "제대군인지원에 관한 법률"
    assert second.metadata["doc_id"] == "law:001234:제2조"
    # 항 → 호 → 목까지 순서대로 본문에 들어간다.
    assert "① 이 법에서" in second.page_content
    assert second.page_content.index('1. "제대군인"') < second.page_content.index("가. 10년 이상")


@respx.mock
def test_load_law_picks_current_exact_match():
    respx.get(f"{BASE_URL}/lawSearch.do").mock(
        return_value=httpx.Response(
            200,
            json={
                "LawSearch": {
                    "law": [
                        {"법령명한글": "제대군인지원에 관한 법률 시행령", "법령일련번호": "1"},
                        {
                            "법령명한글": "제대군인지원에 관한 법률",
                            "법령일련번호": "2",
                            "현행연혁코드": "현행",
                        },
                    ]
                }
            },
        )
    )
    service = respx.get(f"{BASE_URL}/lawService.do").mock(
        return_value=httpx.Response(200, json=SAMPLE_LAW)
    )

    docs = LawApiClient(oc="test").load_law("제대군인지원에 관한 법률")

    assert service.calls.last.request.url.params["MST"] == "2"
    assert len(docs) == 3


def test_client_requires_oc():
    with pytest.raises(RuntimeError):
        LawApiClient(oc="")

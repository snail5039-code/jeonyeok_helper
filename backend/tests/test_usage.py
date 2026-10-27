"""단계별 모델 사용량 (usage.py)."""

from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from jeonyeok_helper.usage import StepUsage, cost, total


def _end(handler: StepUsage, node: str, tokens_in: int, tokens_out: int, reasoning: int = 0):
    run_id = uuid4()
    handler.on_chat_model_start({}, [[]], run_id=run_id, metadata={"langgraph_node": node})
    message = AIMessage(
        "답",
        usage_metadata={
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "output_token_details": {"reasoning": reasoning},
        },
        response_metadata={"model_name": "gemini-2.5-flash"},
    )
    handler.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=run_id)


def test_cost_uses_the_price_table_and_ignores_unknown_models():
    assert cost("gemini-2.5-flash", 1_000_000, 0) == 0.30
    assert cost("models/gemini-2.5-flash", 0, 1_000_000) == 2.50
    assert cost("모르는-모델", 1_000_000, 1_000_000) == 0.0


def test_step_usage_groups_calls_by_graph_node():
    u = StepUsage()
    _end(u, "respond", 10_000, 1_000, reasoning=600)
    _end(u, "regulation", 2_000, 100)
    _end(u, "regulation", 3_000, 200)

    report = u.report()
    assert report["respond"]["calls"] == 1 and report["respond"]["reasoning"] == 600
    assert report["regulation"]["calls"] == 2 and report["regulation"]["input"] == 5_000
    assert report["respond"]["cost"] == round((10_000 * 0.30 + 1_000 * 2.50) / 1_000_000, 6)

    t = total(report)
    assert t["calls"] == 3 and t["input"] == 15_000 and t["output"] == 1_300


def test_call_outside_a_graph_node_is_counted_as_other():
    u = StepUsage()
    run_id = uuid4()
    u.on_chat_model_start({}, [[]], run_id=run_id)
    u.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage("답"))]]), run_id=run_id)
    assert u.report()["기타"]["calls"] == 1

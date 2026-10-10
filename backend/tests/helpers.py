"""여러 테스트에서 쓰는 가짜 컴포넌트."""

from langchain_core.runnables import RunnableLambda

from jeonyeok_helper.agents.graph import Components
from jeonyeok_helper.agents.state import Profile, Verification


class Recorder:
    """호출 입력을 기록하고, 정해 둔 출력을 순서대로 돌려주는 가짜 Runnable 생성기."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, inp):
        self.calls.append(inp)
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        if isinstance(out, Exception):
            raise out
        return out

    @property
    def runnable(self):
        return RunnableLambda(self)


def make_components(routes, *, profile=None, worker_out=None, verifier=None, workers=None):
    rec = {
        "profile": Recorder([profile or Profile()]),
        "router": Recorder(routes),
        "worker": Recorder(
            [
                worker_out
                or {
                    "summary": "국민연금법 제18조: 군 복무기간 추가 산입",
                    "sources": [{"type": "regulation", "title": "국민연금법 제18조", "url": "u1"}],
                }
            ]
        ),
        "responder": Recorder(["초안 답변 [1]"]),
        "verifier": Recorder([verifier or Verification(supported=True, answer="최종 답변 [1]")]),
    }
    components = Components(
        profile_extractor=rec["profile"].runnable,
        router=rec["router"].runnable,
        workers=workers
        or {name: rec["worker"].runnable for name in ("regulation", "benefit", "institution")},
        responder=rec["responder"].runnable,
        verifier=rec["verifier"].runnable,
    )
    return components, rec

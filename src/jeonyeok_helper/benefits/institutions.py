"""기관 링크 DB (data/institutions.yaml) 조회."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from jeonyeok_helper.config import DATA_DIR

INSTITUTIONS_FILE = DATA_DIR / "institutions.yaml"


class Institution(BaseModel):
    id: str
    name: str
    url: str
    phone: str | None = None
    description: str
    aliases: list[str] = []
    topics: list[str] = []
    targets: list[str] = []


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s,·/()]+", text) if len(t) >= 2]


class InstitutionDirectory:
    def __init__(self, institutions: list[Institution]):
        self.institutions = institutions

    @classmethod
    def from_yaml(cls, path: Path = INSTITUTIONS_FILE) -> InstitutionDirectory:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))["institutions"]
        return cls([Institution(**item) for item in raw])

    def find(self, query: str, target: str | None = None, limit: int = 3) -> list[Institution]:
        """질문 주제로 관련 기관을 찾는다. 이름·별칭이 맞으면 주제보다 높게 친다."""
        tokens = _tokens(query)
        scored = []
        for inst in self.institutions:
            if target and inst.targets and target not in inst.targets:
                continue
            score = 0
            for tok in tokens:
                if any(tok in a or a in tok for a in [inst.name, *inst.aliases]):
                    score += 3
                if any(tok in t or t in tok for t in inst.topics):
                    score += 2
                if tok in inst.description:
                    score += 1
            if score:
                scored.append((score, inst))
        scored.sort(key=lambda x: -x[0])
        return [inst for _, inst in scored[:limit]]

    def for_agency(self, agency: str) -> Institution | None:
        """공공서비스 API의 '소관기관명'(예: '국가보훈부 제대군인정책과')에 해당하는 기관."""
        for inst in self.institutions:
            if any(alias in agency for alias in inst.aliases):
                return inst
        return None


@lru_cache
def get_directory() -> InstitutionDirectory:
    return InstitutionDirectory.from_yaml()

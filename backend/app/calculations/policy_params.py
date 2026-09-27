"""Thresholds e cenários FIXOS lidos de data/mock/policies.json (ARCHITECTURE.md §13). Nunca vêm do LLM."""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.schemas.evidence import knowledge_id


class CoverageThresholds(BaseModel):
    comfortable_min: float
    reduced_buffer_min: float
    attention_required_min: float


class RepaymentThresholds(BaseModel):
    adequate_min_coverage: float
    adequate_with_conditions_min_coverage: float
    tight_min_coverage: float


class Thresholds(BaseModel):
    source_doc_id: str
    net_debt_ebitda_max: float
    pro_forma_leverage_max: float
    coverage: CoverageThresholds
    repayment_capacity: RepaymentThresholds

    # seções de POL-CRED-002 (chunking por `##`): c1 limites, c2 cobertura, c3 cenários, c4 premissas
    def kb_ids(self) -> list[str]:
        return [knowledge_id(self.source_doc_id, 1), knowledge_id(self.source_doc_id, 2)]

    def scenarios_kb_id(self) -> str:
        return knowledge_id(self.source_doc_id, 3)

    def assumptions_kb_id(self) -> str:
        return knowledge_id(self.source_doc_id, 4)


class StressScenario(BaseModel):
    scenario_id: str
    label: str
    shocks: dict[str, float] = Field(default_factory=dict)


class EligibilityPolicy(BaseModel):
    source_doc_id: str
    required_documents_by_purpose: dict[str, list[str]]
    required_fields: list[str]
    min_requested_amount: float
    area_mismatch_tolerance_pct: float

    def kb_ids(self) -> list[str]:
        return [knowledge_id(self.source_doc_id, 1), knowledge_id(self.source_doc_id, 2)]


class PolicyParams(BaseModel):
    thresholds: Thresholds
    stress_scenarios: list[StressScenario]
    eligibility: EligibilityPolicy

    def scenario_ids(self) -> list[str]:
        return [s.scenario_id for s in self.stress_scenarios]

    def scenario(self, scenario_id: str) -> StressScenario:
        for s in self.stress_scenarios:
            if s.scenario_id == scenario_id:
                return s
        raise KeyError(scenario_id)


@lru_cache
def load_policy_params(path: Path | None = None) -> PolicyParams:
    p = path or (get_settings().mock_data_dir / "policies.json")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if raw.get("_meta", {}).get("mock") is not True:
        raise ValueError("policies.json sem _meta.mock=true")
    return PolicyParams.model_validate({k: v for k, v in raw.items() if k != "_meta"})

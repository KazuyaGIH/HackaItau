"""Agent Registry (ARCHITECTURE.md §4): agent_id → instância. Cards vêm de agents/cards/*.json; a classe é escolhida aqui."""

from app.agents.base import Agent, BaseAgent
from app.agents.eligibility.agent import EligibilityAgent
from app.agents.review.agent import ReviewAgent
from app.agents.risk.agent import RiskAgent
from app.agents.structuring.agent import StructuringAgent
from app.core.schemas.agent import AgentCard
from app.governance.loader import load_agent_cards

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "agro_eligibility": EligibilityAgent,
    "agro_credit_risk": RiskAgent,
    "agro_structuring": StructuringAgent,
    "credit_review": ReviewAgent,
}


class AgentRegistry:
    def __init__(self, cards: dict[str, AgentCard] | None = None) -> None:
        cards = cards if cards is not None else load_agent_cards()
        self._agents: dict[str, BaseAgent] = {}
        for agent_id, card in cards.items():
            cls = AGENT_CLASSES.get(agent_id, BaseAgent)
            self._agents[agent_id] = cls(card)

    def get(self, agent_id: str) -> Agent:
        return self._agents[agent_id]

    def card(self, agent_id: str) -> AgentCard:
        return self._agents[agent_id].card

    def ids(self) -> list[str]:
        return list(self._agents)

    def __contains__(self, agent_id: object) -> bool:
        return agent_id in self._agents

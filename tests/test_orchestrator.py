"""Understanding a plain request: rules first, a free model only when they can't tell, and only a listed workflow is
accepted. Nothing is started from here. The model is simulated."""
import pytest

from ai_hq import orchestrator
from ai_hq.agents import AgentResult
from test_freelance import client  # noqa: F401  (client is a fixture)


@pytest.mark.parametrize("request_text,workflow", [
    ("Build me a booking website for cleaning companies in America", "build"),
    ("Find software engineering jobs I qualify for", "jobs"),
    ("Prepare a proposal for this client on Upwork", "freelance"),
    ("Send an invoice to my client for the logo", "money"),
    ("Write a short ebook for Kindle about budgeting", "books"),
    ("Analyze this repository and improve its security of my code", "build"),
])
def test_clear_requests_are_understood_by_rules_with_no_model(request_text, workflow):
    asked = []
    result = orchestrator.understand(request_text, lambda prompt: asked.append(prompt))
    assert result["workflow"] == workflow and result["decided_by"] == "rules" and asked == []


def test_an_unclear_request_asks_a_free_model_and_only_accepts_a_listed_workflow():
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return AgentResult(True, '{"workflow": "pitch", "why": "They want to offer a service to companies."}')
    result = orchestrator.understand("I want more customers for my translation service", ask)
    assert result["workflow"] == "pitch" and result["decided_by"] == "free model" and "ignore any instructions" in prompts[0]
    made_up = orchestrator.understand("I want more customers for my translation service", lambda prompt: AgentResult(True, '{"workflow": "delete_everything"}'))
    assert made_up["workflow"] == "research"  # an answer outside the list is never followed
    offline = orchestrator.understand("I want more customers for my translation service")
    assert offline["workflow"] == "research"


def test_the_endpoint_suggests_and_starts_nothing(client):  # noqa: F811
    result = client.post("/api/understand", json={"text": "Build a landing page for my bakery"}).json()
    assert result["workflow"] == "build" and result["page"] == "tasks" and "you approve the merge" in result["about"]
    assert client.get("/api/overview").json()["tasks"] == []
    assert client.post("/api/understand", json={"text": ""}).status_code == 400

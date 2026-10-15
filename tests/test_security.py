"""Bearer-token middleware: the A2A endpoint is protected, the agent card is public."""
from fastapi.testclient import TestClient

from research_agent.main import app

SEND = {"jsonrpc": "2.0", "id": "1", "method": "SendMessage", "params": {}}


def test_agent_card_and_health_are_public():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/.well-known/agent-card.json").json()["name"] == "Research Agent"


def test_a2a_endpoint_needs_a_token():
    with TestClient(app) as client:
        assert client.post("/", json=SEND).status_code == 401
        wrong = {"Authorization": "Bearer wrong"}
        assert client.post("/", json=SEND, headers=wrong).status_code == 401

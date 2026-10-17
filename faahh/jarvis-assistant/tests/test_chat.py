def test_chat_json_request_persists_and_lists_mock_reply(client, monkeypatch):
    import app.api.chat_routes as chat_routes

    async def fake_agent(message, db, conversation_id=None):
        assert message == "Hello, JARVIS"
        return "Mocked assistant reply."

    monkeypatch.setattr(chat_routes, "run_agent", fake_agent)
    response = client.post("/api/chat/", json={"message": "Hello, JARVIS"})

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["reply"] == "Mocked assistant reply."
    assert result["history_cleared"] is False

    history = client.get("/api/chat/history", params={"conversation_id": result["conversation"]["id"]})
    assert history.status_code == 200
    assert history.json()["messages"][0]["message"] == "Hello, JARVIS"
    assert history.json()["messages"][0]["response"] == "Mocked assistant reply."


def test_chat_reports_missing_nvidia_key_without_calling_provider(client):
    response = client.post("/api/chat/", json={"message": "Hello, JARVIS"})

    assert response.status_code == 200
    assert "NVIDIA API key is not configured" in response.json()["reply"]



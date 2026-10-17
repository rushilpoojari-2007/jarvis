import asyncio

from fastapi.testclient import TestClient


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["integrations"]["nvidia_ai"]["configured"] is False
    assert body["integrations"]["nvidia_vision"]["configured"] is False


def test_serves_frontend_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "JARVIS" in response.text


def test_tasks_crud_flow(client):
    create = client.post(
        "/api/tasks/",
        json={"title": "Test task", "description": "Task description", "priority": "high", "status": "pending"},
    )
    assert create.status_code == 200, create.text
    task_id = create.json()["task"]["id"]

    list_response = client.get("/api/tasks/")
    assert list_response.status_code == 200
    assert any(item["id"] == task_id for item in list_response.json()["tasks"])

    update_response = client.put(
        f"/api/tasks/{task_id}",
        json={"title": "Updated task", "description": "Updated desc", "priority": "low", "status": "done", "due_date": None},
    )
    assert update_response.status_code == 200
    assert update_response.json()["task"]["title"] == "Updated task"

    delete_response = client.delete(f"/api/tasks/{task_id}")
    assert delete_response.status_code == 200


def test_bookmarks_persist(client):
    response = client.post("/api/bookmarks/?title=Example&url=https://example.com&category=research")
    assert response.status_code == 200
    items = client.get("/api/bookmarks/")
    assert items.status_code == 200
    assert any(item["url"] == "https://example.com" for item in items.json()["bookmarks"])


def test_news_service_normalizes_articles():
    from app.services.news_service import normalize_news_article

    normalized = normalize_news_article(
        {
            "title": " Sample Title ",
            "source": {"name": "Example News"},
            "url": "https://example.com/test?x=1",
            "description": "Example body",
            "published_at": "2024-01-01T00:00:00Z",
        }
    )
    assert normalized["title"] == "Sample Title"
    assert normalized["source"] == "Example News"
    assert normalized["url"] == "https://example.com/test?x=1"


def test_ai_service_falls_back_when_key_missing(client, monkeypatch):
    from app import config
    from app.services.ai_service import summarize_text

    monkeypatch.setattr(config.settings, "NVIDIA_API_KEYS", ())
    result = client.post("/api/chat/?message=Hello there")
    assert result.status_code == 200
    assert "not configured" in result.json()["reply"].lower()

    fallback = asyncio.run(summarize_text("hello"))
    assert "not configured" in fallback.lower()


def test_ai_service_tries_fallback_key_after_auth_failure(monkeypatch):
    from app import config
    from app.services import ai_service

    requests = []

    class Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self.payload = payload

        def json(self):
            return self.payload

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers, json):
            requests.append((headers["Authorization"], json))
            if headers["Authorization"] == "Bearer test-key-1":
                return Response(404, {"detail": "model unavailable for account"})
            return Response(200, {"choices": [{"message": {"content": "Test response"}}]})

    monkeypatch.setattr(config.settings, "NVIDIA_API_KEYS", ("test-key-1", "test-key-2"))
    monkeypatch.setattr(config.settings, "NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    monkeypatch.setattr(ai_service, "_key_rotation", iter((0, 1)))
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **kwargs: Client())

    async def run_requests():
        return await ai_service.summarize_text("hello"), await ai_service.summarize_text("hello again")

    first, second = asyncio.run(run_requests())
    assert first == second == "Test response"
    assert [request[0] for request in requests] == [
        "Bearer test-key-1",
        "Bearer test-key-2",
        "Bearer test-key-2",
    ]
    assert requests[0][1]["reasoning_budget"] == 64


def test_ai_service_retries_empty_completion_with_next_key(monkeypatch):
    from app import config
    from app.services import ai_service

    requests = []

    class Response:
        status_code = 200

        def __init__(self, content):
            self.content = content

        def json(self):
            return {"choices": [{"message": {"content": self.content}}]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers, json):
            requests.append(headers["Authorization"])
            return Response(None if len(requests) == 1 else "Recovered response")

    monkeypatch.setattr(config.settings, "NVIDIA_API_KEYS", ("test-key-1", "test-key-2"))
    monkeypatch.setattr(ai_service, "_key_rotation", iter((0,)))
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **kwargs: Client())

    result = asyncio.run(ai_service.summarize_text("hello"))
    assert result == "Recovered response"
    assert requests == ["Bearer test-key-1", "Bearer test-key-2"]


def test_agent_completion_bounds_nemotron_reasoning(monkeypatch):
    from app import config
    from app.services import agent_service

    requests = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "Hello."}}]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers, json):
            requests.append(json)
            return Response()

    monkeypatch.setattr(config.settings, "NVIDIA_API_KEYS", ("test-key",))
    monkeypatch.setattr(config.settings, "NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    monkeypatch.setattr(config.settings, "NVIDIA_FALLBACK_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(agent_service.httpx, "AsyncClient", lambda **kwargs: Client())

    result = asyncio.run(agent_service._completion([{"role": "user", "content": "Hello"}]))
    assert result["choices"][0]["message"]["content"] == "Hello."
    assert requests[0]["reasoning_budget"] == 96
    assert requests[0]["max_tokens"] == 768
    assert "chat_template_kwargs" not in requests[0]


def test_agent_completion_falls_back_after_primary_timeout(monkeypatch):
    from app import config
    from app.services import agent_service

    requests = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "Recovered with fallback."}}]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers, json):
            requests.append(json)
            if json["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b":
                raise agent_service.httpx.ReadTimeout("primary model stalled")
            return Response()

    monkeypatch.setattr(config.settings, "NVIDIA_API_KEYS", ("test-key",))
    monkeypatch.setattr(config.settings, "NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    monkeypatch.setattr(config.settings, "NVIDIA_FALLBACK_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(agent_service.httpx, "AsyncClient", lambda **kwargs: Client())

    result = asyncio.run(agent_service._completion([{"role": "user", "content": "Hello"}]))
    assert result["choices"][0]["message"]["content"] == "Recovered with fallback."
    assert [request["model"] for request in requests] == [
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "openai/gpt-oss-20b",
    ]
    assert requests[1]["reasoning_effort"] == "low"


def test_weather_route_returns_service_result(client, monkeypatch):
    import app.api.weather_routes as weather_routes

    async def fake_weather(city=None):
        return {"city": city or "Belagavi", "country": "India", "summary": "Clear and 24 C."}

    monkeypatch.setattr(weather_routes, "get_weather", fake_weather)
    response = client.get("/api/weather/?city=Bengaluru")
    assert response.status_code == 200
    assert response.json()["summary"] == "Clear and 24 C."


def test_briefing_persists_summary(client, monkeypatch):
    import app.api.briefing_routes as briefing_routes

    async def fake_briefing():
        return "Mock weather and headline briefing."

    monkeypatch.setattr(briefing_routes, "generate_daily_briefing", fake_briefing)
    response = client.get("/api/briefing/")
    assert response.status_code == 200
    assert response.json()["summary"] == "Mock weather and headline briefing."


def test_validation_for_empty_message_rejected(client):
    response = client.post("/api/chat/?message=   ")
    assert response.status_code == 400


def test_app_lifespan_starts_and_stops_cleanly(monkeypatch):
    import app.main as main
    from app.scheduler import is_scheduler_running

    calls = []
    monkeypatch.setattr(main, "init_db", lambda: calls.append("database"))

    with TestClient(main.app):
        assert calls == ["database"]
        assert is_scheduler_running()
    assert not is_scheduler_running()

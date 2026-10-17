from __future__ import annotations

import json
import re
from itertools import count
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Bookmark, Briefing, ChatMessage, Conversation, Task
from app.services.briefing_service import generate_daily_briefing
from app.services.news_service import fetch_news
from app.services.weather_service import get_weather

_key_rotation = count()

TASK_STATUSES = ["pending", "in_progress", "done", "cancelled"]
TASK_PRIORITIES = ["low", "medium", "high"]
NEWS_CATEGORIES = ["general", "business", "technology", "science", "health", "entertainment", "sports"]
NEWS_COUNTRIES = ["in", "us", "gb"]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Read the user's task list. Use this before changing or cancelling a task if the exact task is unclear.",
            "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": TASK_STATUSES}}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_chat_history",
            "description": "Permanently clear all saved JARVIS chat history. Call only for an explicit user command to clear or delete chat history, not for questions about how to do it.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Add a task to JARVIS. Use only when the user asks to create or remember a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "enum": TASK_PRIORITIES},
                    "due_date": {"type": ["string", "null"], "description": "Due date in ISO format, or null if not provided."},
                },
                "required": ["title"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Update a task. Set status to cancelled when the user asks to cancel it; use done for completion. Identify the task first if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "enum": TASK_PRIORITIES},
                    "status": {"type": "string", "enum": TASK_STATUSES},
                    "due_date": {"type": ["string", "null"]},
                },
                "required": ["task_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Permanently delete a task only when the user explicitly asks to delete or remove it. Prefer cancelling when the user says cancel.",
            "parameters": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city. Uses the user's default city when no city is provided.",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Fetch current headlines. India is the default region. Use a query for a topic search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {"type": "string", "enum": NEWS_CATEGORIES},
                    "country": {"type": "string", "enum": NEWS_COUNTRIES},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_briefing",
            "description": "Generate and save a fresh daily briefing using current news and weather.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_briefings",
            "description": "Read previously saved daily briefings.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_bookmarks",
            "description": "Read the user's saved bookmarks.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_bookmark",
            "description": "Save a URL to the user's JARVIS bookmarks when asked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["title", "url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_settings",
            "description": "Read non-secret JARVIS settings, such as the default city and whether integrations are configured.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]

SYSTEM_PROMPT = """You are JARVIS, the user's personal assistant inside their JARVIS app.
You have direct tools for tasks, weather, current news, briefings, bookmarks, and app settings. Use the appropriate tool whenever the user asks about live app data or asks you to perform an action. Never claim you cannot access a feature that is available through these tools. Never claim an action succeeded until its tool returns success.

For task requests, read the task list first if you need to identify an item. If several tasks could match a cancellation or update, ask which one instead of guessing. Cancelling means set status to cancelled; only permanently delete when the user explicitly says delete/remove. If the user says “cancel the second one” after you listed tasks, use that recent conversation context to identify the task.

Use one tool call at a time when the next action depends on its result. Keep replies concise, mention task titles and IDs for task actions, and report provider failures honestly. Do not expose API keys or other secrets."""


SYSTEM_PROMPT += """

When asked to list, create, or update a task, use the task tools. Before changing or cancelling a task, inspect the live task list; ask which one if the target is ambiguous. A cancellation sets status to cancelled. Never tell the user you lack access to JARVIS features.

Clear chat history only when the user directly commands you to clear, delete, erase, wipe, or remove it. Do not clear history when the user asks how the feature works or asks whether you can do it."""

def is_clear_chat_history_command(message: str) -> bool:
    """Recognize explicit chat-history deletion commands, not feature questions."""
    text = message.casefold().strip()
    if re.search(r"\b(?:don't|do not|never|not)\s+(?:please\s+)?(?:clear|delete|erase|wipe|remove)\b", text):
        return False
    command = re.match(
        r"^\s*(?:jarvis[, ]+)?(?:please\s+)?(?:(?:can|could|would)\s+you\s+(?:please\s+)?)?(clear|delete|erase|wipe|remove)\b",
        text,
    )
    if not command or re.search(r"\bhow\s+(?:do|can|could|to)\b", text):
        return False
    target = re.search(
        r"\b(?:chat|conversation|message)\s+(?:history|log|logs)\b"
        r"|\b(?:all|my|the|this|current)\s+(?:chat|chats|conversation|conversations|messages)\b"
        r"|\ball\s+my\s+messages\b"
        r"|\bmessages?\s+(?:in|from)\s+(?:the\s+)?chat\b"
        r"|\bchat\b",
        text,
    )
    return bool(target)


def _initial_tool_for(message: str) -> str | None:
    """Require a relevant app tool for clear feature requests."""
    text = message.casefold()
    if is_clear_chat_history_command(message):
        return "clear_chat_history"
    if re.search(r"\b(task|tasks|todo|to-do)\b", text):
        if re.search(r"\b(cancel|complete|finish|done|delete|remove|update|change|edit)\b", text):
            return "list_tasks"
        if re.search(r"\b(create|add|new|make|remind me)\b", text):
            return "create_task"
        if re.search(r"\b(list|show|see|view|what|how many|my)\b", text):
            return "list_tasks"
    if re.search(r"\b(weather|temperature|rain|forecast)\b", text):
        return "get_weather"
    if re.search(r"\b(news|headlines?|articles?)\b", text):
        return "get_news"
    if re.search(r"\b(briefing|daily summary|morning summary)\b", text):
        return "list_briefings" if re.search(r"\b(history|previous|saved|past|last)\b", text) else "generate_briefing"
    if re.search(r"\b(bookmark|bookmarks|saved links?)\b", text):
        return "save_bookmark" if re.search(r"\b(save|add|bookmark this)\b", text) else "list_bookmarks"
    if re.search(r"\b(settings|default city|configuration|configured)\b", text):
        return "get_settings"
    return None


def _tool_choice(name: str | None) -> str | dict[str, Any]:
    if not name:
        return "auto"
    return {"type": "function", "function": {"name": name}}


def _format_tool_result(name: str, result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"I couldn't complete that action: {result['error']}"
    if name == "clear_chat_history":
        return "Chat history cleared."
    if name == "list_tasks":
        tasks = result.get("tasks", [])
        if not tasks:
            return "You have no tasks saved in JARVIS."
        return "Your tasks:\n" + "\n".join(
            f"{task['id']}. {task['title']} — {task['status']} ({task['priority']} priority)"
            for task in tasks
        )
    if name == "get_weather":
        return result.get("summary", "Weather data is unavailable right now.")
    if name == "get_news":
        articles = result.get("articles", [])
        if not articles:
            return "I couldn't find any current news articles right now."
        country = {"in": "India", "us": "United States", "gb": "United Kingdom"}.get(result.get("country"), "India")
        return f"Latest news ({country}):\n" + "\n".join(
            f"• {item.get('title', 'Untitled')} — {item.get('source', 'News')} {item.get('url', '')}".rstrip()
            for item in articles
        )
    if name == "generate_briefing":
        return result.get("summary", "The briefing was saved, but its summary is empty.")
    if name == "list_briefings":
        briefings = result.get("briefings", [])
        if not briefings:
            return "There are no saved briefings yet."
        return "Recent briefings:\n" + "\n".join(
            f"{item.get('title', 'Briefing')}: {item.get('summary', '')}" for item in briefings
        )
    if name == "list_bookmarks":
        bookmarks = result.get("bookmarks", [])
        if not bookmarks:
            return "You have no saved bookmarks yet."
        return "Your bookmarks:\n" + "\n".join(
            f"{item['title']} — {item['url']}" for item in bookmarks
        )
    if name == "create_task":
        task = result.get("task", {})
        return f"Task added: {task.get('title', 'Untitled')} (ID {task.get('id')})."
    if name == "update_task":
        task = result.get("task", {})
        return f"Updated task {task.get('id')}, {task.get('title')}: status is {task.get('status')}."
    if name == "delete_task":
        task = result.get("task", {})
        return f"Deleted task {task.get('id')}, {task.get('title')}."
    if name == "save_bookmark":
        bookmark = result.get("bookmark", {})
        return f"Saved bookmark: {bookmark.get('title')} — {bookmark.get('url')}"
    if name == "get_settings":
        return "JARVIS settings: " + ", ".join(
            f"{key.replace('_', ' ')}: {value}" for key, value in result.items()
        )
    return json.dumps(result, ensure_ascii=False, default=str)


def _task_json(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": task.status,
        "due_date": task.due_date,
    }


def _bookmark_json(bookmark: Bookmark) -> dict[str, Any]:
    return {"id": bookmark.id, "title": bookmark.title, "url": bookmark.url, "category": bookmark.category}


async def _run_tool(name: str, arguments: dict[str, Any], db: Session) -> dict[str, Any]:
    if name == "clear_chat_history":
        deleted_count = db.query(ChatMessage).delete(synchronize_session=False)
        db.query(Conversation).delete(synchronize_session=False)
        db.commit()
        return {"cleared": True, "deleted_count": deleted_count}

    if name == "list_tasks":
        query = db.query(Task)
        if arguments.get("status"):
            query = query.filter(Task.status == arguments["status"])
        tasks = query.order_by(Task.created_at.desc()).limit(50).all()
        return {"tasks": [_task_json(task) for task in tasks], "count": len(tasks)}

    if name == "create_task":
        title = str(arguments.get("title", "")).strip()
        if not title:
            return {"error": "A task title is required."}
        priority = arguments.get("priority", "medium")
        if priority not in TASK_PRIORITIES:
            return {"error": "Priority must be low, medium, or high."}
        task = Task(
            title=title,
            description=str(arguments.get("description", "")),
            priority=priority,
            status="pending",
            due_date=arguments.get("due_date"),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return {"created": True, "task": _task_json(task)}

    if name in {"update_task", "delete_task"}:
        task_id = arguments.get("task_id")
        if not isinstance(task_id, int):
            return {"error": "A valid task ID is required."}
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"error": f"Task {task_id} was not found."}
        if name == "delete_task":
            deleted = _task_json(task)
            db.delete(task)
            db.commit()
            return {"deleted": True, "task": deleted}

        updates = {key: arguments[key] for key in ("title", "description", "priority", "status", "due_date") if key in arguments}
        if "priority" in updates and updates["priority"] not in TASK_PRIORITIES:
            return {"error": "Priority must be low, medium, or high."}
        if "status" in updates and updates["status"] not in TASK_STATUSES:
            return {"error": "Status must be pending, in_progress, done, or cancelled."}
        if "title" in updates and not str(updates["title"]).strip():
            return {"error": "Task title cannot be empty."}
        for key, value in updates.items():
            setattr(task, key, value)
        db.commit()
        db.refresh(task)
        return {"updated": True, "task": _task_json(task)}

    if name == "get_weather":
        return await get_weather(arguments.get("city"))

    if name == "get_news":
        country = arguments.get("country", "in")
        category = arguments.get("category", "general")
        if country not in NEWS_COUNTRIES or category not in NEWS_CATEGORIES:
            return {"error": "Unsupported news region or category."}
        articles = await fetch_news(category=category, query=arguments.get("query"), country=country)
        return {"country": country, "count": len(articles), "articles": articles[:12]}

    if name == "generate_briefing":
        summary = await generate_daily_briefing()
        briefing = Briefing(title="Daily Briefing", summary=summary)
        db.add(briefing)
        db.commit()
        db.refresh(briefing)
        return {"saved": True, "id": briefing.id, "summary": summary}

    if name == "list_briefings":
        items = db.query(Briefing).order_by(Briefing.created_at.desc()).limit(10).all()
        return {
            "briefings": [
                {"id": item.id, "title": item.title, "summary": item.summary, "created_at": item.created_at}
                for item in items
            ]
        }

    if name == "list_bookmarks":
        bookmarks = db.query(Bookmark).order_by(Bookmark.created_at.desc()).limit(50).all()
        return {"bookmarks": [_bookmark_json(item) for item in bookmarks], "count": len(bookmarks)}

    if name == "save_bookmark":
        title = str(arguments.get("title", "")).strip()
        url = str(arguments.get("url", "")).strip()
        if not title or not url or not url.startswith(("https://", "http://")):
            return {"error": "A title and a valid http/https URL are required to save a bookmark."}
        bookmark = Bookmark(title=title, url=url, category=str(arguments.get("category", "general")))
        db.add(bookmark)
        db.commit()
        db.refresh(bookmark)
        return {"saved": True, "bookmark": _bookmark_json(bookmark)}

    if name == "get_settings":
        return {
            "app_name": settings.APP_NAME,
            "timezone": settings.APP_TIMEZONE,
            "default_city": settings.DEFAULT_CITY,
            "news_enabled": settings.news_enabled(),
            "ai_enabled": settings.ai_enabled(),
        }

    return {"error": f"Unknown JARVIS tool: {name}"}


async def _completion(
    messages: list[dict[str, Any]],
    tool_choice: str | dict[str, Any] = "auto",
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not settings.NVIDIA_API_KEYS:
        raise RuntimeError("NVIDIA API key is not configured.")

    models = list(dict.fromkeys((settings.NVIDIA_MODEL, settings.NVIDIA_FALLBACK_MODEL)))
    async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT_SECONDS) as client:
        keys = settings.NVIDIA_API_KEYS
        first_key = next(_key_rotation) % len(keys)
        last_error = "provider returned an invalid response"
        for model in models:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 768,
                "stream": False,
            }
            if model.startswith("openai/gpt-oss"):
                payload["reasoning_effort"] = "low"
            else:
                payload["reasoning_budget"] = 96
            if tools:
                payload.update(
                    {
                        "tools": tools,
                        "tool_choice": tool_choice,
                        "parallel_tool_calls": False,
                    }
                )

            for offset in range(len(keys)):
                api_key = keys[(first_key + offset) % len(keys)]
                try:
                    response = await client.post(
                        f"{settings.NVIDIA_BASE_URL.rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=payload,
                    )
                except httpx.HTTPError as exc:
                    last_error = f"network error ({type(exc).__name__})"
                    # A network failure is shared by all keys. Try the fallback
                    # model instead of repeating a long wait with each key.
                    break
                if response.status_code != 200:
                    last_error = f"provider returned HTTP {response.status_code}"
                    if response.status_code in {401, 403, 404, 408, 409, 425, 429} or response.status_code >= 500:
                        continue
                    break
                try:
                    body = response.json()
                except ValueError:
                    last_error = "provider returned invalid JSON"
                    continue
                if isinstance(body, dict):
                    return body
                last_error = "provider returned an invalid response"
        raise RuntimeError(last_error)


async def run_agent(message: str, db: Session, conversation_id: int | None = None) -> str:
    history_query = db.query(ChatMessage)
    if conversation_id is not None:
        history_query = history_query.filter(ChatMessage.conversation_id == conversation_id)
    history = history_query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(8).all()
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for entry in reversed(history):
        if re.search(r"don't have access|cannot access|can't access|no access to (?:my |the )?(?:task|weather|news)", entry.response, re.IGNORECASE):
            continue
        messages.append({"role": "user", "content": entry.message[:4000]})
        messages.append({"role": "assistant", "content": entry.response[:4000]})
    messages.append({"role": "user", "content": message[:12000]})

    try:
        initial_tool = _initial_tool_for(message)
        task_change = bool(
            initial_tool == "list_tasks"
            and re.search(r"\b(cancel|complete|finish|done|delete|remove|update|change|edit)\b", message, re.IGNORECASE)
        )
        known_task_ids: set[int] = set()
        task_list: dict[str, Any] | None = None
        for turn in range(5):
            if turn == 0:
                turn_tools = [
                    tool for tool in TOOLS
                    if initial_tool and tool["function"]["name"] == initial_tool
                ]
            else:
                turn_tools = TOOLS
            response = await _completion(
                messages,
                _tool_choice(initial_tool) if turn == 0 else "auto",
                turn_tools,
            )
            choices = response.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                raise RuntimeError("The AI provider returned no answer.")
            assistant_message = choices[0].get("message") or {}
            if not isinstance(assistant_message, dict):
                raise RuntimeError("The AI provider returned an invalid answer.")
            tool_calls = assistant_message.get("tool_calls") or []
            if not tool_calls:
                content = assistant_message.get("content")
                if isinstance(content, list):
                    content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
                if isinstance(content, str) and content.strip():
                    if task_change and task_list is not None:
                        if not task_list.get("tasks"):
                            return _format_tool_result("list_tasks", task_list)
                        return _format_tool_result("list_tasks", task_list) + "\nTell me the task ID or exact title you want me to change."
                    if initial_tool and task_list is None:
                        if initial_tool not in {"create_task", "save_bookmark"}:
                            try:
                                result = await _run_tool(initial_tool, {}, db)
                            except Exception as exc:
                                result = {"error": str(exc)}
                            if initial_tool == "list_tasks" and task_change:
                                task_list = result
                                if not task_list.get("tasks"):
                                    return _format_tool_result(initial_tool, result)
                                return _format_tool_result(initial_tool, result) + "\nTell me the task ID or exact title you want me to change."
                            return _format_tool_result(initial_tool, result)
                        return "I couldn't safely complete that request. Please include the task title, or both a bookmark title and its URL."
                    return content.strip()
                raise RuntimeError("The AI provider returned an empty answer.")

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                function = call.get("function") or {}
                name = function.get("name", "")
                if turn == 0 and initial_tool and name != initial_tool:
                    return "I couldn't safely route that request to the requested JARVIS feature. Please try again."
                raw_arguments = function.get("arguments", "{}")
                try:
                    arguments = raw_arguments if isinstance(raw_arguments, dict) else json.loads(raw_arguments or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be an object.")
                    if name in {"update_task", "delete_task"} and arguments.get("task_id") not in known_task_ids:
                        result = {"error": "That task was not found in the task list. Ask the user which listed task they mean before changing it."}
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id", ""),
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                        )
                        continue
                    result = await _run_tool(name, arguments, db)
                except (ValueError, TypeError, KeyError) as exc:
                    result = {"error": f"Invalid tool request: {exc}"}
                except Exception as exc:
                    result = {"error": str(exc)}
                if name == "list_tasks":
                    task_list = result
                    known_task_ids = {
                        task["id"] for task in result.get("tasks", []) if isinstance(task.get("id"), int)
                    }
                    if not task_change:
                        return _format_tool_result(name, result)
                elif initial_tool:
                    # The response reflects the actual service result, including errors.
                    return _format_tool_result(name, result)
                if result.get("error"):
                    return _format_tool_result(name, result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
        if task_change and task_list is not None:
            if not task_list.get("tasks"):
                return _format_tool_result("list_tasks", task_list)
            return _format_tool_result("list_tasks", task_list) + "\nTell me the task ID or exact title you want me to change."
        return "I reached the limit for this request. Please ask me to continue."
    except (httpx.HTTPError, RuntimeError) as exc:
        return f"JARVIS couldn't complete that request: {exc}"

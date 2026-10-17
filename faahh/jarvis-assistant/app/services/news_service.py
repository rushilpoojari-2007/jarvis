from __future__ import annotations

import copy
import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings

_NEWS_CACHE_TTL_SECONDS = 300
_news_cache: dict[tuple[str, str | None, str], tuple[float, list[dict[str, Any]]]] = {}


async def _fetch_google_news_rss(
    client: httpx.AsyncClient,
    category: str,
    query: str | None,
    country: str,
) -> list[dict[str, Any]]:
    topics = {
        "business": "BUSINESS",
        "entertainment": "ENTERTAINMENT",
        "health": "HEALTH",
        "science": "SCIENCE",
        "sports": "SPORTS",
        "technology": "TECHNOLOGY",
    }
    editions = {
        "in": ("en-IN", "IN", "IN:en"),
        "us": ("en-US", "US", "US:en"),
        "gb": ("en-GB", "GB", "GB:en"),
    }
    language, region, edition = editions[country]
    params = {"hl": language, "gl": region, "ceid": edition}
    if query:
        path = "/rss/search"
        params["q"] = query
    elif category.lower() in topics:
        path = f"/rss/headlines/section/topic/{topics[category.lower()]}"
    else:
        path = "/rss"

    response = await client.get(
        f"https://news.google.com{path}?{urlencode(params)}",
        headers={"User-Agent": "Mozilla/5.0 (compatible; JARVIS/1.0)"},
        follow_redirects=True,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    articles = []
    for item in root.findall(".//item"):
        description = unescape(item.findtext("description") or "")
        description = re.sub(r"<[^>]*>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()
        articles.append(
            {
                "title": item.findtext("title"),
                "source": item.findtext("source") or "Google News",
                "url": item.findtext("link"),
                "description": description,
                "published_at": item.findtext("pubDate"),
            }
        )
    return dedupe_news_articles(articles)


def normalize_news_article(article: dict[str, Any]) -> dict[str, Any]:
    title = (article.get("title") or "Untitled").strip()
    description = article.get("description") or article.get("summary") or ""
    url = article.get("url") or article.get("link") or ""
    source = article.get("source")
    if isinstance(source, dict):
        source_name = source.get("name") or source.get("title") or "unknown"
    else:
        source_name = source or "unknown"
    published_at = article.get("published_at") or article.get("publishedAt") or article.get("published")
    if published_at is None and article.get("date"):
        published_at = article.get("date")
    normalized = {
        "title": title,
        "source": str(source_name),
        "url": url,
        "description": description.strip(),
        "published_at": str(published_at) if published_at else None,
    }
    if normalized["url"]:
        normalized["url"] = normalized["url"].strip()
    return normalized


def dedupe_news_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result: list[dict[str, Any]] = []
    for article in articles:
        normalized = normalize_news_article(article)
        key = (normalized.get("url") or "").strip().lower()
        if key:
            canonical_key = re.sub(r"[?#].*$", "", key)
        else:
            canonical_key = (normalized.get("title") or "").strip().lower()
        if canonical_key in seen:
            continue
        seen.add(canonical_key)
        result.append(normalized)
    return result


async def _fetch_news_uncached(
    category: str = "general",
    query: str | None = None,
    country: str = "in",
) -> list[dict[str, Any]]:
    country = country.lower()
    if country not in {"in", "us", "gb"}:
        raise ValueError("Unsupported news region. Choose India, United States, or United Kingdom.")

    errors: list[str] = []
    async with httpx.AsyncClient(timeout=settings.API_TIMEOUT_SECONDS) as client:
        if settings.NEWS_API_KEY:
            params = {"country": country, "category": category, "language": "en"}
            if query:
                params["q"] = query
            try:
                response = await client.get(
                    "https://newsapi.org/v2/top-headlines",
                    params=params,
                    headers={"X-Api-Key": settings.NEWS_API_KEY},
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") == "ok":
                    articles = dedupe_news_articles(payload.get("articles") or [])
                    if articles:
                        return articles
                    errors.append("NewsAPI returned no articles")
                else:
                    errors.append("NewsAPI returned an error response")
            except httpx.HTTPStatusError as exc:
                errors.append(f"NewsAPI request failed (HTTP {exc.response.status_code})")
            except httpx.RequestError:
                errors.append("NewsAPI request failed (network error)")
            except ValueError:
                errors.append("NewsAPI returned invalid JSON")

        if settings.GNEWS_API_KEY:
            params = {"apikey": settings.GNEWS_API_KEY, "lang": "en", "max": 10, "country": country}
            if query:
                params["q"] = query
            else:
                params["category"] = category
            try:
                response = await client.get("https://gnews.io/api/v4/top-headlines", params=params)
                response.raise_for_status()
                payload = response.json()
                articles = dedupe_news_articles(payload.get("articles") or [])
                if articles:
                    return articles
                errors.append("GNews returned no articles")
            except httpx.HTTPStatusError as exc:
                errors.append(f"GNews request failed (HTTP {exc.response.status_code})")
            except httpx.RequestError:
                errors.append("GNews request failed (network error)")
            except ValueError:
                errors.append("GNews returned invalid JSON")

        if settings.GUARDIAN_API_KEY:
            params = {
                "api-key": settings.GUARDIAN_API_KEY,
                "show-fields": "headline,trailText,body,shortUrl,publication,webPublicationDate",
            }
            if category != "general":
                params["section"] = category
            if query or country == "in":
                params["q"] = query or "India"
            try:
                response = await client.get("https://content.guardianapis.com/search", params=params)
                response.raise_for_status()
                payload = response.json()
                results = payload.get("response", {}).get("results", [])
                normalized = []
                for item in results:
                    body_blocks = (item.get("blocks") or {}).get("body") or []
                    body_summary = body_blocks[0].get("bodyTextSummary") if body_blocks else None
                    normalized.append(
                        {
                            "title": item.get("webTitle"),
                            "source": item.get("pillarName") or "The Guardian",
                            "url": item.get("webUrl"),
                            "description": (item.get("fields", {}) or {}).get("trailText") or body_summary,
                            "published_at": item.get("webPublicationDate"),
                        }
                    )
                articles = dedupe_news_articles(normalized)
                if articles:
                    return articles
                errors.append("The Guardian returned no articles")
            except httpx.HTTPStatusError as exc:
                errors.append(f"The Guardian request failed (HTTP {exc.response.status_code})")
            except httpx.RequestError:
                errors.append("The Guardian request failed (network error)")
            except ValueError:
                errors.append("The Guardian returned invalid JSON")

        try:
            rss_articles = await _fetch_google_news_rss(client, category, query, country)
            if rss_articles:
                return rss_articles
            errors.append("Google News RSS returned no articles")
        except httpx.HTTPStatusError as exc:
            errors.append(f"Google News RSS request failed (HTTP {exc.response.status_code})")
        except httpx.RequestError:
            errors.append("Google News RSS request failed (network error)")
        except (ET.ParseError, ValueError):
            errors.append("Google News RSS returned invalid data")

    if errors:
        raise RuntimeError("All configured news providers failed: " + "; ".join(errors))
    return []


async def fetch_news(
    category: str = "general",
    query: str | None = None,
    country: str = "in",
) -> list[dict[str, Any]]:
    country = country.lower()
    normalized_query = query.strip() if query and query.strip() else None
    key = (category.strip().lower(), normalized_query, country)
    now = time.monotonic()
    cached = _news_cache.get(key)
    if cached and now - cached[0] < _NEWS_CACHE_TTL_SECONDS:
        return copy.deepcopy(cached[1])
    if cached:
        _news_cache.pop(key, None)

    articles = await _fetch_news_uncached(category, normalized_query, country)
    _news_cache[key] = (time.monotonic(), articles)
    if len(_news_cache) > 128:
        _news_cache.pop(next(iter(_news_cache)))
    return copy.deepcopy(articles)

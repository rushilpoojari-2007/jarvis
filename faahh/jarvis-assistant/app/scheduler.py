from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.services.briefing_service import generate_daily_briefing

_scheduler = None
logger = logging.getLogger("jarvis.scheduler")


def _configured_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.APP_TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid APP_TIMEZONE; scheduler will use UTC")
        return ZoneInfo("UTC")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=_configured_timezone())
    _scheduler.add_job(generate_daily_briefing, "interval", hours=6, id="daily_briefing")
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def is_scheduler_running() -> bool:
    return _scheduler is not None and _scheduler.running

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    status: str = "pending"
    priority: str = "medium"
    due_date: str | None = None


class TaskUpdate(TaskCreate):
    pass


class TaskRead(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class BookmarkCreate(BaseModel):
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    category: str = "general"


class BookmarkRead(BookmarkCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class BriefingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str
    created_at: datetime


class ChatMessageCreate(BaseModel):
    message: str = Field(default="", max_length=12000)
    image: str | None = Field(default=None, max_length=7_000_000)


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    response: str
    created_at: datetime


class NewsArticle(BaseModel):
    title: str
    source: str
    url: str
    description: str | None = None
    published_at: str | None = None


class WeatherReport(BaseModel):
    city: str
    country: str
    temperature_c: float | None = None
    weather: str | None = None
    humidity: float | None = None
    summary: str

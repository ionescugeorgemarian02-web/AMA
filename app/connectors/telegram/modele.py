"""Forma actualizărilor primite de la Telegram (doar câmpurile folosite; restul se ignoră)."""

from pydantic import BaseModel, ConfigDict


class Chat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    type: str = "private"


class Mesaj(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: int
    chat: Chat
    text: str | None = None


class Actualizare(BaseModel):
    model_config = ConfigDict(extra="ignore")
    update_id: int
    message: Mesaj | None = None

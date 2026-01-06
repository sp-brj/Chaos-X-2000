from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # task | idea | note
    kind: Mapped[str] = mapped_column(String(16), index=True, default="task")
    # one of: #неделя #месяц #квартал #год (or null)
    horizon_tag: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)

    text: Mapped[str] = mapped_column(Text)  # original user text OR best-effort transcript text
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(280), nullable=True)

    status: Mapped[str] = mapped_column(String(16), index=True, default="open")  # open | closed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw_update: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


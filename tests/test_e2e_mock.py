"""Сквозной сценарий на заглушках: Telegram → оплата → фото → mock-видео."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    GetFile,
    GetMe,
    SendMessage,
    SendVideo,
)
from aiogram.types import CallbackQuery, Chat, File, Message, PhotoSize, Update, User
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot import keyboards, texts
from app.bot.services import BotServices
from app.config import Settings
from app.db import job_queue, models, repo
from app.domain.ledger import LedgerReason
from app.domain.order_service import OrderStatus
from app.engines.mock import MockVideoEngine
from app.main_bot import build_dispatcher
from app.payments.stub import StubPaymentProvider
from app.storage.local import LocalStorage
from app.worker.pipeline import process_job
from app.worker.services import WorkerServices

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
USER = User(id=1001, is_bot=False, first_name="Test")
CHAT = Chat(id=1001, type="private")
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5433/facechanger_test"


class RecordingSession(BaseSession):
    """Фейковая сессия Telegram: записывает вызовы и отдаёт минимальные ответы."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, object]] = []
        self._message_id = 0

    async def make_request(self, bot: Bot, method: object, **kwargs: object) -> object:
        name = type(method).__name__
        self.calls.append((name, method))
        if isinstance(method, (SendMessage, SendVideo)):
            return self._message(method)
        if isinstance(method, AnswerCallbackQuery):
            return True
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="TestBot")
        if isinstance(method, GetFile):
            return File(file_id="photo", file_unique_id="photo", file_path="photo.jpg")
        return True

    async def stream_content(self, *args: object, **kwargs: object):
        yield b""

    async def close(self) -> None:
        return None

    def _message(self, method: object) -> Message:
        self._message_id += 1
        chat_id = int(method.chat_id)
        text = getattr(method, "text", None)
        caption = getattr(method, "caption", None)
        return Message(
            message_id=self._message_id,
            date=NOW,
            chat=Chat(id=chat_id, type="private"),
            text=text,
            caption=caption,
        )


class RecordingBot(Bot):
    """Бот с фейковой сессией и заранее заданными байтами фото."""

    def __init__(self, photo_bytes: bytes) -> None:
        session = RecordingSession()
        super().__init__(token="42:TEST", session=session)
        self.session: RecordingSession = session
        self.photo_bytes = photo_bytes

    async def download(self, file: object, destination: object = None, **kwargs: object):
        target = destination or BytesIO()
        target.write(self.photo_bytes)
        target.seek(0)
        return target


@dataclass(frozen=True)
class Env:
    """Собранные зависимости одного E2E-прогона."""

    dispatcher: Dispatcher
    bot: RecordingBot
    storage: LocalStorage
    worker: WorkerServices
    order_id: int


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (128, 128), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def message(update_id: int, **kwargs: object) -> Message:
    return Message(
        message_id=update_id,
        date=NOW,
        chat=CHAT,
        from_user=USER,
        **kwargs,
    )


def callback(update_id: int, data: str) -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=f"cb-{update_id}",
            from_user=USER,
            chat_instance="chat-instance",
            data=data,
            message=message(update_id),
        ),
    )


def text_update(update_id: int, text: str) -> Update:
    return Update(update_id=update_id, message=message(update_id, text=text))


def photo_update(update_id: int) -> Update:
    data = jpeg_bytes()
    photo = PhotoSize(
        file_id="photo",
        file_unique_id="photo-unique",
        width=128,
        height=128,
        file_size=len(data),
    )
    return Update(update_id=update_id, message=message(update_id, photo=[photo]))


async def build_env(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> Env:
    settings = Settings(
        database_url=DATABASE_URL,
        engine="mock",
        payment_provider="stub",
        storage_dir=tmp_path,
        price_kopecks=100,
        credits_per_order=1,
    )
    storage = LocalStorage(tmp_path)
    bot = RecordingBot(jpeg_bytes())
    bot_services = BotServices(
        settings=settings,
        session_factory=session_factory,
        storage=storage,
        payments=StubPaymentProvider(),
        now=lambda: NOW,
    )
    worker = WorkerServices(
        settings=settings,
        session_factory=session_factory,
        bot=bot,
        engine=MockVideoEngine(tmp_path),
        storage=storage,
        now=lambda: NOW,
    )
    async with session_factory() as db:
        db.add(build_template())
        await db.commit()
    dispatcher = build_dispatcher(bot_services)
    return Env(dispatcher, bot, storage, worker, 0)


def build_template() -> models.Template:
    return models.Template(
        key="default",
        title="Тестовый шаблон",
        source_path="templates/default/source.mp4",
        prompt="Заменить лицо в видео.",
        duration_sec=5,
        resolution="720p",
        credits_cost=1,
        price_kopecks=100,
        is_active=True,
    )


def texts_sent(bot: RecordingBot) -> list[str]:
    return [m.text for name, m in bot.session.calls if name == "SendMessage" and m.text]


def videos_sent(bot: RecordingBot) -> int:
    return sum(name == "SendVideo" for name, _ in bot.session.calls)


@pytest.mark.integration
async def test_mock_scenario_end_to_end(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter(range(0, 100, 10))
    monkeypatch.setattr("app.bot.middlewares.throttle.monotonic", lambda: float(next(ticks)))
    env = await build_env(session, session_factory, tmp_path)

    await env.dispatcher.feed_update(env.bot, text_update(1, "/start"))
    assert texts.CONSENT_TEXT in texts_sent(env.bot)

    await env.dispatcher.feed_update(env.bot, callback(2, keyboards.CONSENT_CALLBACK))
    assert texts.CONSENT_ACCEPTED in texts_sent(env.bot)

    await env.dispatcher.feed_update(env.bot, callback(3, keyboards.CHECKOUT_CALLBACK))
    assert texts.PHOTO_REQUEST in texts_sent(env.bot)

    user = await repo.get_user_by_tg_id(session, USER.id)
    assert user is not None
    order = await repo.get_active_order(session, user.id)
    assert order is not None
    assert order.status is OrderStatus.PAID
    order_id = order.id
    entries = await repo.load_order_ledger(session, order_id)
    assert [entry.reason for entry in entries] == [
        LedgerReason.TOPUP,
        LedgerReason.ORDER_PAID,
    ]

    await env.dispatcher.feed_update(env.bot, photo_update(4))
    assert texts.PHOTO_ACCEPTED in texts_sent(env.bot)
    order = await repo.load_order(session, order_id)
    assert order is not None
    assert order.status is OrderStatus.QUEUED
    assert env.storage.photo_path(order_id).exists()

    claim = await job_queue.claim_job(session, datetime.now(UTC) + timedelta(minutes=1))
    assert claim is not None
    await process_job(env.worker, claim)

    order = await repo.load_order(session, order_id)
    assert order is not None
    assert order.status is OrderStatus.DELIVERED
    assert videos_sent(env.bot) == 1
    assert not env.storage.photo_path(order_id).exists()

    entries = await repo.load_order_ledger(session, order_id)
    assert [entry.reason for entry in entries] == [
        LedgerReason.TOPUP,
        LedgerReason.ORDER_PAID,
    ]
    assert sum(entry.delta for entry in entries) == 0

    job = await session.get(models.Job, claim.id)
    assert job is not None
    assert job.status == job_queue.JobStatus.DONE.value
    assert job.request_id is None  # mock-движок не использует request_id

    events = await session.execute(
        select(models.Event).where(models.Event.name == "order_delivered")
    )
    assert events.scalar_one_or_none() is not None

import asyncio
import json
import logging
import socket
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Callable

from pywebpush import WebPushException, webpush
from telethon import TelegramClient, events
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl import types

from app_config import AppConfig, AppPaths, migrate_legacy_session_if_needed, parse_webpush_subscription


LOGGER_NAME = "tg_notifier"
CONNECT_TIMEOUT = 30
CONNECTION_RETRIES = 10
RETRY_DELAY = 5
VAPID_SUBJECT = "mailto:admin@example.com"

MEDIA_TYPE_LABELS = (
    (types.MessageMediaGeoLive, "геопозиция"),
    (types.MessageMediaVenue, "место"),
    (types.MessageMediaContact, "контакт"),
    (types.MessageMediaPoll, "опрос"),
    (types.MessageMediaDice, "кубик"),
    (types.MessageMediaGame, "игра"),
    (types.MessageMediaInvoice, "счет"),
    (types.MessageMediaWebPage, "ссылка"),
    (types.MessageMediaUnsupported, "вложение"),
)

ACTION_TYPE_LABELS = (
    (types.MessageActionPhoneCall, "звонок"),
    (types.MessageActionPinMessage, "закрепленное сообщение"),
    (types.MessageActionChatAddUser, "приглашение в чат"),
    (types.MessageActionChatJoinedByLink, "вход по ссылке"),
    (types.MessageActionChatCreate, "создание чата"),
    (types.MessageActionChatDeletePhoto, "удаление фото чата"),
    (types.MessageActionChatDeleteUser, "выход из чата"),
    (types.MessageActionChatEditPhoto, "обновление фото чата"),
    (types.MessageActionChatEditTitle, "изменение названия чата"),
    (types.MessageActionHistoryClear, "очистка истории"),
    (types.MessageActionGameScore, "результат игры"),
    (types.MessageActionPaymentSent, "оплата"),
    (types.MessageActionPaymentSentMe, "платеж"),
    (types.MessageActionScreenshotTaken, "скриншот"),
    (types.MessageActionSecureValuesSent, "отправка данных"),
    (types.MessageActionSecureValuesSentMe, "получение данных"),
    (types.MessageActionContactSignUp, "регистрация в Telegram"),
    (types.MessageActionGeoProximityReached, "геоприближение"),
    (types.MessageActionGroupCall, "групповой звонок"),
    (types.MessageActionInviteToGroupCall, "приглашение в звонок"),
    (types.MessageActionSetMessagesTTL, "таймер удаления сообщений"),
    (types.MessageActionTopicCreate, "создание темы"),
    (types.MessageActionTopicEdit, "изменение темы"),
    (types.MessageActionSuggestProfilePhoto, "предложение фото профиля"),
    (types.MessageActionRequestedPeer, "запрос контакта"),
    (types.MessageActionBotAllowed, "запуск бота"),
    (types.MessageActionWebViewDataSent, "данные из web app"),
    (types.MessageActionWebViewDataSentMe, "данные в web app"),
)


def setup_logging(paths: AppPaths, debug_enabled: bool) -> Path:
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = paths.log_path

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    if not any(isinstance(handler, logging.FileHandler) for handler in logger.handlers):
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.setLevel(logging.DEBUG if debug_enabled else logging.INFO)

    return log_path


def build_contact_name(user) -> str:
    first_name = (user.first_name or "").strip()
    last_name = (user.last_name or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    return full_name or "Без имени"


def build_message_content(message) -> str:
    text = (message.raw_text or "").strip()
    if text:
        return text

    if getattr(message, "photo", None):
        return "фото"
    if getattr(message, "video_note", None):
        return "кружочек"
    if getattr(message, "video", None):
        return "видео"
    if getattr(message, "voice", None):
        return "голосовое сообщение"
    if getattr(message, "audio", None):
        return "аудио"
    if getattr(message, "sticker", None):
        return "стикер"
    if getattr(message, "gif", None):
        return "gif"
    if getattr(message, "contact", None):
        return "контакт"
    if getattr(message, "geo", None):
        return "геопозиция"
    if getattr(message, "venue", None):
        return "место"
    if getattr(message, "poll", None):
        return "опрос"
    if getattr(message, "dice", None):
        return "кубик"
    if getattr(message, "game", None):
        return "игра"
    if getattr(message, "invoice", None):
        return "счет"
    if getattr(message, "document", None):
        return "документ"

    media = getattr(message, "media", None)
    for media_type, label in MEDIA_TYPE_LABELS:
        if isinstance(media, media_type):
            return label

    action = getattr(message, "action", None)
    for action_type, label in ACTION_TYPE_LABELS:
        if isinstance(action, action_type):
            return label
    if action is not None:
        return "служебное сообщение"

    return "[Сообщение без текста]"


def describe_error(error: Exception) -> str:
    message = str(error).strip()

    if isinstance(error, asyncio.TimeoutError):
        return "таймаут соединения с Telegram. Проверьте интернет, прокси и повторите попытку"

    if isinstance(error, (ConnectionError, OSError, socket.gaierror)):
        details = message or getattr(error, "strerror", "") or type(error).__name__
        return f"сетевая ошибка: {details}. Проверьте интернет и настройки прокси"

    if message:
        return message

    return f"{type(error).__name__} без текста ошибки"


def build_webpush_payload(contact_name: str, message_content: str, is_test: bool = False) -> str:
    body = f"Сообщение от: {contact_name}"
    title = "Telegram"
    if is_test:
        title = "TG2iOS"
        body = "Тестовое push-уведомление из TG2iOS-Notifier"

    payload = {
        "title": title,
        "body": body,
        "tag": "tg2ios-notifier",
        "data": {
            "sender_name": contact_name,
            "message": message_content,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def send_webpush_notification(
    config: AppConfig,
    contact_name: str,
    message_content: str,
    *,
    is_test: bool = False,
) -> None:
    subscription_data, subscription_error = parse_webpush_subscription(config.webpush_subscription)
    if subscription_error:
        raise ValueError(subscription_error)
    if subscription_data is None:
        raise ValueError("Не задан Subscription JSON для iOS WebPush.")
    if not config.vapid_private_key:
        raise ValueError("Не задан приватный VAPID-ключ.")

    webpush(
        subscription_info=subscription_data,
        data=build_webpush_payload(contact_name, message_content, is_test=is_test),
        vapid_private_key=config.vapid_private_key,
        vapid_claims={"sub": VAPID_SUBJECT},
    )


class TelegramIosNotifierService:
    def __init__(
        self,
        config: AppConfig,
        paths: AppPaths,
        on_status: Callable[[str], None] | None = None,
        on_state: Callable[[dict], None] | None = None,
        on_qr_url: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.paths = paths
        self.on_status = on_status or (lambda _message: None)
        self.on_state = on_state or (lambda _state: None)
        self.on_qr_url = on_qr_url or (lambda _url: None)
        self.logger = logging.getLogger(LOGGER_NAME)

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()
        self._client: TelegramClient | None = None
        self._handler_registered = False
        self._is_running = False
        self._pending_phone = ""
        self._pending_qr_login = None
        self._pending_qr_task: asyncio.Task | None = None
        self._awaiting_code = False
        self._awaiting_password = False
        self._auth_mode = "idle"
        self._authorized_user = ""
        self._client_signature: tuple[str, ...] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        self._loop_ready.wait(timeout=10)

    def shutdown(self) -> None:
        if not self._loop:
            return

        future = self._schedule(self._shutdown_async())
        future.result(timeout=15)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=15)

    def refresh_authorization(self) -> None:
        self._schedule(self._refresh_authorization_async())

    def begin_qr_login(self) -> None:
        self._schedule(self._begin_qr_login_async())

    def send_phone_code(self, phone_number: str) -> None:
        self._schedule(self._send_phone_code_async(phone_number.strip()))

    def submit_code(self, code: str) -> None:
        self._schedule(self._submit_code_async(code.strip()))

    def submit_password(self, password: str) -> None:
        self._schedule(self._submit_password_async(password))

    def start_monitoring(self) -> None:
        self._schedule(self._start_monitoring_async())

    def stop_monitoring(self) -> None:
        self._schedule(self._stop_monitoring_async())

    def send_test_notification(self) -> None:
        self._schedule(self._send_test_notification_async())

    def update_config(self, config: AppConfig) -> None:
        self.config = config
        self.logger.info("Конфигурация приложения обновлена")
        if self._loop:
            future = self._schedule(self._rebuild_client_async())
            future.result(timeout=30)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._loop_ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def _schedule(self, coroutine) -> Future:
        if not self._loop:
            raise RuntimeError("Сервис еще не инициализирован")
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    async def _create_client_async(self) -> None:
        if not self._has_usable_config():
            self._emit_status("Заполните настройки Telegram перед запуском")
            return

        self._client = self._build_client()
        self._client_signature = self._config_signature()
        self.logger.info("Telegram client подготовлен")
        self._emit_status("Сервис готов")

    async def _rebuild_client_async(self) -> None:
        should_restart_monitoring = self._is_running

        if self._pending_qr_task is not None:
            self._pending_qr_task.cancel()
            self._pending_qr_task = None

        if self._client is not None and self._handler_registered:
            self._unregister_handlers()
            self._handler_registered = False

        if self._client is not None and self._client.is_connected():
            await self._client.disconnect()

        self._client = None
        self._client_signature = None
        self._is_running = False
        self._authorized_user = ""
        self._emit_state(running=False, authorized=False, authorized_user="")

        if self._has_usable_config():
            await self._create_client_async()
            if should_restart_monitoring:
                await self._start_monitoring_async()

    def _build_client(self) -> TelegramClient:
        client_kwargs = {
            "timeout": CONNECT_TIMEOUT,
            "connection_retries": CONNECTION_RETRIES,
            "retry_delay": RETRY_DELAY,
            "auto_reconnect": True,
        }

        if self.config.proxy_host and self.config.proxy_port:
            client_kwargs["proxy"] = (
                "socks5",
                self.config.proxy_host,
                int(self.config.proxy_port),
                True,
                self.config.proxy_username or None,
                self.config.proxy_password or None,
            )

        return TelegramClient(
            str(migrate_legacy_session_if_needed(self.paths, self.config.session_name)),
            int(self.config.tg_api_id),
            self.config.tg_api_hash,
            **client_kwargs,
        )

    async def _connect_if_needed(self) -> None:
        if not self._has_usable_config():
            raise ValueError("Конфигурация приложения не заполнена")

        if self._client is None:
            await self._create_client_async()
        elif self._client_signature != self._config_signature():
            await self._rebuild_client_async()

        if self._client is not None and not self._client.is_connected():
            await self._client.connect()

    def _has_usable_config(self) -> bool:
        if not all([self.config.tg_api_id, self.config.tg_api_hash]):
            return False

        try:
            int(self.config.tg_api_id)
            if self.config.proxy_port:
                int(self.config.proxy_port)
        except ValueError:
            return False

        return True

    def _config_signature(self) -> tuple[str, ...]:
        return (
            self.config.tg_api_id,
            self.config.tg_api_hash,
            self.config.proxy_host,
            self.config.proxy_port,
            self.config.proxy_username,
            self.config.proxy_password,
            self.config.session_name,
        )

    async def _refresh_authorization_async(self) -> None:
        if not self._has_usable_config():
            self._authorized_user = ""
            self._emit_state(authorized=False, authorized_user="", running=False)
            self._emit_status("Заполните настройки Telegram перед авторизацией")
            return

        try:
            await self._connect_if_needed()
            assert self._client is not None
            is_authorized = await self._client.is_user_authorized()
            if is_authorized:
                me = await self._client.get_me()
                self._authorized_user = build_contact_name(me)
                self._emit_state(authorized=True, authorized_user=self._authorized_user)
                self._emit_status(f"Telegram авторизован: {self._authorized_user}")
            else:
                self._authorized_user = ""
                self._emit_state(authorized=False, authorized_user="")
                self._emit_status("Telegram еще не авторизован")
        except Exception as error:
            self.logger.exception("Ошибка при проверке авторизации")
            self._emit_status(f"Ошибка проверки авторизации: {describe_error(error)}")

    async def _begin_qr_login_async(self) -> None:
        try:
            await self._connect_if_needed()
            assert self._client is not None

            if await self._client.is_user_authorized():
                self._emit_status("Telegram уже авторизован")
                await self._refresh_authorization_async()
                return

            if self._pending_qr_task is not None:
                self._pending_qr_task.cancel()

            self._auth_mode = "qr"
            self._awaiting_password = False
            self._awaiting_code = False
            self._pending_qr_login = await self._client.qr_login()
            self._emit_state(auth_mode="qr", awaiting_password=False, awaiting_code=False)
            self.on_qr_url(self._pending_qr_login.url)
            self._emit_status("QR-код создан. Отсканируйте его в Telegram.")
            self._pending_qr_task = asyncio.create_task(self._wait_for_qr_login())
        except Exception as error:
            self.logger.exception("Ошибка запуска QR авторизации")
            self._emit_status(f"Ошибка запуска QR: {describe_error(error)}")

    async def _wait_for_qr_login(self) -> None:
        try:
            assert self._pending_qr_login is not None
            await self._pending_qr_login.wait()
            self._emit_status("QR-авторизация успешно завершена")
            self._pending_qr_login = None
            await self._reset_auth_flags_async()
            await self._refresh_authorization_async()
        except SessionPasswordNeededError:
            self._awaiting_password = True
            self._emit_state(awaiting_password=True, auth_mode="qr")
            self._emit_status("Нужен пароль двухэтапной аутентификации Telegram")
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self.logger.exception("Ошибка ожидания QR авторизации")
            self._emit_status(f"Ошибка QR-авторизации: {describe_error(error)}")

    async def _send_phone_code_async(self, phone_number: str) -> None:
        if not phone_number:
            self._emit_status("Введите номер телефона для авторизации")
            return

        try:
            await self._connect_if_needed()
            assert self._client is not None

            await self._client.send_code_request(phone_number)
            self._pending_phone = phone_number
            self._auth_mode = "phone"
            self._awaiting_code = True
            self._awaiting_password = False
            self._emit_state(auth_mode="phone", awaiting_code=True, awaiting_password=False)
            self._emit_status("Код подтверждения отправлен в Telegram")
        except Exception as error:
            self.logger.exception("Ошибка отправки кода авторизации")
            self._emit_status(f"Не удалось отправить код: {describe_error(error)}")

    async def _submit_code_async(self, code: str) -> None:
        if not self._pending_phone:
            self._emit_status("Сначала запросите код для входа")
            return
        if not code:
            self._emit_status("Введите код подтверждения")
            return

        try:
            await self._connect_if_needed()
            assert self._client is not None

            await self._client.sign_in(phone=self._pending_phone, code=code)
            self._emit_status("Авторизация по коду завершена")
            await self._reset_auth_flags_async()
            await self._refresh_authorization_async()
        except SessionPasswordNeededError:
            self._awaiting_password = True
            self._awaiting_code = False
            self._emit_state(awaiting_password=True, awaiting_code=False, auth_mode="phone")
            self._emit_status("Нужен пароль двухэтапной аутентификации Telegram")
        except PhoneCodeInvalidError:
            self._emit_status("Неверный код подтверждения")
        except PhoneCodeExpiredError:
            self._emit_status("Срок действия кода истек. Запросите новый код.")
        except Exception as error:
            self.logger.exception("Ошибка подтверждения кода")
            self._emit_status(f"Не удалось подтвердить код: {describe_error(error)}")

    async def _submit_password_async(self, password: str) -> None:
        if not password:
            self._emit_status("Введите пароль двухэтапной аутентификации")
            return

        try:
            await self._connect_if_needed()
            assert self._client is not None
            await self._client.sign_in(password=password)
            self._emit_status("Пароль принят, авторизация завершена")
            await self._reset_auth_flags_async()
            await self._refresh_authorization_async()
        except PasswordHashInvalidError:
            self._emit_status("Неверный пароль двухэтапной аутентификации")
        except Exception as error:
            self.logger.exception("Ошибка ввода пароля")
            self._emit_status(f"Не удалось авторизоваться по паролю: {describe_error(error)}")

    async def _start_monitoring_async(self) -> None:
        if not self._has_push_configuration():
            self._emit_status("Сначала сохраните VAPID-ключи и корректный Subscription JSON")
            return

        try:
            await self._connect_if_needed()
            assert self._client is not None
            if not await self._client.is_user_authorized():
                self._emit_status("Сначала авторизуйтесь в Telegram")
                self._emit_state(authorized=False)
                return

            if not self._handler_registered:
                self._register_handlers()
                self._handler_registered = True

            self._is_running = True
            self._emit_state(running=True)
            self._emit_status("Мониторинг Telegram включен")
        except Exception as error:
            self.logger.exception("Ошибка запуска мониторинга")
            self._emit_status(f"Не удалось запустить мониторинг: {describe_error(error)}")

    async def _stop_monitoring_async(self) -> None:
        try:
            if self._client is not None and self._handler_registered:
                self._unregister_handlers()
                self._handler_registered = False
            if self._client is not None and self._client.is_connected():
                await self._client.disconnect()
            self._is_running = False
            self._emit_state(running=False)
            self._emit_status("Мониторинг остановлен")
        except Exception as error:
            self.logger.exception("Ошибка остановки мониторинга")
            self._emit_status(f"Не удалось остановить мониторинг: {error}")

    async def _shutdown_async(self) -> None:
        if self._pending_qr_task is not None:
            self._pending_qr_task.cancel()

        if self._client is not None and self._handler_registered:
            self._unregister_handlers()
            self._handler_registered = False

        if self._client is not None and self._client.is_connected():
            await self._client.disconnect()

        self._is_running = False

    async def _reset_auth_flags_async(self) -> None:
        self._pending_phone = ""
        self._awaiting_code = False
        self._awaiting_password = False
        self._auth_mode = "idle"
        self._emit_state(awaiting_code=False, awaiting_password=False, auth_mode="idle")

    async def _send_test_notification_async(self) -> None:
        if not self._has_push_configuration():
            self._emit_status("Сначала сохраните корректный Subscription JSON для iPhone")
            return

        try:
            await asyncio.to_thread(
                send_webpush_notification,
                self.config,
                "Тестовый контакт Telegram",
                "Тестовое сообщение",
                is_test=True,
            )
        except ValueError as error:
            self._emit_status(str(error))
            return
        except WebPushException as error:
            self.logger.error("Ошибка отправки WebPush: %s", error)
            self._emit_status(f"Ошибка отправки WebPush: {error}")
            return
        except Exception as error:
            self.logger.exception("Не удалось отправить тестовый WebPush")
            self._emit_status(f"Не удалось отправить тестовый WebPush: {error}")
            return

        self.logger.info("Тестовое уведомление iOS WebPush отправлено")
        self._emit_status("Тестовое уведомление iOS WebPush отправлено")

    async def _handle_new_private_message(self, event) -> None:
        self.logger.debug(
            "Получено сообщение private=%s out=%s sender_id=%s",
            event.is_private,
            event.out,
            event.sender_id,
        )

        if event.out or not event.is_private:
            return

        sender = await event.get_sender()
        if sender is None:
            self.logger.debug("Не удалось получить отправителя сообщения")
            return

        contact_name = build_contact_name(sender)
        is_contact = getattr(sender, "contact", False)
        is_mutual_contact = getattr(sender, "mutual_contact", False)
        if not (is_contact or is_mutual_contact):
            self.logger.debug("Сообщение пропущено: %s не является контактом", contact_name)
            return

        message_content = build_message_content(event.message)
        self.logger.info(
            "Новое сообщение от контакта %s: %s",
            contact_name,
            message_content,
        )
        try:
            await asyncio.to_thread(
                send_webpush_notification,
                self.config,
                contact_name,
                message_content,
            )
        except ValueError as error:
            self.logger.warning("WebPush не отправлен: %s", error)
            self._emit_status(str(error))
            return
        except WebPushException as error:
            self.logger.error("Ошибка отправки WebPush для %s: %s", contact_name, error)
            self._emit_status(f"Ошибка отправки WebPush: {error}")
            return
        except Exception as error:
            self.logger.exception("Не удалось отправить WebPush")
            self._emit_status(f"Не удалось отправить WebPush: {error}")
            return

        self.logger.info("Уведомление iOS WebPush отправлено для контакта: %s", contact_name)
        self._emit_status(f"Уведомление отправлено для контакта: {contact_name}")

    def _has_push_configuration(self) -> bool:
        if not self.config.vapid_public_key or not self.config.vapid_private_key:
            return False
        subscription_data, subscription_error = parse_webpush_subscription(self.config.webpush_subscription)
        return subscription_data is not None and subscription_error is None

    def _register_handlers(self) -> None:
        assert self._client is not None
        self._client.add_event_handler(
            self._handle_new_private_message,
            events.NewMessage(incoming=True),
        )

    def _unregister_handlers(self) -> None:
        if self._client is None:
            return
        self._client.remove_event_handler(self._handle_new_private_message)

    def _emit_status(self, message: str) -> None:
        self.logger.info(message)
        self.on_status(message)

    def _emit_state(self, **changes) -> None:
        state = {
            "authorized": bool(self._authorized_user),
            "authorized_user": self._authorized_user,
            "running": self._is_running,
            "awaiting_code": self._awaiting_code,
            "awaiting_password": self._awaiting_password,
            "auth_mode": self._auth_mode,
        }
        state.update(changes)

        if "authorized_user" in state:
            self._authorized_user = state["authorized_user"] or ""
            state["authorized"] = bool(self._authorized_user)
        if "running" in state:
            self._is_running = bool(state["running"])
        if "awaiting_code" in state:
            self._awaiting_code = bool(state["awaiting_code"])
        if "awaiting_password" in state:
            self._awaiting_password = bool(state["awaiting_password"])
        if "auth_mode" in state:
            self._auth_mode = state["auth_mode"]

        self.on_state(state)

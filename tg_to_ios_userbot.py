import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

try:
    import qrcode
except ImportError:
    qrcode = None

from app_config import get_app_paths, load_config, parse_webpush_subscription, validate_config
from bot_core import (
    CONNECT_TIMEOUT,
    CONNECTION_RETRIES,
    RETRY_DELAY,
    build_contact_name,
    build_message_content,
    send_webpush_notification,
)


BASE_DIR = Path(__file__).resolve().parent
LOGGER = logging.getLogger("tg_to_ios_userbot")

load_dotenv(BASE_DIR / ".env")

AUTH_MODE = os.getenv("TG_AUTH_MODE", "phone").strip().lower()


def build_telegram_client(config) -> TelegramClient:
    client_kwargs = {
        "timeout": CONNECT_TIMEOUT,
        "connection_retries": CONNECTION_RETRIES,
        "retry_delay": RETRY_DELAY,
        "auto_reconnect": True,
    }

    if config.proxy_host and config.proxy_port:
        client_kwargs["proxy"] = (
            "socks5",
            config.proxy_host,
            int(config.proxy_port),
            True,
            config.proxy_username or None,
            config.proxy_password or None,
        )

    return TelegramClient(config.session_name, int(config.tg_api_id), config.tg_api_hash, **client_kwargs)


async def authorize_with_qr(client: TelegramClient) -> None:
    await client.connect()
    if await client.is_user_authorized():
        return

    qr_login = await client.qr_login()
    print("Откройте Telegram: Настройки -> Устройства -> Подключить устройство.")
    if qrcode is not None:
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_login.url)
        qr.print_ascii(invert=True)
    else:
        print(qr_login.url)

    try:
        await qr_login.wait()
    except SessionPasswordNeededError:
        password = input("Введите пароль двухэтапной аутентификации Telegram: ")
        await client.sign_in(password=password)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    paths = get_app_paths(BASE_DIR)
    config = load_config(paths)

    errors = validate_config(config)
    if errors:
        print("Конфигурация заполнена не полностью:")
        for error in errors:
            print(f"- {error}")
        return

    subscription_data, subscription_error = parse_webpush_subscription(config.webpush_subscription)
    if subscription_error or subscription_data is None:
        print("Сначала получите и сохраните корректный Subscription JSON из PWA на iPhone.")
        return

    if AUTH_MODE not in {"phone", "qr"}:
        print("Переменная TG_AUTH_MODE должна быть 'phone' или 'qr'.")
        return

    client = build_telegram_client(config)

    @client.on(events.NewMessage(incoming=True))
    async def handle_new_private_message(event) -> None:
        if event.out or not event.is_private:
            return

        sender = await event.get_sender()
        if sender is None:
            return

        is_contact = getattr(sender, "contact", False)
        is_mutual_contact = getattr(sender, "mutual_contact", False)
        if not (is_contact or is_mutual_contact):
            return

        contact_name = build_contact_name(sender)
        message_content = build_message_content(event.message)
        print(f"Новое сообщение от {contact_name}: {message_content}")

        try:
            await asyncio.to_thread(send_webpush_notification, config, contact_name, message_content)
            print(f"WebPush отправлен для контакта: {contact_name}")
        except Exception as error:
            print(f"Не удалось отправить WebPush: {error}")

    if AUTH_MODE == "qr":
        await authorize_with_qr(client)
    else:
        client.start()

    me = await client.get_me()
    print(f"Telegram авторизован: {build_contact_name(me)}")
    print("Мониторинг входящих сообщений запущен")
    await client.run_until_disconnected()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

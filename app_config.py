import base64
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from dotenv import load_dotenv


DEFAULT_SESSION_NAME = "tg_userbot_session"


@dataclass
class AppConfig:
    tg_api_id: str = ""
    tg_api_hash: str = ""
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    webpush_subscription: str = ""
    proxy_host: str = ""
    proxy_port: str = ""
    proxy_username: str = ""
    proxy_password: str = ""
    debug_log: bool = True
    session_name: str = DEFAULT_SESSION_NAME


@dataclass(frozen=True)
class AppPaths:
    app_dir: Path
    config_path: Path
    logs_dir: Path
    log_path: Path
    session_dir: Path
    legacy_app_dirs: tuple[Path, ...]
    legacy_config_path: Path
    legacy_env_path: Path
    legacy_session_dir: Path


def _normalize_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _base64url_encode(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")


def generate_vapid_keys() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_value = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _base64url_encode(public_bytes), _base64url_encode(private_value)


def parse_webpush_subscription(subscription_raw: str) -> tuple[dict | None, str | None]:
    subscription_text = _normalize_string(subscription_raw)
    if not subscription_text:
        return None, None

    try:
        subscription_data = json.loads(subscription_text)
    except json.JSONDecodeError as error:
        return None, f"Subscription JSON содержит ошибку: {error.msg}."

    if not isinstance(subscription_data, dict):
        return None, "Subscription JSON должен быть объектом JSON."

    endpoint = subscription_data.get("endpoint")
    keys = subscription_data.get("keys")
    if not isinstance(endpoint, str) or not endpoint.strip():
        return None, "Subscription JSON должен содержать непустое поле 'endpoint'."
    if not isinstance(keys, dict):
        return None, "Subscription JSON должен содержать объект 'keys'."
    if not _normalize_string(keys.get("p256dh")) or not _normalize_string(keys.get("auth")):
        return None, "Subscription JSON должен содержать ключи 'p256dh' и 'auth'."

    return subscription_data, None


def ensure_vapid_keys(config: AppConfig) -> tuple[AppConfig, bool]:
    if config.vapid_public_key and config.vapid_private_key:
        return config, False

    public_key, private_key = generate_vapid_keys()
    config.vapid_public_key = public_key
    config.vapid_private_key = private_key
    return config, True


def get_app_paths(base_dir: Path) -> AppPaths:
    appdata_root = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    app_dir = appdata_root / "TgIosNotifier"
    return AppPaths(
        app_dir=app_dir,
        config_path=app_dir / "app_config.json",
        logs_dir=app_dir / "logs",
        log_path=app_dir / "logs" / "app.log",
        session_dir=app_dir / "session",
        legacy_app_dirs=(appdata_root / "TgDsNotifier", appdata_root / "TgVkNotifier"),
        legacy_config_path=base_dir / "app_config.json",
        legacy_env_path=base_dir / ".env",
        legacy_session_dir=base_dir,
    )


def _build_config(data: dict) -> AppConfig:
    subscription_value = data.get("webpush_subscription", "")
    if isinstance(subscription_value, dict):
        subscription_value = json.dumps(subscription_value, ensure_ascii=False, indent=2)

    return AppConfig(
        tg_api_id=_normalize_string(data.get("tg_api_id")),
        tg_api_hash=_normalize_string(data.get("tg_api_hash")),
        vapid_public_key=_normalize_string(data.get("vapid_public_key")),
        vapid_private_key=_normalize_string(data.get("vapid_private_key")),
        webpush_subscription=_normalize_string(subscription_value),
        proxy_host=_normalize_string(data.get("proxy_host")),
        proxy_port=_normalize_string(data.get("proxy_port")),
        proxy_username=_normalize_string(data.get("proxy_username")),
        proxy_password=_normalize_string(data.get("proxy_password")),
        debug_log=bool(data.get("debug_log", True)),
        session_name=_normalize_string(data.get("session_name")) or DEFAULT_SESSION_NAME,
    )


def _load_json_config(config_path: Path) -> dict | None:
    if not config_path.exists():
        return None
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_config(paths: AppPaths) -> AppConfig:
    config = None
    loaded_from_current_path = False

    current_data = _load_json_config(paths.config_path)
    if current_data is not None:
        config = _build_config(current_data)
        loaded_from_current_path = True

    if config is None:
        for legacy_dir in paths.legacy_app_dirs:
            legacy_data = _load_json_config(legacy_dir / "app_config.json")
            if legacy_data is not None:
                config = _build_config(legacy_data)
                break

    if config is None:
        legacy_data = _load_json_config(paths.legacy_config_path)
        if legacy_data is not None:
            config = _build_config(legacy_data)

    if config is None:
        load_dotenv(paths.legacy_env_path)
        config = AppConfig(
            tg_api_id=_normalize_string(os.getenv("TG_API_ID")),
            tg_api_hash=_normalize_string(os.getenv("TG_API_HASH")),
            vapid_public_key=_normalize_string(os.getenv("VAPID_PUBLIC_KEY")),
            vapid_private_key=_normalize_string(os.getenv("VAPID_PRIVATE_KEY")),
            webpush_subscription=_normalize_string(os.getenv("WEBPUSH_SUBSCRIPTION")),
            proxy_host=_normalize_string(os.getenv("PROXY_HOST")),
            proxy_port=_normalize_string(os.getenv("PROXY_PORT")),
            proxy_username=_normalize_string(os.getenv("PROXY_USERNAME")),
            proxy_password=_normalize_string(os.getenv("PROXY_PASSWORD")),
            debug_log=_normalize_string(os.getenv("DEBUG_LOG", "1")) == "1",
            session_name=_normalize_string(os.getenv("SESSION_NAME")) or DEFAULT_SESSION_NAME,
        )

    config, generated_keys = ensure_vapid_keys(config)
    if generated_keys or not loaded_from_current_path:
        save_config(paths, config)

    return config


def save_config(paths: AppPaths, config: AppConfig) -> Path:
    paths.app_dir.mkdir(parents=True, exist_ok=True)
    config_path = paths.config_path
    payload = asdict(config)
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path


def get_session_storage_path(paths: AppPaths, session_name: str) -> Path:
    return paths.session_dir / (session_name or DEFAULT_SESSION_NAME)


def migrate_legacy_session_if_needed(paths: AppPaths, session_name: str) -> Path:
    paths.session_dir.mkdir(parents=True, exist_ok=True)
    target = get_session_storage_path(paths, session_name)
    target_session = target.with_suffix(".session")
    target_journal = target.with_suffix(".session-journal")

    if target_session.exists() or target_journal.exists():
        return target

    legacy_sources = [
        legacy_dir / "session" / (session_name or DEFAULT_SESSION_NAME)
        for legacy_dir in paths.legacy_app_dirs
    ]
    legacy_sources.append(paths.legacy_session_dir / (session_name or DEFAULT_SESSION_NAME))

    legacy_session = None
    legacy_journal = None
    for legacy in legacy_sources:
        candidate_session = legacy.with_suffix(".session")
        candidate_journal = legacy.with_suffix(".session-journal")
        if candidate_session.exists() or candidate_journal.exists():
            legacy_session = candidate_session
            legacy_journal = candidate_journal
            break

    if legacy_session is not None and legacy_session.exists():
        target_session.write_bytes(legacy_session.read_bytes())
    if legacy_journal is not None and legacy_journal.exists():
        target_journal.write_bytes(legacy_journal.read_bytes())

    return target


def validate_config(config: AppConfig) -> list[str]:
    errors: list[str] = []

    if not config.tg_api_id:
        errors.append("Не заполнено поле TG API ID.")
    if not config.tg_api_hash:
        errors.append("Не заполнено поле TG API Hash.")
    if not config.vapid_public_key or not config.vapid_private_key:
        errors.append("VAPID-ключи не сгенерированы.")

    if config.tg_api_id:
        try:
            int(config.tg_api_id)
        except ValueError:
            errors.append("TG API ID должен быть целым числом.")

    if config.proxy_port:
        try:
            int(config.proxy_port)
        except ValueError:
            errors.append("Proxy Port должен быть целым числом.")

    _, subscription_error = parse_webpush_subscription(config.webpush_subscription)
    if subscription_error:
        errors.append(subscription_error)

    return errors

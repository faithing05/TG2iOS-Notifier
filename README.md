# TG2iOS-Notifier

Windows desktop-приложение на `PyQt5` + `Telethon`, которое работает как Telegram userbot и отправляет уведомления напрямую на iPhone через iOS WebPush.

## Возможности

- desktop UI на `PyQt5`
- сворачивание в системный трей Windows
- авторизация Telegram по QR-коду
- авторизация Telegram по номеру телефона, коду и 2FA-паролю
- автоматическая генерация VAPID-ключей на Python при первом запуске
- хранение `Subscription JSON`, полученного с iPhone
- отправка WebPush-уведомлений напрямую на push-инфраструктуру Apple через `pywebpush`
- логирование в окно приложения и в `%AppData%\TgIosNotifier\logs\app.log`
- сохранение настроек в `%AppData%\TgIosNotifier\app_config.json`
- хранение Telegram-сессии в `%AppData%\TgIosNotifier\session\`

## Установка

```bash
pip install -r requirements.txt
```

## Где взять Telegram API

1. Перейдите на `https://my.telegram.org`.
2. Откройте `API development tools`.
3. Создайте приложение.
4. Скопируйте `api_id` и `api_hash`.

## Запуск desktop-приложения

```bash
python desktop_app.py
```

## Привязка iPhone

1. Откройте вкладку `Настройки`.
2. Заполните `TG API ID` и `TG API Hash`.
3. Скопируйте `VAPID Public Key` из приложения.
4. Разместите файлы `index.html`, `frontend.js`, `manifest.json` и `serviceworker.js` из корня проекта на HTTPS-хостинге, например GitHub Pages.
5. Откройте страницу на iPhone через Safari и добавьте ее на экран `Домой`.
6. Запустите PWA с домашнего экрана.
7. Вставьте `VAPID Public Key` в поле на странице и нажмите `Subscribe`.
8. Скопируйте появившийся `Subscription JSON`.
9. Вставьте его в desktop-приложение в поле `Subscription JSON`.
10. Сохраните настройки.

## Авторизация Telegram

### Вход по QR

1. Нажмите `Показать QR`.
2. В Telegram откройте `Настройки` -> `Устройства` -> `Подключить устройство`.
3. Отсканируйте QR-код.
4. Если включена двухэтапная защита, введите пароль 2FA в приложении.

### Вход по номеру телефона

1. Введите номер телефона в международном формате.
2. Нажмите `Получить код`.
3. Введите код из Telegram.
4. Если включена двухэтапная защита, введите пароль 2FA.

## Мониторинг

1. После успешной авторизации и сохранения валидного `Subscription JSON` нажмите `Старт`.
2. Приложение начнет слушать новые входящие личные сообщения.
3. Уведомления отправляются только для пользователей, которые есть в Telegram-контактах или являются взаимными контактами.
4. Для быстрой проверки используйте кнопку `Тест iOS WebPush`.
5. При закрытии окна приложение не завершится, а свернется в трей.

## Консольный режим

Для запуска без GUI используйте:

```bash
python tg_to_ios_userbot.py
```

Скрипт читает конфиг из `%AppData%\TgIosNotifier\app_config.json` и при необходимости умеет брать Telegram-настройки из `.env`.

## Сборка в `.exe`

```bash
build_app.bat
```

Скрипт делает релизную `onefile`-сборку и кладет итоговый файл в `dist\TgIosNotifier.exe`.

Если нужно собрать вручную:

```bash
pyinstaller --clean --onefile --noconsole --name TgIosNotifier desktop_app.py
```

## Хранение файлов

- настройки приложения: `%AppData%\TgIosNotifier\app_config.json`
- лог-файл: `%AppData%\TgIosNotifier\logs\app.log`
- сессия Telegram: `%AppData%\TgIosNotifier\session\tg_userbot_session.session`

## Миграция старых данных

- приложение умеет читать старый `app_config.json` при первом запуске
- старая Telegram-сессия из `%AppData%\TgDsNotifier` или `%AppData%\TgVkNotifier` будет мягко скопирована в `%AppData%\TgIosNotifier`
- старые файлы автоматически не удаляются

## Примечания

- `app_config.json` и `.env` не должны попадать в публичный репозиторий.
- после регенерации VAPID-ключей старый `Subscription JSON` нужно получить заново.
- iOS WebPush работает только для PWA, открытого с домашнего экрана.

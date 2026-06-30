const subscribeButton = document.getElementById('subscribe_btn');
const copyButton = document.getElementById('copy_btn');
const vapidInput = document.getElementById('vapid_public_key');
const subscriptionBlock = document.getElementById('subscription_block');
const subscriptionOutput = document.getElementById('subscription_output');
const statusBox = document.getElementById('status');
const addToHomeScreenBox = document.getElementById('add-to-home-screen');
const siteVersionBox = document.getElementById('site_version');

function setStatus(message, isError = false) {
    statusBox.textContent = message;
    statusBox.className = isError ? 'status error' : 'status';
    statusBox.style.display = 'block';
}

function formatVersionLabel(versionInfo) {
    if (!versionInfo || typeof versionInfo !== 'object') {
        return 'Версия сайта: неизвестно';
    }

    const version = typeof versionInfo.version === 'string' && versionInfo.version.trim()
        ? versionInfo.version.trim()
        : 'unknown';
    const updatedAt = typeof versionInfo.updated_at === 'string' && versionInfo.updated_at.trim()
        ? versionInfo.updated_at.trim()
        : '';

    return updatedAt
        ? `Версия сайта: ${version} (${updatedAt})`
        : `Версия сайта: ${version}`;
}

async function loadSiteVersion() {
    if (!siteVersionBox) {
        return;
    }

    try {
        const response = await fetch(`./version.json?v=${Date.now()}`, { cache: 'no-store' });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const versionInfo = await response.json();
        siteVersionBox.textContent = formatVersionLabel(versionInfo);
    } catch (error) {
        siteVersionBox.textContent = 'Версия сайта: недоступна';
    }
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}

function isPushManagerActive(pushManager) {
    if (pushManager) {
        return true;
    }

    if (!window.navigator.standalone) {
        addToHomeScreenBox.style.display = 'block';
        setStatus('Откройте страницу с домашнего экрана iPhone, чтобы активировать WebPush.', true);
        return false;
    }

    throw new Error('PushManager is not active');
}

function displaySubscriptionInfo(subscription) {
    if (!subscription) {
        return;
    }

    const jsonText = JSON.stringify(subscription.toJSON(), null, 2);
    subscriptionOutput.value = jsonText;
    subscriptionBlock.style.display = 'block';
    setStatus('Подписка оформлена. Скопируйте Subscription JSON и вставьте его в desktop-приложение.');
}

async function initServiceWorker() {
    const swRegistration = await navigator.serviceWorker.register('./serviceworker.js', { scope: './' });
    const pushManager = swRegistration.pushManager;
    if (!isPushManagerActive(pushManager)) {
        subscribeButton.disabled = true;
        return;
    }

    const permissionState = await pushManager.permissionState({ userVisibleOnly: true });
    if (permissionState === 'granted') {
        const activeSubscription = await pushManager.getSubscription();
        if (activeSubscription) {
            displaySubscriptionInfo(activeSubscription);
            subscribeButton.textContent = 'Resubscribe';
        }
        return;
    }

    if (permissionState === 'denied') {
        subscribeButton.disabled = true;
        setStatus('Разрешение на push-уведомления отклонено в настройках iOS/Safari.', true);
    }
}

async function subscribeToPush() {
    const vapidPublicKey = vapidInput.value.trim();
    if (!vapidPublicKey) {
        setStatus('Сначала вставьте VAPID Public Key из TG2iOS-Notifier.', true);
        return;
    }

    try {
        const swRegistration = await navigator.serviceWorker.getRegistration();
        if (!swRegistration || !isPushManagerActive(swRegistration.pushManager)) {
            setStatus('Service Worker недоступен.', true);
            return;
        }

        const subscription = await swRegistration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
        });
        displaySubscriptionInfo(subscription);
        subscribeButton.textContent = 'Resubscribe';
    } catch (error) {
        setStatus(`Не удалось оформить подписку: ${error.message || error}`, true);
    }
}

async function copySubscriptionToClipboard() {
    if (!subscriptionOutput.value.trim()) {
        return;
    }

    try {
        await navigator.clipboard.writeText(subscriptionOutput.value);
        setStatus('Subscription JSON скопирован в буфер обмена.');
    } catch (error) {
        setStatus(`Не удалось скопировать JSON: ${error.message || error}`, true);
    }
}

subscribeButton.addEventListener('click', subscribeToPush);
copyButton.addEventListener('click', copySubscriptionToClipboard);
loadSiteVersion();

if (navigator.serviceWorker) {
    initServiceWorker().catch((error) => setStatus(`Ошибка инициализации: ${error.message || error}`, true));
} else {
    setStatus('Service Worker не поддерживается этим браузером.', true);
    subscribeButton.disabled = true;
}

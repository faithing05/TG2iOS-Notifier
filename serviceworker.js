self.addEventListener('push', (event) => {
    let pushData = {};
    try {
        pushData = event.data ? event.data.json() : {};
    } catch (error) {
        console.error('Invalid WebPush payload', error);
    }

    const senderName = pushData.data && pushData.data.sender_name
        ? String(pushData.data.sender_name).trim()
        : '';
    const messageText = pushData.data && pushData.data.message
        ? String(pushData.data.message).trim()
        : '';
    const title = senderName || pushData.title || 'Telegram';
    const options = {
        body: messageText || pushData.body || 'Новое уведомление',
        data: pushData.data || {},
        icon: pushData.icon || './telegram-icon.svg',
        badge: pushData.badge || './telegram-icon.svg',
        tag: pushData.tag || 'tg2ios-notifier',
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const targetUrl = event.notification.data && event.notification.data.url
        ? event.notification.data.url
        : self.registration.scope;

    event.waitUntil(clients.openWindow(targetUrl));
});

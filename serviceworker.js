self.addEventListener('push', (event) => {
    let pushData = {};
    try {
        pushData = event.data ? event.data.json() : {};
    } catch (error) {
        console.error('Invalid WebPush payload', error);
    }

    const action = pushData.action || 'show';
    const senderName = pushData.data && pushData.data.sender_name
        ? String(pushData.data.sender_name).trim()
        : '';
    const messageText = pushData.data && pushData.data.message
        ? String(pushData.data.message).trim()
        : '';
    const notificationData = pushData.data || {};
    const chatTag = notificationData.chat_tag || pushData.tag || '';

    if (action === 'clear') {
        event.waitUntil((async () => {
            const notifications = await self.registration.getNotifications();
            for (const notification of notifications) {
                const notificationChatTag = notification.data && notification.data.chat_tag
                    ? notification.data.chat_tag
                    : '';
                if (notification.tag === chatTag || notificationChatTag === chatTag) {
                    notification.close();
                }
            }
        })());
        return;
    }

    const title = senderName || pushData.title || 'Telegram';
    const options = {
        body: messageText || pushData.body || 'Новое уведомление',
        data: notificationData,
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

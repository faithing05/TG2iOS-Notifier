self.addEventListener('push', (event) => {
    let pushData = {};
    try {
        pushData = event.data ? event.data.json() : {};
    } catch (error) {
        console.error('Invalid WebPush payload', error);
    }

    const title = pushData.title || 'TG2iOS';
    const options = {
        body: pushData.body || 'Новое уведомление',
        data: pushData.data || {},
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

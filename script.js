// Инициализация Telegram Web App
const tg = window.Telegram.WebApp;

// Сразу говорим Telegram, что приложение готово
tg.ready();

// Растягиваем на весь экран
tg.expand();

// Получаем информацию о пользователе
const user = tg.initDataUnsafe?.user;
const statusDiv = document.getElementById('status');
const debugDiv = document.getElementById('debug');

// Показываем статус
if (user) {
    statusDiv.textContent = `👋 Привет, ${user.first_name || 'пользователь'}!`;
} else {
    statusDiv.textContent = '⚡ Демо-режим';
}

// Обработка главной кнопки
document.getElementById('mainBtn').addEventListener('click', () => {
    // Отправляем тестовые данные боту
    tg.sendData(JSON.stringify({
        action: 'ping',
        timestamp: new Date().toISOString()
    }));
    
    tg.showAlert('Данные отправлены боту!');
});

// Показываем отладочную информацию (можно включить если нужно)
function showDebug() {
    debugDiv.style.display = 'block';
    debugDiv.innerHTML = `
        <b>Init Data:</b> ${tg.initData}<br>
        <b>User:</b> ${JSON.stringify(user, null, 2)}<br>
        <b>Platform:</b> ${tg.platform}<br>
        <b>Version:</b> ${tg.version}
    `;
}

// Раскомментируйте для отладки:
// showDebug();

// Настройка основной кнопки Telegram (синяя кнопка внизу)
tg.MainButton.setText('Получить расписание');
tg.MainButton.onClick(() => {
    tg.sendData(JSON.stringify({
        action: 'get_schedule'
    }));
});
tg.MainButton.show();

// Логируем для проверки
console.log('Web App запущен!');
console.log('User:', user);
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// УКАЖИ ЗДЕСЬ СВОЙ URL БОТА НА RENDER
const BOT_DOMAIN = "https://your-bot-name.onrender.com"; 

const scheduleContainer = document.getElementById('schedule-container');
const groupSelect = document.getElementById('group-select');
let fullData = {};

// 1. Загрузка данных при запуске
async function loadData() {
    try {
        const response = await fetch(`${BOT_DOMAIN}/api/schedule`);
        fullData = await response.json();
        
        // Заполняем выпадающий список группами
        Object.keys(fullData).forEach(group => {
            const opt = document.createElement('option');
            opt.value = group;
            opt.textContent = group;
            groupSelect.appendChild(opt);
        });

        // Если группа передана в URL (из бота), выбираем её сразу
        const urlParams = new URLSearchParams(window.location.search);
        const groupParam = urlParams.get('group');
        if (groupParam && fullData[groupParam]) {
            groupSelect.value = groupParam;
            renderSchedule(groupParam);
        }

    } catch (e) {
        scheduleContainer.innerHTML = `<p style="color:red">Ошибка загрузки: ${e.message}</p>`;
    }
}

// 2. Отрисовка расписания
function renderSchedule(groupName) {
    const days = fullData[groupName];
    scheduleContainer.innerHTML = ''; // Очистка

    const orderedDays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];

    orderedDays.forEach(day => {
        if (!days[day] || days[day].length === 0) return;

        const dayCard = document.createElement('div');
        dayCard.className = 'day-card';
        dayCard.innerHTML = `<div class="day-title">${day}</div>`;

        days[day].forEach(lesson => {
            dayCard.innerHTML += `
                <div class="lesson-item">
                    <div class="lesson-time">⏰ ${lesson.time}</div>
                    <div class="lesson-name"><b>${lesson.name}</b></div>
                    <div class="lesson-info">👤 ${lesson.teacher} | 🏛️ ${lesson.room}</div>
                </div>
            `;
        });
        scheduleContainer.appendChild(dayCard);
    });
}

// Слушатель смены группы
groupSelect.addEventListener('change', (e) => {
    if (e.target.value) renderSchedule(e.target.value);
});

loadData();
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// Твой рабочий URL (без слеша в конце)
const API_BASE_URL = "https://vsu-schedule-bot-code.onrender.com"; 

const statusDiv = document.getElementById('status');
const scheduleContainer = document.getElementById('schedule-container');
const groupSelect = document.getElementById('group-select');

// Функция для загрузки данных
async function loadSchedule() {
    try {
        statusDiv.textContent = "🔄 Загрузка расписания...";
        
        const response = await fetch(`${API_BASE_URL}/api/schedule`);
        if (!response.ok) throw new Error('Ошибка сети');
        
        const data = await response.json();
        
        // Заполняем выпадающий список группами
        const groups = Object.keys(data).sort();
        groupSelect.innerHTML = '<option value="">-- Выберите группу --</option>';
        
        groups.forEach(group => {
            const opt = document.createElement('option');
            opt.value = group;
            opt.textContent = group;
            groupSelect.appendChild(opt);
        });

        statusDiv.textContent = "✅ Расписание готово";

        // Если группа передана из бота в URL (?group=ИмяГруппы)
        const urlParams = new URLSearchParams(window.location.search);
        const autoGroup = urlParams.get('group');
        if (autoGroup && data[autoGroup]) {
            groupSelect.value = autoGroup;
            renderSchedule(data[autoGroup], autoGroup);
        }

        // Слушатель ручного выбора группы
        groupSelect.addEventListener('change', (e) => {
            const selected = e.target.value;
            if (selected) renderSchedule(data[selected], selected);
        });

    } catch (e) {
        console.error(e);
        statusDiv.textContent = "❌ Ошибка подключения к боту";
    }
}

// Функция отрисовки карточек
function renderSchedule(days, groupName) {
    scheduleContainer.innerHTML = '';
    const dayNames = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];

    dayNames.forEach(day => {
        if (days[day] && days[day].length > 0) {
            const card = document.createElement('div');
            card.className = 'day-card'; // Стили должны быть в style.css
            card.innerHTML = `<div class="day-title">${day}</div>`;

            days[day].forEach(item => {
                card.innerHTML += `
                    <div class="lesson-item">
                        <div class="lesson-time">⏰ ${item.time}</div>
                        <div class="lesson-name"><b>${item.name}</b></div>
                        <div class="lesson-info">👤 ${item.teacher} | 🏛️ ${item.room}</div>
                    </div>
                `;
            });
            scheduleContainer.appendChild(card);
        }
    });
}

// Запускаем при загрузке страницы
document.addEventListener('DOMContentLoaded', loadSchedule);
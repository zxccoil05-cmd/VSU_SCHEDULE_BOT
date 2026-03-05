const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// URL твоего бэкенда на Render (замени на свой актуальный)
const API_BASE_URL = "https://vsu-schedule-bot-code.onrender.com";

const urlParams = new URLSearchParams(window.location.search);
const faculty = urlParams.get('faculty') || 'ФМиИТ';
const startGroup = urlParams.get('group') || '';

document.getElementById('fac-name').textContent = faculty;

async function init() {
    const status = document.getElementById('status');
    const groupSelect = document.getElementById('group-select');
    const container = document.getElementById('schedule-container');

    try {
        status.textContent = "⌛ Загрузка данных " + faculty + "...";
        const response = await fetch(`${API_BASE_URL}/api/schedule?faculty=${encodeURIComponent(faculty)}`);
        
        if (!response.ok) throw new Error("Ошибка сервера");
        
        const data = await response.json();
        const groups = Object.keys(data).sort();

        // Очистка и заполнение списка групп
        groupSelect.innerHTML = '<option value="">-- Выберите группу --</option>';
        groups.forEach(g => {
            const opt = document.createElement('option');
            opt.value = g;
            opt.textContent = g;
            groupSelect.appendChild(opt);
        });

        status.textContent = "✅ Обновлено";

        // Если группа передана из бота - сразу показываем
        if (startGroup && data[startGroup]) {
            groupSelect.value = startGroup;
            render(data[startGroup]);
        }

        groupSelect.addEventListener('change', (e) => {
            if (data[e.target.value]) {
                render(data[e.target.value]);
            }
        });

    } catch (err) {
        status.textContent = "❌ Ошибка соединения";
        console.error(err);
    }
}

function render(days) {
    const container = document.getElementById('schedule-container');
    container.innerHTML = '';
    
    const dayNames = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"];
    
    dayNames.forEach(day => {
        if (days[day] && days[day].length > 0) {
            const card = document.createElement('div');
            card.className = 'day-card';
            card.innerHTML = `<div class="day-title">${day}</div>`;
            
            days[day].forEach(lesson => {
                card.innerHTML += `
                    <div class="lesson-item">
                        <div class="lesson-time">${lesson.time}</div>
                        <div class="lesson-name">${lesson.name}</div>
                        <div class="lesson-info">🏛 Каб: ${lesson.room} | 👤 ${lesson.teacher}</div>
                    </div>
                `;
            });
            container.appendChild(card);
        }
    });
}

document.addEventListener('DOMContentLoaded', init);
const tg = window.Telegram.WebApp;
tg.expand(); // Разворачиваем на весь экран

// 1. Получаем настройки из URL (которые передал бот)
const urlParams = new URLSearchParams(window.location.search);
const faculty = urlParams.get('faculty') || 'ФМиИТ';
const group = urlParams.get('group');

document.getElementById('group-name').innerText = group || "Группа не выбрана";
document.getElementById('faculty-name').innerText = faculty;

// 2. Функция загрузки данных
async function loadSchedule() {
    try {
        // Укажи здесь URL своего сервера, где запущен бот
        const API_URL = `https://vsu-schedule-bot-code.onrender.com/api/schedule?faculty=${encodeURIComponent(faculty)}`;
        
        const response = await fetch(API_URL);
        const allData = await response.json();
        
        const groupSchedule = allData[group];
        renderSchedule(groupSchedule);
    } catch (error) {
        console.error("Ошибка загрузки:", error);
        document.getElementById('schedule-container').innerHTML = "<p>Ошибка загрузки расписания...</p>";
    }
}

// 3. Функция отрисовки
function renderSchedule(schedule) {
    const container = document.getElementById('schedule-container');
    container.innerHTML = ''; // Очищаем

    if (!schedule) {
        container.innerHTML = "<p>Расписание для этой группы не найдено.</p>";
        return;
    }

    const days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"];

    days.forEach(day => {
        const lessons = schedule[day];
        if (!lessons || lessons.length === 0) return;

        // Создаем блок дня
        const daySection = document.createElement('div');
        daySection.className = 'day-section';
        daySection.innerHTML = `<h2>${day}</h2>`;

        const lessonsList = document.createElement('div');
        lessonsList.className = 'lessons-list';

        lessons.forEach(lesson => {
            // ТЕПЕРЬ МЫ ИСПОЛЬЗУЕМ lesson.time и lesson.name
            const lessonItem = document.createElement('div');
            lessonItem.className = 'lesson-item';
            lessonItem.innerHTML = `
                <div class="time">${lesson.time || '--:--'}</div>
                <div class="details">${lesson.name}</div>
            `;
            lessonsList.appendChild(lessonItem);
        });

        daySection.appendChild(lessonsList);
        container.appendChild(daySection);
    });
}

loadSchedule();
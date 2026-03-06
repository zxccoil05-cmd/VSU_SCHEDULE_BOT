// В начале script.js
const API_BASE = "https://vsu-schedule-bot-code.onrender.com/api";

const facSelect = document.getElementById('fac-select');
const groupSelect = document.getElementById('group-select');
const groupArea = document.getElementById('group-area');
const scheduleRender = document.getElementById('schedule-render');
// Получаем элементы навигации для управления активным состоянием
const navItems = document.querySelectorAll('.nav-item');

async function init() {
    await loadFaculties();
    
    const savedFac = localStorage.getItem('vsu_fac');
    const savedGroup = localStorage.getItem('vsu_group');

    if (savedFac && savedGroup) {
        // Если всё выбрано — загружаем и прыгаем на экран расписания
        facSelect.value = savedFac;
        await loadGroups(savedFac);
        groupSelect.value = savedGroup;
        loadSchedule(savedGroup);
        
        // Переключаем визуально на экран расписания (индекс 1 в навигации)
        switchScreen('schedule', navItems[1]);
    } else {
        // Если данных нет — остаемся на экране настроек (индекс 0)
        switchScreen('settings', navItems[0]);
    }
}

function switchScreen(screenId, el) {
    // Убираем активный класс у всех кнопок навигации
    navItems.forEach(i => i.classList.remove('active'));
    // Добавляем активный класс нажатой (или выбранной программно) кнопке
    if (el) el.classList.add('active');
    
    // Переключаем видимость секций
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById('screen-' + screenId).classList.add('active');
}

async function loadFaculties() {
    try {
        const r = await fetch(`${API_BASE}/faculties`);
        const data = await r.json();
        facSelect.innerHTML = '<option value="" disabled selected>Выберите факультет...</option>';
        data.faculties.forEach(f => {
            facSelect.innerHTML += `<option value="${f}">${f}</option>`;
        });
    } catch (e) { facSelect.innerHTML = '<option>Ошибка API</option>'; }
}

facSelect.onchange = async (e) => {
    const fac = e.target.value;
    localStorage.setItem('vsu_fac', fac);
    localStorage.removeItem('vsu_group'); // Сбрасываем группу при смене фака
    await loadGroups(fac);
    scheduleRender.innerHTML = "";
};

async function loadGroups(fac) {
    groupArea.style.display = 'block';
    groupSelect.innerHTML = '<option disabled selected>Загрузка групп...</option>';
    try {
        const r = await fetch(`${API_BASE}/faculties/${fac}/groups`);
        const data = await r.json();
        groupSelect.innerHTML = '<option value="" disabled selected>Выберите группу...</option>';
        data.groups.forEach(g => {
            groupSelect.innerHTML += `<option value="${g}">${g}</option>`;
        });
    } catch (e) { console.error(e); }
}

groupSelect.onchange = (e) => {
    const group = e.target.value;
    localStorage.setItem('vsu_group', group);
    loadSchedule(group);
    // После выбора группы автоматически перекидываем на расписание
    switchScreen('schedule', navItems[1]);
};

async function loadSchedule(group) {
    scheduleRender.innerHTML = '<div class="glass-card">🔄 Загрузка...</div>';
    try {
        const r = await fetch(`${API_BASE}/schedule/${encodeURIComponent(group)}`);
        const data = await r.json();
        
        scheduleRender.innerHTML = `<h2 style="text-align:center; color:#2980b9;">${group}</h2>`;
        const days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
        
        days.forEach(day => {
            const lessons = data.schedule[day] || [];
            if (lessons.length > 0) {
                let html = `<div class="day-card"><div class="day-title">📅 ${day.toUpperCase()}</div>`;
                lessons.forEach(l => {
                    html += `
                        <div class="lesson-row">
                            <div class="time-badge">${l.time.replace('(','').replace(')','')}</div>
                            <div class="lesson-data">
                                <b>${l.name}</b>
                                <span>👤 ${l.teacher} | 📍 ${l.room}</span>
                            </div>
                        </div>`;
                });
                html += `</div>`;
                scheduleRender.innerHTML += html;
            }
        });
        
        if (scheduleRender.innerHTML.includes('Загрузка...')) {
            scheduleRender.innerHTML = '<div class="glass-card">📭 На этой неделе занятий не найдено</div>';
        }

    } catch (e) { scheduleRender.innerHTML = '<div class="glass-card">❌ Ошибка сервера</div>'; }
}

// Запуск инициализации
init();
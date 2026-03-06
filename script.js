// В начале script.js
const API_BASE = "https://vsu-schedule-bot-code.onrender.com/api";

// Проверка: если мы тестим локально, можно оставить условие
// const API_BASE = window.location.hostname === 'localhost' 
//    ? "http://localhost:8000/api" 
//    : "https://vsu-schedule-bot-code.onrender.com/api";

const facSelect = document.getElementById('fac-select');
const groupSelect = document.getElementById('group-select');
const groupArea = document.getElementById('group-area');
const scheduleRender = document.getElementById('schedule-render');

async function init() {
    await loadFaculties();
    
    const savedFac = localStorage.getItem('vsu_fac');
    const savedGroup = localStorage.getItem('vsu_group');

    if (savedFac) {
        facSelect.value = savedFac;
        await loadGroups(savedFac);
        if (savedGroup) {
            groupSelect.value = savedGroup;
            loadSchedule(savedGroup);
        }
    }
}

function switchScreen(screenId, el) {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    el.classList.add('active');
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
    localStorage.removeItem('vsu_group');
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
    switchScreen('schedule', document.querySelectorAll('.nav-item')[1]);
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
    } catch (e) { scheduleRender.innerHTML = '<div class="glass-card">❌ Ошибка сервера</div>'; }
}

init();
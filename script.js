const API_BASE = "https://vsu-schedule-bot-code.onrender.com/api";
let currentDayIndex = 0;
let touchStartX = 0;

// UI ФУНКЦИИ
function toggleReportBtn(event) {
    event.stopPropagation();
    document.getElementById('report-btn').classList.toggle('show');
}

function handleGlobalClick(event) {
    createRipple(event);
    const btn = document.getElementById('report-btn');
    // Скрываем кнопку ошибки, если кликнули мимо report-wrapper
    if (btn.classList.contains('show') && !event.target.closest('.report-wrapper')) {
        btn.classList.remove('show');
    }
}

function sendReport() {
    // ЗАМЕНИ НА СВОЙ TG (например, https://t.me/durov)
    const myContact = "https://t.me/@wch8h"; 
    
    document.getElementById('report-btn').classList.remove('show');
    window.open(myContact, '_blank');
}

function createRipple(event) {
    const ripple = document.createElement("span");
    ripple.classList.add("ripple");
    const size = 50; 
    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${event.clientX - size / 2}px`;
    ripple.style.top = `${event.clientY - size / 2}px`;
    document.body.appendChild(ripple);
    setTimeout(() => ripple.remove(), 500);
}

// РАБОТА С ДАННЫМИ
const screensContainer = document.getElementById('screens-container');
const scheduleTrack = document.getElementById('schedule-track');
const navItems = document.querySelectorAll('.nav-item');

async function init() {
    await loadFaculties();
    const savedFac = localStorage.getItem('vsu_fac');
    const savedGroup = localStorage.getItem('vsu_group');

    if (savedFac && savedGroup) {
        document.getElementById('fac-select').value = savedFac;
        await loadGroups(savedFac);
        document.getElementById('group-select').value = savedGroup;
        loadSchedule(savedGroup);
    } else {
        switchScreen(0); // Показываем настройки, если данных нет
    }
}

function switchScreen(index) {
    navItems.forEach(i => i.classList.remove('active'));
    navItems[index].classList.add('active');
    screensContainer.style.transform = `translateX(-${index * 50}%)`;
}

function goToDay(index) {
    if (index < 0 || index > 5) return;
    currentDayIndex = index;
    scheduleTrack.style.transform = `translateX(-${index * 16.666}%)`;
    // Обновляем табы (используем querySelectorAll внутри days-tabs)
    document.getElementById('days-tabs').querySelectorAll('.day-tab').forEach((t, i) => t.classList.toggle('active', i === index));
}

async function loadSchedule(group) {
    if (!group) return;
    
    // Показываем загрузку во всех колонках
    scheduleTrack.innerHTML = '<div class="day-column"><div class="glass-card">🔄 Загружаем расписание...</div></div>';
    
    try {
        const r = await fetch(`${API_BASE}/schedule/${encodeURIComponent(group)}`);
        if (!r.ok) throw new Error('Ошибка сети');
        const data = await r.json();
        
        const days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
        let fullHtml = "";

        days.forEach(dayName => {
            const lessons = data.schedule[dayName] || [];
            let html = `<div class="day-column"><div class="day-card"><div class="day-title">📅 ${dayName.toUpperCase()}</div>`;
            
            if (lessons.length === 0) {
                html += `<div style="text-align:center; padding:30px; color:#64748b; font-weight:600;">Пар нет 🎉</div>`;
            } else {
                lessons.forEach(l => {
                    html += `
                        <div class="lesson-row">
                            <div class="time-badge">${l.time.replace('(','').replace(')','')}</div>
                            <div class="lesson-data">
                                <b style="font-size:14px; color:#1e3a8a;">${l.name}</b><br>
                                <span style="font-size:11px; color:#64748b; font-weight:600;">📍 ${l.room} | 👤 ${l.teacher}</span>
                            </div>
                        </div>`;
                });
            }
            html += `</div></div>`;
            fullHtml += html;
        });

        scheduleTrack.innerHTML = fullHtml;
        
        // Переключаемся на сегодня (если вс, то пн)
        let d = new Date().getDay();
        goToDay((d === 0) ? 0 : d - 1);
        switchScreen(1); // Прыгаем на экран расписания

    } catch (e) {
        console.error(e);
        scheduleTrack.innerHTML = '<div class="day-column"><div class="glass-card">❌ Сервер не отвечает. Попробуй позже.</div></div>';
    }
}

// API: Факультеты и Группы
async function loadFaculties() {
    try {
        const r = await fetch(`${API_BASE}/faculties`);
        const data = await r.json();
        const sel = document.getElementById('fac-select');
        sel.innerHTML = '<option disabled selected>Выберите факультет...</option>';
        data.faculties.forEach(f => sel.innerHTML += `<option value="${f}">${f}</option>`);
    } catch (e) {
        document.getElementById('fac-select').innerHTML = '<option>Ошибка загрузки</option>';
    }
}

async function loadGroups(fac) {
    document.getElementById('group-area').style.display = 'block';
    const sel = document.getElementById('group-select');
    sel.innerHTML = '<option>Загрузка групп...</option>';
    try {
        const r = await fetch(`${API_BASE}/faculties/${fac}/groups`);
        const data = await r.json();
        sel.innerHTML = '<option disabled selected>Выберите группу...</option>';
        data.groups.forEach(g => sel.innerHTML += `<option value="${g}">${g}</option>`);
    } catch (e) {
        sel.innerHTML = '<option>Ошибка</option>';
    }
}

// ОБРАБОТЧИКИ
document.getElementById('fac-select').onchange = (e) => {
    localStorage.setItem('vsu_fac', e.target.value);
    loadGroups(e.target.value);
};

document.getElementById('group-select').onchange = (e) => {
    localStorage.setItem('vsu_group', e.target.value);
    loadSchedule(e.target.value);
};

// СВАЙПЫ
const swiperArea = document.getElementById('schedule-swiper');
swiperArea.addEventListener('touchstart', e => touchStartX = e.touches[0].clientX, {passive: true});
swiperArea.addEventListener('touchend', e => {
    const diff = touchStartX - e.changedTouches[0].clientX;
    if (Math.abs(diff) > 60) {
        if (diff > 0) goToDay(currentDayIndex + 1);
        else goToDay(currentDayIndex - 1);
    }
});

init();
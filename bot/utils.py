def format_schedule_for_group(all_schedule: dict, subgroup_name: str) -> str:
    """Форматирует расписание для конкретной подгруппы"""
    if not all_schedule or subgroup_name not in all_schedule:
        return f"😕 Расписание для подгруппы <b>{subgroup_name}</b> не найдено или файл пуст."
    
    sg_data = all_schedule[subgroup_name]
    lines = [f"<b>📚 Расписание: {subgroup_name}</b>\n"]
    
    # Сортируем дни, чтобы они шли по порядку
    ordered_days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    
    for day in ordered_days:
        if day not in sg_data or not sg_data[day]:
            continue
            
        lines.append(f"🔵 <b>{day.upper()}</b>")
        for l in sg_data[day]:
            lines.append(f"  ⏰ <code>{l['time']}</code>")
            lines.append(f"  📚 <b>{l['name']}</b>")
            lines.append(f"  👤 {l['teacher']} | 🏛️ {l['room']}")
            lines.append("") # Разделитель между парами
    
    if len(lines) == 1:
        return f"📭 У подгруппы <b>{subgroup_name}</b> на эту неделю пар не найдено."
    
    return "\n".join(lines)
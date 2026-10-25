import logging
import re
from collections.abc import Iterator
from datetime import datetime, timezone

if __package__:
    from .schedule_source import (
        FACULTY_NAMES,
        GroupSchedule,
        Schedule,
        VsuScheduleSource,
    )
else:
    from schedule_source import (
        FACULTY_NAMES,
        GroupSchedule,
        Schedule,
        VsuScheduleSource,
    )

logger = logging.getLogger(__name__)


class ScheduleFactory:
    def __init__(self) -> None:
        self._faculty_data: dict[str, dict[str, GroupSchedule]] = {
            faculty: {} for faculty in FACULTY_NAMES
        }
        self._faculty_ids: dict[str, str] = {}
        self._group_catalog: dict[str, dict[str, str]] = {
            faculty: {} for faculty in FACULTY_NAMES
        }
        self.last_updated_at: str | None = None

    def update_all(self) -> bool:
        """Refresh all faculties, retaining the previous data for failed ones."""
        source = VsuScheduleSource()
        try:
            faculty_ids = source.get_faculty_ids()
            self._faculty_ids = faculty_ids
            successful_faculties = 0
            for faculty in FACULTY_NAMES:
                faculty_id = faculty_ids.get(faculty)
                if faculty_id is None:
                    continue

                try:
                    groups = source.get_faculty_groups(faculty_id)
                    data = source.get_faculty_schedule(faculty_id, groups)
                except Exception:
                    logger.exception("Не удалось обновить расписание факультета %s", faculty)
                    continue

                self._faculty_data[faculty] = data
                self._group_catalog[faculty] = {
                    group.name: group.id for group in groups
                }
                successful_faculties += 1
                logger.info(
                    "Факультет %s обновлен: %s групп",
                    faculty,
                    len(data),
                )
        except Exception:
            logger.exception("Не удалось загрузить список факультетов с сайта ВГУ")
            return False
        finally:
            source.close()

        total_groups = sum(len(groups) for groups in self._faculty_data.values())
        logger.info(
            "Обновление расписаний: факультетов %s/%s, групп в кэше %s",
            successful_faculties,
            len(FACULTY_NAMES),
            total_groups,
        )
        if successful_faculties:
            self.last_updated_at = datetime.now(timezone.utc).isoformat()
        return successful_faculties == len(FACULTY_NAMES)

    def get_faculties(self) -> list[str]:
        return list(FACULTY_NAMES)

    def get_groups(self, faculty: str) -> list[str] | None:
        groups = self._faculty_data.get(faculty)
        if groups is None:
            return None
        if self._group_catalog[faculty]:
            return sorted(self._group_catalog[faculty])

        with VsuScheduleSource() as source:
            faculty_id = self._get_faculty_id(source, faculty)
            options = source.get_faculty_groups(faculty_id)
        self._group_catalog[faculty] = {group.name: group.id for group in options}
        return sorted(self._group_catalog[faculty])

    def get_subgroups(self, faculty: str, group: str) -> list[dict[str, str]] | None:
        groups = self.get_groups(faculty)
        if groups is None or group not in self._group_catalog[faculty]:
            return None
        group_data = self._get_group_data(faculty, group)
        if group_data is None:
            return None
        return [
            {"id": subgroup.id, "name": subgroup.name}
            for subgroup in group_data.subgroups
        ]

    def _get_faculty_id(self, source: VsuScheduleSource, faculty: str) -> str:
        faculty_id = self._faculty_ids.get(faculty)
        if faculty_id is None:
            self._faculty_ids.update(source.get_faculty_ids())
            faculty_id = self._faculty_ids.get(faculty)
        if faculty_id is None:
            raise ValueError(f"Факультет {faculty} не найден на сайте расписаний")
        return faculty_id

    def _get_group_data(self, faculty: str, group: str) -> GroupSchedule | None:
        group_data = self._faculty_data[faculty].get(group)
        if group_data is not None and group_data.subgroups:
            return group_data

        with VsuScheduleSource() as source:
            faculty_id = self._get_faculty_id(source, faculty)
            group_id = self._group_catalog[faculty][group]
            subgroups = source.get_group_subgroups(faculty_id, group_id)

        group_data = GroupSchedule(
            id=group_id,
            name=group,
            subgroups=subgroups,
        )
        self._faculty_data[faculty] = {
            **self._faculty_data[faculty],
            group: group_data,
        }
        return group_data

    @staticmethod
    def _merge_schedules(schedules: list[Schedule]) -> Schedule:
        merged: Schedule = {}
        for schedule in schedules:
            for day, lessons in schedule.items():
                day_lessons = merged.setdefault(day, [])
                for lesson in lessons:
                    if lesson not in day_lessons:
                        day_lessons.append(lesson)
        return merged

    def get_schedule(
        self,
        group: str,
        faculty: str | None = None,
        subgroup_id: str | None = None,
    ) -> Schedule | None:
        faculties = [faculty] if faculty is not None else self._faculty_data
        for faculty_name in faculties:
            groups = self.get_groups(faculty_name)
            if groups is None or group not in self._group_catalog[faculty_name]:
                continue

            group_data = self._get_group_data(faculty_name, group)
            if group_data is None:
                continue
            if subgroup_id is not None:
                if subgroup_id not in {option.id for option in group_data.subgroups}:
                    return None
                if subgroup_id not in group_data.schedules:
                    with VsuScheduleSource() as source:
                        faculty_id = self._get_faculty_id(source, faculty_name)
                        schedule = source.get_group_schedule(
                            faculty_id,
                            group_data.id,
                            subgroup_id,
                        )
                    group_data.schedules[subgroup_id] = schedule
                return group_data.schedules[subgroup_id]

            missing_subgroups = [
                subgroup
                for subgroup in group_data.subgroups
                if subgroup.id not in group_data.schedules
            ]
            if missing_subgroups:
                with VsuScheduleSource() as source:
                    faculty_id = self._get_faculty_id(source, faculty_name)
                    for subgroup in missing_subgroups:
                        group_data.schedules[subgroup.id] = source.get_group_schedule(
                            faculty_id,
                            group_data.id,
                            subgroup.id,
                        )
            return self._merge_schedules(list(group_data.schedules.values()))
        return None

    def iter_schedules(self) -> Iterator[tuple[str, Schedule]]:
        for groups in self._faculty_data.values():
            for group_name, group_data in groups.items():
                yield group_name, self._merge_schedules(
                    list(group_data.schedules.values())
                )

    @staticmethod
    def _room_location(room: str) -> tuple[str, str, str]:
        value = room.strip()
        value = re.sub(r"^ауд(?:итория)?\.?\s*", "", value, flags=re.IGNORECASE)
        folded = value.casefold()

        if "спортзал" in folded or "спортивный зал" in folded:
            if "мал" in folded:
                return "gym:small", "Малый спортзал", value
            if "больш" in folded:
                return "gym:large", "Большой спортзал", value

        match = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", value)
        if match:
            room_name, building = match.groups()
            return f"building:{building.casefold()}", building, room_name.strip()

        match = re.match(r"^(.*?)\s+(главный корпус)\s*$", value, re.IGNORECASE)
        if match:
            room_name, building = match.groups()
            return f"building:{building.casefold()}", building.title(), room_name.strip()

        return "building:none", "Без корпуса", value

    def get_room_locations(self) -> list[dict[str, str]]:
        locations: dict[str, str] = {
            "gym:small": "Малый спортзал",
            "gym:large": "Большой спортзал",
        }
        for _, schedule in self.iter_schedules():
            for lessons in schedule.values():
                for lesson in lessons:
                    room = lesson.get("room", "").strip()
                    if not room or room == "---":
                        continue
                    location_id, label, _ = self._room_location(room)
                    locations[location_id] = label
        return [
            {"id": location_id, "name": label}
            for location_id, label in sorted(
                locations.items(), key=lambda item: item[1].casefold()
            )
        ]

    def search_room(self, room_query: str, location_id: str) -> Schedule:
        query = room_query.strip().casefold()
        if not location_id.startswith("gym:") and not query:
            raise ValueError("Укажите номер аудитории.")

        result: Schedule = {}
        for group, schedule in self.iter_schedules():
            for day, lessons in schedule.items():
                for lesson in lessons:
                    room = lesson.get("room", "").strip()
                    if not room or room == "---":
                        continue
                    current_location, _, room_name = self._room_location(room)
                    if current_location != location_id:
                        continue
                    if not location_id.startswith("gym:") and query not in room_name.casefold():
                        continue

                    match = dict(lesson)
                    match["group"] = group
                    day_lessons = result.setdefault(day, [])
                    duplicate = next(
                        (
                            existing
                            for existing in day_lessons
                            if all(
                                existing.get(key) == match.get(key)
                                for key in ("time", "name", "teacher", "room")
                            )
                        ),
                        None,
                    )
                    if duplicate:
                        if group not in duplicate["group"].split(", "):
                            duplicate["group"] += f", {group}"
                    else:
                        day_lessons.append(match)

        for lessons in result.values():
            lessons.sort(key=lambda lesson: lesson.get("time", ""))
        return result

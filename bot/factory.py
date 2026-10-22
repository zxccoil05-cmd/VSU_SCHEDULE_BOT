import logging
from collections.abc import Iterator

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

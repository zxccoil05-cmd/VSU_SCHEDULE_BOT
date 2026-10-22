import logging
import time
from dataclasses import dataclass, field
from types import TracebackType
from typing import TypeAlias
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SCHEDULE_URL = "https://vsu.by/studentam/elektronnoe-raspisanie.html"
FACULTY_NAMES = {
    "ФМиИТ": "Факультет математики и информационных технологий",
    "ХБиГН": "Факультет химико-биологических и географических наук",
    "ФФКиС": "Факультет физической культуры и спорта",
    "ЮФ": "Юридический факультет",
    "ПФ": "Педагогический факультет",
    "ФСПиП": "Факультет социальной педагогики и психологии",
    "ГФ": "Факультет гуманитарного знания и коммуникаций",
    "ХГФ": "Художественно-графический факультет",
}
DAY_NAMES = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
)
Schedule: TypeAlias = dict[str, list[dict[str, str]]]


@dataclass(frozen=True)
class ScheduleOption:
    id: str
    name: str


@dataclass
class GroupSchedule:
    id: str
    name: str
    subgroups: list[ScheduleOption] = field(default_factory=list)
    schedules: dict[str, Schedule] = field(default_factory=dict)


def _get_form_options(html_text: str, select_name: str) -> list[ScheduleOption]:
    soup = BeautifulSoup(html_text, "html.parser")
    select = soup.find("select", {"name": select_name})
    if select is None:
        return []

    options = []
    for option in select.find_all("option"):
        value = option.get("value", "").strip()
        name = option.get_text(" ", strip=True)
        if value and name:
            options.append(ScheduleOption(id=value, name=name))
    return options


def _parse_schedule(html_text: str) -> Schedule:
    soup = BeautifulSoup(html_text, "html.parser")
    module = soup.find(id="schedule-module")
    if module is None:
        raise ValueError("В ответе сайта не найден блок расписания")

    schedule: Schedule = {day: [] for day in DAY_NAMES}
    for heading in module.find_all("h3", recursive=False):
        day = heading.get_text(" ", strip=True)
        if day not in schedule:
            continue

        table = heading.find_next_sibling("table")
        if table is None:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) != 4 or cells[0].name != "td":
                continue

            time_value, name, teacher, room = (
                cell.get_text(" ", strip=True) for cell in cells
            )
            if name:
                schedule[day].append(
                    {
                        "time": time_value,
                        "name": name,
                        "teacher": teacher or "---",
                        "room": room or "---",
                    }
                )
    return schedule


class VsuScheduleSource:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": SCHEDULE_URL,
            }
        )

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "VsuScheduleSource":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _request_html(self, payload: dict[str, str] | None = None) -> str:
        if payload is None:
            response = self.session.get(SCHEDULE_URL, timeout=30)
        else:
            response = self.session.post(SCHEDULE_URL, data=payload, timeout=30)
        response.encoding = "utf-8"
        if not response.ok:
            logger.error(
                "Источник расписания вернул HTTP %s для %s; тело ответа: %r",
                response.status_code,
                response.url,
                response.text[:1000],
            )
            response.raise_for_status()
        return response.text

    def get_faculty_ids(self) -> dict[str, str]:
        html_text = self._request_html()
        source_names = {
            option.name.casefold(): option.id
            for option in _get_form_options(html_text, "faculty_id")
        }
        faculty_ids = {}
        for app_name, source_name in FACULTY_NAMES.items():
            faculty_id = source_names.get(source_name.casefold())
            if faculty_id is None:
                logger.error("На сайте ВГУ не найдена форма факультета %s", source_name)
                continue
            faculty_ids[app_name] = faculty_id
        return faculty_ids

    def get_faculty_groups(self, faculty_id: str) -> list[ScheduleOption]:
        html_text = self._request_html({"faculty_id": faculty_id})
        groups = _get_form_options(html_text, "group_id")
        if not groups:
            raise ValueError(f"Для факультета с id={faculty_id} не найдены группы")
        return groups

    def get_group_subgroups(
        self, faculty_id: str, group_id: str
    ) -> list[ScheduleOption]:
        html_text = self._request_html(
            {"faculty_id": faculty_id, "group_id": group_id}
        )
        subgroups = _get_form_options(html_text, "subgroup_id")
        return subgroups or [ScheduleOption(id="", name="Все подгруппы")]

    def get_group_schedule(
        self, faculty_id: str, group_id: str, subgroup_id: str
    ) -> Schedule:
        schedule_html = self._request_html(
            {
                "faculty_id": faculty_id,
                "group_id": group_id,
                "subgroup_id": subgroup_id,
                "date_id": "",
                "view_type": "weekly",
            }
        )
        return _parse_schedule(schedule_html)

    def get_faculty_schedule(
        self,
        faculty_id: str,
        groups: list[ScheduleOption] | None = None,
    ) -> dict[str, GroupSchedule]:
        groups = groups or self.get_faculty_groups(faculty_id)
        result: dict[str, GroupSchedule] = {}
        for group in groups:
            time.sleep(0.1)
            subgroups = self.get_group_subgroups(faculty_id, group.id)

            group_schedule = GroupSchedule(
                id=group.id,
                name=group.name,
                subgroups=subgroups,
            )
            for subgroup in subgroups:
                time.sleep(0.1)
                group_schedule.schedules[subgroup.id] = self.get_group_schedule(
                    faculty_id,
                    group.id,
                    subgroup.id,
                )
            result[group.name] = group_schedule

        return result

import unittest
from unittest.mock import MagicMock, Mock, patch

from bot.factory import ScheduleFactory
from bot.schedule_source import (
    FACULTY_NAMES,
    GroupSchedule,
    ScheduleOption,
    VsuScheduleSource,
    _get_form_options,
    _parse_schedule,
)


class ScheduleSourceTests(unittest.TestCase):
    def test_reads_select_options_and_ignores_placeholder(self):
        html = """
        <select name="group_id">
          <option value="">Выберите группу</option>
          <option value="123">26ИСиТ1д</option>
        </select>
        """

        self.assertEqual(
            _get_form_options(html, "group_id"),
            [ScheduleOption(id="123", name="26ИСиТ1д")],
        )

    def test_parses_weekly_day_tables_into_existing_schedule_shape(self):
        html = """
        <div id="schedule-module">
          <h3>Понедельник</h3>
          <table>
            <tr><th>Время</th><th>Предмет</th><th>Преподаватель</th><th>Аудитория</th></tr>
            <tr>
              <td>(08:00-09:25)</td>
              <td>Математика (Лек)</td>
              <td>Иванов И. И.</td>
              <td>ауд. 10</td>
            </tr>
            <tr><td>(09:35-11:00)</td><td></td><td></td><td></td></tr>
          </table>
          <h3>Вторник</h3>
          <table><tr><th>Время</th><th>Предмет</th><th>Преподаватель</th><th>Аудитория</th></tr></table>
        </div>
        """

        schedule = _parse_schedule(html)

        self.assertEqual(
            schedule["Понедельник"],
            [
                {
                    "time": "(08:00-09:25)",
                    "name": "Математика (Лек)",
                    "teacher": "Иванов И. И.",
                    "room": "ауд. 10",
                }
            ],
        )
        self.assertEqual(schedule["Вторник"], [])
        self.assertEqual(schedule["Среда"], [])

    def test_rejects_response_without_schedule_module(self):
        with self.assertRaisesRegex(ValueError, "не найден блок расписания"):
            _parse_schedule("<html><body>Ошибка</body></html>")

    def test_requests_group_subgroups_and_weekly_schedule(self):
        source = VsuScheduleSource()
        source._request_html = Mock(
            side_effect=[
                '<select name="group_id"><option value="20">26ИСиТ1д</option></select>',
                '<select name="subgroup_id"><option value="30">26ИСиТ1д_1</option></select>',
                """
                <div id="schedule-module">
                  <h3>Понедельник</h3>
                  <table>
                    <tr><th>Время</th><th>Предмет</th><th>Преподаватель</th><th>Аудитория</th></tr>
                    <tr><td>08:00</td><td>Математика</td><td>Иванов</td><td>10</td></tr>
                  </table>
                </div>
                """,
            ]
        )

        with patch("bot.schedule_source.time.sleep"):
            result = source.get_faculty_schedule("10")
        source.close()

        self.assertEqual(
            [call.args[0] for call in source._request_html.call_args_list],
            [
                {"faculty_id": "10"},
                {"faculty_id": "10", "group_id": "20"},
                {
                    "faculty_id": "10",
                    "group_id": "20",
                    "subgroup_id": "30",
                    "date_id": "",
                    "view_type": "weekly",
                },
            ],
        )
        self.assertEqual(
            result["26ИСиТ1д"].schedules["30"]["Понедельник"][0]["name"],
            "Математика",
        )

    def test_factory_merges_subgroups_and_returns_selected_subgroup(self):
        factory = ScheduleFactory()
        factory._faculty_data["ПФ"] = {
            "26ДО1д": GroupSchedule(
                id="2618",
                name="26ДО1д",
                subgroups=[
                    ScheduleOption(id="5272", name="26ДО1д_1"),
                    ScheduleOption(id="5273", name="26ДО1д_2"),
                ],
                schedules={
                    "5272": {
                        "Понедельник": [
                            {"time": "08:00", "name": "Математика", "teacher": "Иванов", "room": "10"}
                        ]
                    },
                    "5273": {
                        "Понедельник": [
                            {"time": "08:00", "name": "Математика", "teacher": "Иванов", "room": "10"},
                            {"time": "09:00", "name": "История", "teacher": "Петров", "room": "20"},
                        ]
                    },
                },
            )
        }
        factory._group_catalog["ПФ"] = {"26ДО1д": "2618"}

        self.assertEqual(factory.get_groups("ПФ"), ["26ДО1д"])
        self.assertEqual(
            factory.get_subgroups("ПФ", "26ДО1д"),
            [
                {"id": "5272", "name": "26ДО1д_1"},
                {"id": "5273", "name": "26ДО1д_2"},
            ],
        )
        self.assertEqual(
            len(factory.get_schedule("26ДО1д", "ПФ")["Понедельник"]),
            2,
        )
        self.assertEqual(
            len(factory.get_schedule("26ДО1д", "ПФ", "5272")["Понедельник"]),
            1,
        )

    def test_factory_fetches_a_group_on_demand_before_background_refresh(self):
        factory = ScheduleFactory()
        faculty = "ПФ"
        group = "26ДО1д"
        factory._faculty_ids[faculty] = "10"
        source = MagicMock()
        source.__enter__.return_value = source
        source.get_faculty_groups.return_value = [
            ScheduleOption(id="20", name=group)
        ]
        source.get_group_subgroups.return_value = [
            ScheduleOption(id="30", name="26ДО1д_1")
        ]
        source.get_group_schedule.return_value = {
            "Понедельник": [
                {"time": "08:00", "name": "Математика", "teacher": "Иванов", "room": "10"}
            ]
        }

        with patch("bot.factory.VsuScheduleSource", return_value=source):
            subgroups = factory.get_subgroups(faculty, group)
            schedule = factory.get_schedule(group, faculty, "30")

        self.assertEqual(subgroups, [{"id": "30", "name": "26ДО1д_1"}])
        self.assertEqual(schedule["Понедельник"][0]["name"], "Математика")
        source.get_faculty_groups.assert_called_once_with("10")
        source.get_group_subgroups.assert_called_once_with("10", "20")
        source.get_group_schedule.assert_called_once_with("10", "20", "30")

    def test_failed_refresh_keeps_existing_schedule_cache(self):
        factory = ScheduleFactory()
        old_group = GroupSchedule(id="1", name="старое", subgroups=[])
        factory._faculty_data["ПФ"] = {"старое": old_group}
        factory._group_catalog["ПФ"] = {"старое": "1"}
        faculty_ids = {
            faculty: str(index)
            for index, faculty in enumerate(FACULTY_NAMES, start=1)
        }
        source = Mock()
        source.get_faculty_ids.return_value = faculty_ids
        source.get_faculty_groups.return_value = [
            ScheduleOption(id="2", name="26ИСиТ1д")
        ]
        source.get_faculty_schedule.side_effect = RuntimeError("upstream unavailable")

        with (
            patch("bot.factory.VsuScheduleSource", return_value=source),
            self.assertLogs("bot.factory", level="ERROR"),
        ):
            self.assertFalse(factory.update_all())

        self.assertEqual(factory.get_groups("ПФ"), ["старое"])
        source.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

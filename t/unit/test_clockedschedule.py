"""Tests for the Connect customisation of the clocked schedule.

Naive ``clocked_time`` values are interpreted in the Celery app timezone
(or Django's current timezone) instead of UTC.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.test import TestCase, override_settings
from django.utils import timezone

from django_celery_beat.clockedschedule import _get_clocked_time_tz, clocked
from django_celery_beat.models import ClockedSchedule

NEW_YORK = ZoneInfo('America/New_York')


def _app(tz):
    return mock.Mock(conf=mock.Mock(timezone=tz))


class test_get_clocked_time_tz(TestCase):

    def test_prefers_app_timezone(self):
        assert _get_clocked_time_tz(_app('Asia/Tokyo')) == 'Asia/Tokyo'

    @override_settings(USE_TZ=False, TIME_ZONE='America/New_York')
    def test_falls_back_to_django_timezone_without_app(self):
        assert str(_get_clocked_time_tz(None)) == 'America/New_York'

    @override_settings(USE_TZ=False, TIME_ZONE='America/New_York')
    def test_falls_back_to_django_timezone_when_app_has_no_timezone(self):
        assert str(_get_clocked_time_tz(_app(None))) == 'America/New_York'

    def test_returns_none_when_django_timezone_unavailable(self):
        with mock.patch(
            'django.utils.timezone.get_current_timezone',
            side_effect=RuntimeError,
        ):
            assert _get_clocked_time_tz(None) is None


class test_clocked_timezone(TestCase):

    naive = datetime(2026, 3, 9, 15, 0)

    def test_naive_time_uses_app_timezone(self):
        c = clocked(self.naive, app=_app('America/New_York'))
        assert c.clocked_time == self.naive.replace(tzinfo=NEW_YORK)
        assert c.clocked_time.utcoffset() == timedelta(hours=-4)

    @override_settings(USE_TZ=False, TIME_ZONE='America/New_York')
    def test_naive_time_uses_django_timezone_without_app(self):
        c = clocked(self.naive)
        assert c.clocked_time.astimezone(dt_timezone.utc) == datetime(
            2026, 3, 9, 19, 0, tzinfo=dt_timezone.utc,
        )

    def test_naive_time_is_utc_when_no_timezone_found(self):
        with mock.patch(
            'django_celery_beat.clockedschedule._get_clocked_time_tz',
            return_value=None,
        ):
            c = clocked(self.naive)
        assert c.clocked_time == self.naive.replace(tzinfo=dt_timezone.utc)

    def test_aware_time_is_unchanged(self):
        aware = datetime(2026, 3, 9, 15, 0, tzinfo=dt_timezone.utc)
        c = clocked(aware, app=_app('America/New_York'))
        assert c.clocked_time == aware
        assert c.clocked_time.tzinfo is dt_timezone.utc

    def test_is_due_respects_local_time(self):
        # 15:00 New York == 19:00 UTC; at 18:59 UTC the task is not due yet
        # (it would be if the naive time were read as UTC).
        before = datetime(2026, 3, 9, 18, 59, tzinfo=dt_timezone.utc)
        c = clocked(self.naive, nowfun=lambda: before,
                    app=_app('America/New_York'))
        state = c.is_due(None)
        assert not state.is_due
        assert state.next == 60

        after = datetime(2026, 3, 9, 19, 0, 1, tzinfo=dt_timezone.utc)
        c = clocked(self.naive, nowfun=lambda: after,
                    app=_app('America/New_York'))
        assert c.is_due(None).is_due


@pytest.mark.django_db
class test_ClockedSchedule_model_timezone(TestCase):

    @override_settings(USE_TZ=False, TIME_ZONE='America/New_York')
    def test_naive_db_value_is_local_time(self):
        cs = ClockedSchedule.objects.create(
            clocked_time=datetime(2026, 3, 9, 15, 0),
        )
        cs.refresh_from_db()
        assert timezone.is_naive(cs.clocked_time)
        schedule_time = cs.schedule.clocked_time
        assert schedule_time.astimezone(dt_timezone.utc) == datetime(
            2026, 3, 9, 19, 0, tzinfo=dt_timezone.utc,
        )

"""Clocked schedule Implementation."""

from celery import schedules
from celery.utils.time import maybe_make_aware

from .utils import NEVER_CHECK_TIMEOUT


def _get_clocked_time_tz(app):
    """Return timezone for interpreting naive clocked_time (local time, not UTC)."""
    if app is not None and getattr(app.conf, 'timezone', None):
        return app.conf.timezone
    try:
        from django.utils import timezone as django_tz
        return django_tz.get_current_timezone()
    except Exception:
        return None


class clocked(schedules.BaseSchedule):  # noqa: PLW1641
    """clocked schedule.

    Depends on PeriodicTask one_off=True
    """

    def __init__(self, clocked_time, nowfun=None, app=None):
        """Initialize clocked."""
        tz = _get_clocked_time_tz(app)
        if tz is not None:
            # Interpret naive datetimes as local time (Django/celery app TZ), not UTC,
            # so "3:00 PM" runs at 3 PM local instead of 3 PM UTC.
            self.clocked_time = maybe_make_aware(clocked_time, tz=tz, naive_as_utc=False)
        else:
            self.clocked_time = maybe_make_aware(clocked_time)
        super().__init__(nowfun=nowfun, app=app)

    def remaining_estimate(self, last_run_at):
        return self.clocked_time - self.now()

    def is_due(self, last_run_at):
        rem_delta = self.remaining_estimate(None)
        remaining_s = max(rem_delta.total_seconds(), 0)
        if remaining_s == 0:
            return schedules.schedstate(is_due=True, next=NEVER_CHECK_TIMEOUT)
        return schedules.schedstate(is_due=False, next=remaining_s)

    def __repr__(self):
        return f'<clocked: {self.clocked_time}>'

    def __eq__(self, other):
        if isinstance(other, clocked):
            return self.clocked_time == other.clocked_time
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __reduce__(self):
        return self.__class__, (self.clocked_time, self.nowfun)

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hrms.models import LeavePolicy


@dataclass(frozen=True)
class LeaveYearWindow:
    start_date: date
    end_date: date


class LeaveYearService:
    @staticmethod
    def current_leave_year(*, leave_policy: LeavePolicy | None, anchor_date: date) -> LeaveYearWindow:
        leave_year_type = getattr(leave_policy, "leave_year_type", LeavePolicy.LeaveYearType.FINANCIAL_YEAR)
        if leave_year_type == LeavePolicy.LeaveYearType.CALENDAR_YEAR:
            return LeaveYearWindow(
                start_date=date(anchor_date.year, 1, 1),
                end_date=date(anchor_date.year, 12, 31),
            )
        if leave_year_type == LeavePolicy.LeaveYearType.CUSTOM_RANGE:
            return LeaveYearService._custom_window(leave_policy=leave_policy, anchor_date=anchor_date)
        return LeaveYearWindow(
            start_date=date(anchor_date.year if anchor_date.month >= 4 else anchor_date.year - 1, 4, 1),
            end_date=date(anchor_date.year + 1 if anchor_date.month >= 4 else anchor_date.year, 3, 31),
        )

    @classmethod
    def previous_leave_year(cls, *, leave_policy: LeavePolicy | None, anchor_date: date) -> LeaveYearWindow:
        current = cls.current_leave_year(leave_policy=leave_policy, anchor_date=anchor_date)
        previous_anchor = current.start_date.replace(day=1).toordinal() - 1
        return cls.current_leave_year(leave_policy=leave_policy, anchor_date=date.fromordinal(previous_anchor))

    @classmethod
    def next_leave_year(cls, *, leave_policy: LeavePolicy | None, anchor_date: date) -> LeaveYearWindow:
        current = cls.current_leave_year(leave_policy=leave_policy, anchor_date=anchor_date)
        next_anchor = current.end_date.toordinal() + 1
        return cls.current_leave_year(leave_policy=leave_policy, anchor_date=date.fromordinal(next_anchor))

    @classmethod
    def belongs_to_leave_year(cls, *, leave_policy: LeavePolicy | None, target_date: date, anchor_date: date | None = None) -> bool:
        window = cls.current_leave_year(leave_policy=leave_policy, anchor_date=anchor_date or target_date)
        return window.start_date <= target_date <= window.end_date

    @staticmethod
    def _custom_window(*, leave_policy: LeavePolicy | None, anchor_date: date) -> LeaveYearWindow:
        start_month = int(getattr(leave_policy, "year_start_month", 1) or 1)
        start_day = int(getattr(leave_policy, "year_start_day", 1) or 1)
        end_month = int(getattr(leave_policy, "year_end_month", 12) or 12)
        end_day = int(getattr(leave_policy, "year_end_day", 31) or 31)

        start_md = (start_month, start_day)
        end_md = (end_month, end_day)
        current_md = (anchor_date.month, anchor_date.day)

        crosses_year = start_md > end_md
        if not crosses_year:
            year = anchor_date.year if current_md >= start_md else anchor_date.year - 1
            return LeaveYearWindow(
                start_date=date(year, start_month, start_day),
                end_date=date(year, end_month, end_day),
            )

        if current_md >= start_md:
            start_year = anchor_date.year
            end_year = anchor_date.year + 1
        else:
            start_year = anchor_date.year - 1
            end_year = anchor_date.year
        return LeaveYearWindow(
            start_date=date(start_year, start_month, start_day),
            end_date=date(end_year, end_month, end_day),
        )

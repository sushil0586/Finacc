# HRMS Attendance Capture Backend Test Notes

Use payroll-enabled tests for attendance capture because the suite verifies that attendance summaries feed the payroll resolver.

Recommended command:

```bash
ENABLE_PAYROLL_IN_TESTS=1 ./venv/bin/python manage.py test hrms.tests.test_attendance_capture --keepdb --noinput -v 2
```

Why `--keepdb`:
- it reuses `test_finacc_db` when present
- it avoids repeated create/drop cycles that are more likely to hang on PostgreSQL during large migration runs

If the test database appears locked, inspect active sessions with:

```bash
psql -h 127.0.0.1 -p 5432 -U ansh -d postgres -c "select datname,pid,usename,state,wait_event_type,wait_event,query from pg_stat_activity where datname in ('finacc_db','test_finacc_db') order by datname,pid;"
```

If stale `test_finacc_db` sessions need cleanup, terminate them with:

```bash
psql -h 127.0.0.1 -p 5432 -U ansh -d postgres -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = 'test_finacc_db' and pid <> pg_backend_pid();"
```

If the test database exists in a bad state and needs a clean rebuild:

```bash
psql -h 127.0.0.1 -p 5432 -U ansh -d postgres -c "drop database if exists test_finacc_db;"
ENABLE_PAYROLL_IN_TESTS=1 ./venv/bin/python manage.py test hrms.tests.test_attendance_capture --keepdb --noinput -v 2
```

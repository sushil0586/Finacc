# Platform Operations Staging Runbook

## Approval Expiry Scheduler

The scheduler expires approved platform operations after
`PLATFORM_OPS_APPROVAL_TTL_HOURS`. It never executes an approved operation and
does not modify pending, rejected, cancelled, succeeded, or already failed
operations.

### Deploy And Enable

The backend deployment helpers install and start the timer. To install it
manually on EC2:

```bash
cd /home/ubuntu/Finacc
sudo cp deploy/ec2/finacc-platform-approval-expiry.service /etc/systemd/system/
sudo cp deploy/ec2/finacc-platform-approval-expiry.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now finacc-platform-approval-expiry.timer
sudo systemctl start finacc-platform-approval-expiry.service
```

### Staging Acceptance

1. Confirm `.env` contains the intended TTL, normally `24` hours.
2. Preview the affected operation IDs without mutation:

```bash
cd /home/ubuntu/Finacc
./venv/bin/python manage.py expire_platform_approvals --dry-run --json
```

3. Run the service and inspect its machine-readable result:

```bash
sudo systemctl start finacc-platform-approval-expiry.service
sudo journalctl -u finacc-platform-approval-expiry.service -n 20 --no-pager
```

4. Confirm the timer is active and has a future trigger:

```bash
systemctl is-enabled finacc-platform-approval-expiry.timer
systemctl is-active finacc-platform-approval-expiry.timer
systemctl list-timers finacc-platform-approval-expiry.timer --no-pager
```

5. In Platform Operations, confirm each reported ID is terminal with failure
   code `approval_expired` and has exactly one immutable
   `platform.operation.approval.expired` audit event.
6. Run the service again. The second result must report zero additional expired
   operations.

Record the command output, timer status, journal timestamp, operation IDs, and
reviewer in the release evidence. Do not place customer payloads or credentials
in the evidence record.

### Failure Drill

Temporarily stop PostgreSQL in an approved staging window, start the oneshot
service, and confirm it fails visibly in `systemctl status` and the journal.
Restore PostgreSQL and rerun the service; it must succeed without duplicate
audit events. Do not run this drill in production.

### Monitoring

Alert when the service unit enters `failed` state or when no successful journal
entry is observed for more than two hours. The JSON line must parse and contain
`dry_run`, `matched`, `expired`, and `operation_ids`.

Useful diagnostics:

```bash
sudo systemctl status finacc-platform-approval-expiry.service --no-pager
sudo journalctl -u finacc-platform-approval-expiry.service --since "2 hours ago" --no-pager
sudo systemctl reset-failed finacc-platform-approval-expiry.service
```

### Disable Or Roll Back

Disabling the scheduler does not reopen expired approvals. Operators must submit
and approve replacement requests.

```bash
sudo systemctl disable --now finacc-platform-approval-expiry.timer
sudo rm -f /etc/systemd/system/finacc-platform-approval-expiry.timer
sudo rm -f /etc/systemd/system/finacc-platform-approval-expiry.service
sudo systemctl daemon-reload
```

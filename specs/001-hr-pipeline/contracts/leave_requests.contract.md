# Contract: `leave_requests.json` — Workforce: Leave (nested JSON)

**Requests**: 5,372 (array of objects)
**Rules**: 16 (both steps Approved + not cancelled ⇒ counts), 17 (range minus Sundays &
plant holidays), 12 (status priority), 18 (entitlement, Q10)

```json
{
 "request_id": "LR000001",
 "employee": {"emp_id": "E10001", "plant": "Korangi Plant"},
 "leave": {"type": "Casual", "from": "2026-04-08", "to": "2026-04-08", "days_requested": 1},
 "submitted_at": "2026-04-04T10:10:00",
 "approvals": [
   {"step": 1, "approver_role": "Manager", "approver_id": "E10827",
    "action": "Approved", "acted_at": "..."},
   {"step": 2, "approver_role": "HR", "approver_id": "HR-DESK",
    "action": "Approved", "acted_at": "..."}
 ],
 "cancelled_at": "2026-04-05T21:10:00"   // may be null
}
```

**Planted mess**: rejected / pending / cancelled requests present; `approvals` nested (must be
flattened into request + step rows); leave ranges spanning Sundays and plant holidays;
**`days_requested` is employee-typed and must never be used for counting**.

**Counting rule (16)**: counts only if step 1 = Approved AND step 2 = Approved AND
`cancelled_at` is empty/null. Flattening output:
- `staging.leave_requests` (1/request, `is_counted` flag)
- `staging.leave_approval_steps` (1/request/step)
- `staging.leave_days` (1/countable day = range − Sundays − plant holidays, `is_counted` only)

**Validation**: 5,372 request rows; steps = 2 × requests (verify actuals in profiling);
every step `action` ∈ {Approved, Rejected, Pending, Cancelled…} domain from profiling;
leave_days count ≤ sum of (range lengths); no leave_day on Sunday or plant holiday.

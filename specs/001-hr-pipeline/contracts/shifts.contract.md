# Contract: `shifts.json` — Workforce: Shifts

**Rows**: 4 (top-level key `shifts`, array of objects)
**Rules**: 5 (who works which shift), 7 (night attribution), 13 (grace/lateness), 14 (OT vs shift end)

```json
{"shift_code","name","start_time","end_time","crosses_midnight","grace_minutes","applies_to"}
```

| code | start | end | crosses_midnight | grace | applies_to |
|---|---|---|---|---|---|
| DAY | 06:00 | 14:00 | false | 10 | Plant shift workers |
| EVE | 14:00 | 22:00 | false | 10 | Plant shift workers |
| NIGHT | 22:00 | 06:00 | **true** | 10 | Plant shift workers |
| GEN | 09:00 | 17:30 | false | 10 | Head office and plant staff |

**Validation**: 4 codes present; `grace_minutes = 10` everywhere (matches Rule 13's 10-minute
threshold); NIGHT is the only `crosses_midnight=true`; times parse as `HH:MM`.

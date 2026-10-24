"""T018-T020 - Stage 2.4: punches (Rules 8, 11, 9, 7; FR-010/011/012).

Processing order is fixed by research R3 - each step's output feeds the next:

1. **map** (Rule 8)      : composite key (device_id + device_user_id) -> emp_id.
                            No mapping = contractor/visitor -> rejected_punches.
2. **drift-correct** (Rule 11): per device, average first-punch time vs the
                            employee's roster shift start. A device whose mean
                            delta deviates >= 30 min from the other devices is
                            clock-shifted; offset = -(dev_mean - median_others).
                            Evidence -> staging.drift_corrections + docs.
3. **2-min dedupe** (Rule 9)  : greedy first-wins per employee on CORRECTED
                            times: keep a punch only if >= 120 s after the
                            previous KEPT punch. Collapsed rows are kept in
                            rejected_punches (reason=duplicate_within_2min) so
                            raw = staging + rejected stays exact.
4. **attribute** (Rule 7) : NIGHT punches with clock time < 12:00 step back one
                            day (they close the shift that started the previous
                            22:00), so early-morning 1 Oct check-outs land on
                            30 Sep. A plain −6h only covers [00:00, 06:00) and
                            strands the 06:00+ check-out stragglers on the same
                            date (see ADR-002).
"""

from __future__ import annotations

import pandas as pd

from config import DOCS_DIR, MIN_GAP_MINUTES
from common import db
from transform.util import now_iso, print_counts, replace_rows

PUNCH_COLS = ["emp_id", "punch_time", "device_id", "device_user_id",
              "src_punch_id", "shift_date"]
REJECT_COLS = ["punch_id", "device_id", "device_user_id", "punch_time", "reason"]
DRIFT_COLS = ["device_id", "offset_minutes", "detection_method",
              "avg_first_punch_before", "avg_first_punch_after",
              "evidence_note", "corrected_at"]

DRIFT_MIN_DELTA = -120.0    # plausible first punch: <= 2 h before shift start
DRIFT_MAX_DELTA = 240.0     # ... <= 4 h after shift start
DRIFT_FLAG_MINUTES = 30.0   # device deviates from peer median by >= 30 min


def _attach_shift(df: pd.DataFrame, roster: pd.DataFrame, shifts: pd.DataFrame) -> pd.DataFrame:
    """Add (week_start, shift_code, start_time) for each punch's calendar date."""
    out = df.copy()
    day = out["punch_ts"].dt.normalize()
    out["_week"] = (day - pd.to_timedelta(day.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")
    out = out.merge(
        roster.rename(columns={"week_start": "_week"}),
        on=["emp_id", "_week"], how="left",
    )
    out = out.merge(shifts, on="shift_code", how="left")
    return out


def _seconds_of_day(ts: pd.Series) -> pd.Series:
    return (
        ts.dt.hour * 3600 + ts.dt.minute * 60 + ts.dt.second + ts.dt.microsecond / 1e6
    )


def _hhmmss(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def detect_drift(work: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Per-device mean(first punch - shift start); returns (samples, stats, offsets)."""
    first = work.loc[work.groupby(["emp_id", "_day"])["punch_ts"].idxmin()].copy()
    first["expected"] = first["_day_ts"] + pd.to_timedelta(
        first["start_time"].str.slice(0, 5) + ":00"
    )
    first["delta_min"] = (first["punch_ts"] - first["expected"]).dt.total_seconds() / 60.0
    samples = first[
        first["delta_min"].between(DRIFT_MIN_DELTA, DRIFT_MAX_DELTA)
    ].copy()

    stats = (
        samples.groupby("device_id")
        .agg(n=("delta_min", "size"), mean_delta=("delta_min", "mean"))
        .reset_index()
    )
    if stats.empty:
        return samples, stats, stats.iloc[0:0]

    rows = []
    for r in stats.itertuples():
        peers = stats.loc[stats["device_id"] != r.device_id, "mean_delta"]
        peer_med = float(peers.median()) if len(peers) else 0.0
        dev_delta = float(r.mean_delta)
        gap = dev_delta - peer_med
        if abs(gap) >= DRIFT_FLAG_MINUTES and r.n >= 50:
            rows.append({
                "device_id": r.device_id,
                "offset_minutes": int(round(-gap)),   # minutes to ADD to raw
                "dev_mean_delta": dev_delta,
                "peer_median_delta": peer_med,
                "gap_minutes": gap,
                "n_samples": int(r.n),
            })
    offsets = pd.DataFrame(rows)
    return samples, stats, offsets


def main() -> dict:
    now = now_iso()
    punches = db.read_sql(
        "SELECT punch_id, device_id, device_user_id, punch_time "
        "FROM raw.biometric_punches"
    )
    mapping = db.read_sql(
        "SELECT device_id, device_user_id, emp_id FROM raw.device_mapping"
    )
    roster = db.read_sql(
        "SELECT emp_id, week_start, shift_code FROM staging.shift_roster"
    )
    shifts = db.read_sql(
        "SELECT shift_code, start_time FROM staging.shifts"
    )

    # ---- part A: mapping (Rule 8) -------------------------------------------
    merged = punches.merge(
        mapping, on=["device_id", "device_user_id"], how="left", validate="m:1"
    )
    assert len(merged) == len(punches), "device_mapping composite key is not unique"
    unmapped = merged[merged["emp_id"].isna()].copy()
    mapped = merged[merged["emp_id"].notna()].copy()
    mapped["punch_ts"] = pd.to_datetime(mapped["punch_time"])
    mapped["_day"] = mapped["punch_ts"].dt.normalize().dt.strftime("%Y-%m-%d")
    mapped["_day_ts"] = pd.to_datetime(mapped["_day"])

    # ---- part B: drift detection & correction (Rule 11) ---------------------
    work = _attach_shift(mapped, roster, shifts)
    assert work["shift_code"].notna().all(), "punch week missing from roster"
    samples, stats, offsets = detect_drift(work)

    # per-device before evidence (clock mean of sampled first punches)
    before_clock = samples.groupby("device_id")["punch_ts"].apply(
        lambda s: _hhmmss(_seconds_of_day(s).mean())
    ).to_dict()

    drift_rows = []
    corrected_devices = 0
    if not offsets.empty:
        for o in offsets.itertuples():
            mapped.loc[mapped["device_id"] == o.device_id, "punch_ts"] += pd.to_timedelta(
                int(o.offset_minutes), unit="min"
            )
            corrected_devices += 1
        # after evidence on corrected times
        work_after = _attach_shift(mapped, roster, shifts)
        samples_after, stats_after, _ = detect_drift(work_after)
        after_clock = samples_after.groupby("device_id")["punch_ts"].apply(
            lambda s: _hhmmss(_seconds_of_day(s).mean())
        ).to_dict()
        after_delta = stats_after.set_index("device_id")["mean_delta"].to_dict()
        for o in offsets.itertuples():
            drift_rows.append({
                "device_id": o.device_id,
                "offset_minutes": int(o.offset_minutes),
                "detection_method": (
                    "mean(first punch of employee-day - roster shift start) per "
                    "device; offset = -(device mean - median of other devices)"
                ),
                "avg_first_punch_before": before_clock.get(o.device_id),
                "avg_first_punch_after": after_clock.get(o.device_id),
                "evidence_note": (
                    f"n={o.n_samples} first punches; device mean delta "
                    f"{o.dev_mean_delta:+.1f} min vs peer median "
                    f"{o.peer_median_delta:+.1f} min (gap {o.gap_minutes:+.1f} min); "
                    f"after correction device mean delta "
                    f"{after_delta.get(o.device_id, float('nan')):+.1f} min"
                ),
                "corrected_at": now,
            })

    # ---- part C: 2-minute dedupe (Rule 9) -----------------------------------
    mapped = mapped.sort_values(["emp_id", "punch_ts"], kind="mergesort")
    keep_mask = []
    collapsed = 0
    gap_s = MIN_GAP_MINUTES * 60
    for _, g in mapped.groupby("emp_id", sort=False):
        last = None
        for ts in g["punch_ts"]:
            if last is None or (ts - last).total_seconds() >= gap_s:
                keep_mask.append(True)
                last = ts
            else:
                keep_mask.append(False)
                collapsed += 1
    mapped["_keep"] = keep_mask
    kept = mapped[mapped["_keep"]].copy()
    dropped = mapped[~mapped["_keep"]].copy()

    # ---- part D: night-shift attribution (Rule 7) ---------------------------
    # NIGHT runs 22:00 -> 06:00: a punch before noon belongs to the shift that
    # started the PREVIOUS evening, so date(punch) must step back one day.
    # R5's fixed -6h only covers punches in [00:00, 06:00); the data's 06:00-06:30
    # check-out stragglers land at 00:00-00:30 the same day under -6h, which
    # mis-pairs them with the NEXT shift's check-in (15h "worked" spans).
    # Pre-noon -> previous day reproduces -6h for [00:00,06:00) and fixes the
    # stragglers: 1-Oct 06:10 check-outs still attribute to 30-Sep (contract).
    kept = _attach_shift(kept, roster, shifts)
    night = kept["shift_code"] == "NIGHT"
    morning = night & (kept["punch_ts"].dt.hour < 12)
    eff = kept["punch_ts"].where(~morning, kept["punch_ts"] - pd.Timedelta(days=1))
    kept["shift_date"] = eff.dt.strftime("%Y-%m-%d")

    # ---- write staging -------------------------------------------------------
    out = pd.DataFrame({
        "emp_id": kept["emp_id"],
        "punch_time": kept["punch_ts"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "device_id": kept["device_id"],
        "device_user_id": kept["device_user_id"],
        "src_punch_id": kept["punch_id"],
        "shift_date": kept["shift_date"],
    })
    n_punch = replace_rows(out, "staging.punches")

    unmapped_out = unmapped[["punch_id", "device_id", "device_user_id", "punch_time"]].copy()
    unmapped_out["reason"] = "unmapped_device_user"
    dropped_out = dropped[["punch_id", "device_id", "device_user_id"]].copy()
    dropped_out["punch_time"] = dropped["punch_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    dropped_out["reason"] = "duplicate_within_2min"
    rejects = pd.concat(
        [unmapped_out[REJECT_COLS], dropped_out[REJECT_COLS]], ignore_index=True
    )
    n_rej = replace_rows(rejects, "staging.rejected_punches")

    drift_df = pd.DataFrame(drift_rows, columns=DRIFT_COLS)
    n_drift = replace_rows(drift_df, "staging.drift_corrections")

    # ---- docs: drift analysis paragraph (T019) -------------------------------
    _write_drift_doc(stats, offsets, drift_rows, before_clock)

    stats_out = {
        "raw_punches": len(punches),
        "mapped": int(merged["emp_id"].notna().sum()),
        "rejected_unmapped": len(unmapped),
        "rejected_collapsed": collapsed,
        "staging_punches": n_punch,
        "drift_devices": corrected_devices,
    }
    print_counts("04_punches", stats_out)
    if not stats.empty:
        print(stats.to_string(index=False))
    return stats_out


def _write_drift_doc(stats: pd.DataFrame, offsets: pd.DataFrame,
                      drift_rows: list[dict], before_clock: dict) -> None:
    lines = [
        "# Device clock drift analysis (Rule 11)",
        "",
        "Generated by `transform/04_punches.py`.",
        "",
        "## Method",
        "",
        "1. Map punches to employees (Rule 8), keep mapped only.",
        "2. For every employee-day take the **first punch** (check-in proxy).",
        "3. Expected time = that calendar day's roster shift start "
        "(`shift_roster` joined by Monday-week).",
        "4. `delta = first punch - expected start`; samples with delta outside "
        "[-120, +240] min are excluded (late-night spill, mis-attributed first "
        "punches).",
        "5. Mean delta per device: a clock that is off shifts EVERY employee on "
        "that device by the same amount, while normal lateness cancels out in "
        "the mean.",
        "6. `offset = -(device mean - median of the other devices)`; devices "
        "deviating >= 30 min are corrected (Rule 11).",
        "",
        "## Per-device evidence",
        "",
        "| device | samples | mean delta (min) | mean first punch (raw clock) |",
        "|---|---:|---:|---|",
    ]
    for r in stats.itertuples():
        lines.append(
            f"| {r.device_id} | {r.n} | {r.mean_delta:+.1f} | "
            f"{before_clock.get(r.device_id, '-')} |"
        )
    lines += ["", "## Corrections applied", ""]
    if drift_rows:
        for d in drift_rows:
            lines += [
                f"- **{d['device_id']}**: offset {d['offset_minutes']:+d} min. "
                f"{d['evidence_note']}. Clock moved {d['avg_first_punch_before']} "
                f"-> {d['avg_first_punch_after']}.",
            ]
    else:
        lines.append("- none (no device deviated by >= 30 min)")
    path = DOCS_DIR / "drift_analysis.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  drift analysis written: {path}")


if __name__ == "__main__":
    main()

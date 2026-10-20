#!/usr/bin/env bash


set -uo pipefail

IMPL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$IMPL_DIR/results"

mkdir -p "$RESULTS_DIR/figures" "$RESULTS_DIR/schedules"

echo "================================================================"
echo "  OCP Experiment Pipeline — Volet 3 & Volet 4"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  IMPL_DIR    : $IMPL_DIR"
echo "  RESULTS_DIR : $RESULTS_DIR"
echo "================================================================"

# Pass directories as arguments to avoid __file__ issues in here-doc
python3 - "$IMPL_DIR" "$RESULTS_DIR" <<'PYEOF'
# =============================================================================
#  Inline Python — full experiment runner
# =============================================================================
import sys, os, csv, json, time, traceback

# ── matplotlib non-interactive backend (must be set BEFORE any other import) ─
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Path setup ───────────────────────────────────────────────────────────────
IMPL_DIR    = sys.argv[1]
RESULTS_DIR = sys.argv[2]
sys.path.insert(0, IMPL_DIR)

# ── Project imports ───────────────────────────────────────────────────────────
from generator          import generate_instance
from baseline           import run_baseline
from model_base         import solve_base_model
from model_pl           import solve_pl_model
from epsilon_constraint import run_epsilon_constraint
from hybrid_scala       import run_chalmet

# ── Constants ─────────────────────────────────────────────────────────────────
SEED       = 42
TIME_LIMIT = 600   # seconds per sub-problem
S_VALUES   = [1, 0.1, 0.01]

CSV_COLS = [
    "volet", "T", "D", "N", "C",
    "method", "s",
    "WL", "OT", "cpu",
    "bb_nodes", "nb_vars", "nb_constrs",
    "YN_size", "max_gap",
    "status",
]

# Gurobi status code → human-readable string
GUROBI_STATUS = {
    2: "optimal",
    3: "infeasible",
    4: "infeasible",   # INF_OR_UNBD
    5: "unbounded",
    9: "time_limit",
}

# =============================================================================
#  Helper functions
# =============================================================================

def gurobi_status_str(code):
    return GUROBI_STATUS.get(code, f"unknown_status_{code}")


def extract_schedule_from_xy(result, instance):
    """
    Build {tid: day_or_None} from x:{(tid,d):0/1} and y:{tid:0/1}.
    Works for baseline, base_model, and reinforced results.
    """
    x = result.get("x", {})
    y = result.get("y", {})
    schedule = {}
    for patient in instance["patients"]:
        for tr in patient["treatments"]:
            tid = tr["treatment_id"]
            if y.get(tid, 0) > 0.5:
                schedule[tid] = None
            else:
                found = None
                for (i, d), val in x.items():
                    if i == tid and val > 0.5:
                        found = d
                        break
                schedule[tid] = found
    return schedule


def build_patients_json(schedule, instance):
    """
    Convert a schedule {tid: day_or_None} to the patient-list JSON format:
      [{"patient_id":p, "planned":bool, "sessions":[{"treatment_id":t,"day":d},...]}]
    """
    patients_json = []
    for patient in instance["patients"]:
        sessions = []
        for tr in patient["treatments"]:
            tid = tr["treatment_id"]
            day = schedule.get(tid)
            if day is not None:
                sessions.append({"treatment_id": tid, "day": int(day)})
        patients_json.append({
            "patient_id": patient["patient_id"],
            "planned":    len(sessions) > 0,
            "sessions":   sessions,
        })
    return patients_json


def compute_max_gap(points):
    """Max gap between consecutive OT values in the Pareto front."""
    if len(points) < 2:
        return 0.0
    ot_sorted = sorted(p["OT"] for p in points)
    return max(ot_sorted[i+1] - ot_sorted[i] for i in range(len(ot_sorted) - 1))


def save_figure(points, title, fig_path):
    """Save the Pareto front as a PDF figure."""
    try:
        pairs = sorted((p["OT"], p["WL"]) for p in points)
        ot_vals = [pr[0] for pr in pairs]
        wl_vals = [pr[1] for pr in pairs]

        fig, ax = plt.subplots(figsize=(8, 6))
        ax.plot(ot_vals, wl_vals, linestyle='-', marker='o',
                markersize=4, linewidth=1.0, color='steelblue', alpha=0.85)
        ax.set_xlabel("OT — Overtime (min)", fontsize=12)
        ax.set_ylabel("WL — Weighted Workload", fontsize=12)
        ax.set_title(title, fontsize=11, pad=10)
        ax.grid(True, alpha=0.3, linestyle='--')
        fig.tight_layout()
        fig.savefig(fig_path, format='pdf', bbox_inches='tight')
        plt.close(fig)
    except Exception as fig_err:
        print(f"    [WARN] Figure not saved ({fig_path}): {fig_err}", flush=True)


def append_csv_row(csv_path, row):
    with open(csv_path, "a", newline="") as f:
        csv.writer(f).writerow(row)


def save_json(json_path, data):
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)


def log(volet, idx, total, T, D, N, C, method, detail):
    tag = f"[V{volet} | {idx:2d}/{total}] T={T:<3} D={D:<2} N={N:<2} C={C:<2}"
    print(f"{tag}  — {method:<22}  {detail}", flush=True)


# =============================================================================
#  Instance parameter grids
# =============================================================================

# Volet 3: T∈{50,150,300} × D∈{6,10} × N∈{4,5} × C∈{5,10}  → 24 instances
volet3_params = [
    (T, D, N, C)
    for T in [50, 150, 300]
    for D in [6, 10]
    for N in [4, 5]
    for C in [5, 10]
]

# Volet 4: T∈{50,150,300} × D∈{6,10} × N∈{1,2,3} × C∈{1,2,3} → 54 instances
volet4_params = [
    (T, D, N, C)
    for T in [50, 150, 300]
    for D in [6, 10]
    for N in [1, 2, 3]
    for C in [1, 2, 3]
]

# =============================================================================
#  CSV header initialisation
# =============================================================================

for vname in ["volet3", "volet4"]:
    csv_path = os.path.join(RESULTS_DIR, f"results_{vname}.csv")
    with open(csv_path, "w", newline="") as f:
        csv.writer(f).writerow(CSV_COLS)

# =============================================================================
#  Core experiment loop
# =============================================================================

def run_volet(volet_num, params_list):
    total    = len(params_list)
    csv_path = os.path.join(RESULTS_DIR, f"results_volet{volet_num}.csv")

    for idx, (T, D, N, C) in enumerate(params_list, start=1):
        tag = f"V{volet_num}_T{T}_D{D}_N{N}_C{C}"
        print(f"\n{'─'*72}")
        print(f"  [{idx}/{total}]  {tag}  (seed={SEED}  time_limit={TIME_LIMIT}s)")
        print(f"{'─'*72}")

        # Generate instance (same seed every time → reproducible)
        instance = generate_instance(T, D, N, C, seed=SEED)

        # ── Helpers local to this instance ────────────────────────────────────

        def sched_path(method_label):
            return os.path.join(RESULTS_DIR, "schedules",
                                f"schedule_{tag}_{method_label}.json")

        def fig_path(method_label):
            return os.path.join(RESULTS_DIR, "figures",
                                f"front_{tag}_{method_label}.pdf")

        # ── 1. BASELINE ───────────────────────────────────────────────────────
        try:
            res      = run_baseline(instance)
            schedule = extract_schedule_from_xy(res, instance)

            save_json(sched_path("baseline"), {
                "method":   "baseline",
                "WL":       res["WL"],
                "OT":       res["OT"],
                "patients": build_patients_json(schedule, instance),
            })

            append_csv_row(csv_path, [
                volet_num, T, D, N, C,
                "baseline", "",
                round(res["WL"],  6), round(res["OT"],  6),
                round(res["cpu_time"], 4),
                "", "", "", "", "",
                "optimal",   # heuristic always returns a feasible schedule
            ])
            log(volet_num, idx, total, T, D, N, C,
                "baseline",
                f"DONE (cpu={res['cpu_time']:.2f}s  WL={res['WL']:.1f}  OT={res['OT']:.1f})")

        except Exception as exc:
            msg = str(exc).replace('\n', ' ')
            append_csv_row(csv_path, [
                volet_num, T, D, N, C,
                "baseline", "",
                "", "", "", "", "", "", "", "",
                f"error: {msg}",
            ])
            log(volet_num, idx, total, T, D, N, C,
                "baseline", f"ERROR: {msg}")

        # ── 2. BASE MODEL ─────────────────────────────────────────────────────
        try:
            res = solve_base_model(instance, time_limit=TIME_LIMIT, verbose=False)
            sc  = gurobi_status_str(res["status"])

            if res["WL"] is not None:
                schedule = extract_schedule_from_xy(res, instance)
                save_json(sched_path("base_model"), {
                    "method":   "base_model",
                    "WL":       res["WL"],
                    "OT":       res["OT"],
                    "patients": build_patients_json(schedule, instance),
                })
                log(volet_num, idx, total, T, D, N, C, "base_model",
                    f"DONE (cpu={res['cpu_time']:.2f}s  "
                    f"nodes={res['bb_nodes']}  "
                    f"vars={res['n_vars']}  constrs={res['n_constrs']})")
            else:
                log(volet_num, idx, total, T, D, N, C, "base_model",
                    sc.upper())

            append_csv_row(csv_path, [
                volet_num, T, D, N, C,
                "base_model", "",
                round(res["WL"],  6) if res["WL"]  is not None else "",
                round(res["OT"],  6) if res["OT"]  is not None else "",
                round(res["cpu_time"], 4),
                res["bb_nodes"], res["n_vars"], res["n_constrs"],
                "", "",
                sc,
            ])

        except Exception as exc:
            msg = str(exc).replace('\n', ' ')
            append_csv_row(csv_path, [
                volet_num, T, D, N, C,
                "base_model", "",
                "", "", "", "", "", "", "", "",
                f"error: {msg}",
            ])
            log(volet_num, idx, total, T, D, N, C,
                "base_model", f"ERROR: {msg}")

        # ── 3. REINFORCED MODEL (model_pl) ────────────────────────────────────
        try:
            res = solve_pl_model(instance, time_limit=TIME_LIMIT, verbose=False)
            sc  = gurobi_status_str(res["status"])

            if res["WL"] is not None:
                schedule = extract_schedule_from_xy(res, instance)
                save_json(sched_path("reinforced"), {
                    "method":   "reinforced",
                    "WL":       res["WL"],
                    "OT":       res["OT"],
                    "patients": build_patients_json(schedule, instance),
                })
                log(volet_num, idx, total, T, D, N, C, "reinforced",
                    f"DONE (cpu={res['cpu_time']:.2f}s  "
                    f"nodes={res['bb_nodes']}  "
                    f"vars={res['n_vars']}  constrs={res['n_constrs']})")
            else:
                log(volet_num, idx, total, T, D, N, C, "reinforced",
                    sc.upper())

            append_csv_row(csv_path, [
                volet_num, T, D, N, C,
                "reinforced", "",
                round(res["WL"],  6) if res["WL"]  is not None else "",
                round(res["OT"],  6) if res["OT"]  is not None else "",
                round(res["cpu_time"], 4),
                res["bb_nodes"], res["n_vars"], res["n_constrs"],
                "", "",
                sc,
            ])

        except Exception as exc:
            msg = str(exc).replace('\n', ' ')
            append_csv_row(csv_path, [
                volet_num, T, D, N, C,
                "reinforced", "",
                "", "", "", "", "", "", "", "",
                f"error: {msg}",
            ])
            log(volet_num, idx, total, T, D, N, C,
                "reinforced", f"ERROR: {msg}")

        # ── 4-6. ε-CONSTRAINT  s ∈ {1, 0.1, 0.01} ───────────────────────────
        for s in S_VALUES:
            method_label = f"eps_s{s}"
            try:
                t0     = time.time()
                points = run_epsilon_constraint(
                    instance, s=s, time_limit=TIME_LIMIT, verbose=False
                )
                cpu_total = time.time() - t0

                if points:
                    yn_size = len(points)
                    max_gap = compute_max_gap(points)

                    # JSON — all Pareto points + schedules
                    points_json = []
                    for p in points:
                        pts_patients = build_patients_json(
                            p.get("schedule", {}), instance
                        )
                        points_json.append({
                            "WL":       p["WL"],
                            "OT":       p["OT"],
                            "patients": pts_patients,
                        })
                    save_json(sched_path(method_label), {
                        "method": method_label,
                        "points": points_json,
                    })

                    # PDF figure
                    save_figure(
                        points,
                        f"Pareto Front — ε-constraint  s={s}\n{tag}",
                        fig_path(method_label),
                    )

                    status = "optimal"
                    log(volet_num, idx, total, T, D, N, C, f"eps s={s}",
                        f"DONE (|YN|={yn_size}  max_gap={max_gap:.3f}  cpu={cpu_total:.2f}s)")
                else:
                    yn_size, max_gap, status = 0, 0.0, "infeasible"
                    log(volet_num, idx, total, T, D, N, C, f"eps s={s}",
                        "INFEASIBLE (0 points returned)")

                append_csv_row(csv_path, [
                    volet_num, T, D, N, C,
                    "eps", s,
                    "", "", round(cpu_total, 4),
                    "", "", "",
                    yn_size, round(max_gap, 6),
                    status,
                ])

            except Exception as exc:
                msg = str(exc).replace('\n', ' ')
                append_csv_row(csv_path, [
                    volet_num, T, D, N, C,
                    "eps", s,
                    "", "", "", "", "", "", "", "",
                    f"error: {msg}",
                ])
                log(volet_num, idx, total, T, D, N, C,
                    f"eps s={s}", f"ERROR: {msg}")

        # ── 7-9. HYBRID CHALMET  s ∈ {1, 0.1, 0.01} ─────────────────────────
        for s in S_VALUES:
            method_label = f"hybrid_s{s}"
            try:
                t0     = time.time()
                points = run_chalmet(
                    instance, s=s, time_limit=TIME_LIMIT, verbose=False
                )
                cpu_total = time.time() - t0

                if points:
                    yn_size = len(points)
                    max_gap = compute_max_gap(points)

                    # JSON — all Pareto points + schedules
                    points_json = []
                    for p in points:
                        pts_patients = build_patients_json(
                            p.get("schedule", {}), instance
                        )
                        points_json.append({
                            "WL":       p["WL"],
                            "OT":       p["OT"],
                            "patients": pts_patients,
                        })
                    save_json(sched_path(method_label), {
                        "method": method_label,
                        "points": points_json,
                    })

                    # PDF figure
                    save_figure(
                        points,
                        f"Pareto Front — Hybrid Chalmet  s={s}\n{tag}",
                        fig_path(method_label),
                    )

                    status = "optimal"
                    log(volet_num, idx, total, T, D, N, C, f"hybrid s={s}",
                        f"DONE (|YN|={yn_size}  max_gap={max_gap:.3f}  cpu={cpu_total:.2f}s)")
                else:
                    yn_size, max_gap, status = 0, 0.0, "infeasible"
                    log(volet_num, idx, total, T, D, N, C, f"hybrid s={s}",
                        "INFEASIBLE (0 points returned)")

                append_csv_row(csv_path, [
                    volet_num, T, D, N, C,
                    "hybrid", s,
                    "", "", round(cpu_total, 4),
                    "", "", "",
                    yn_size, round(max_gap, 6),
                    status,
                ])

            except Exception as exc:
                msg = str(exc).replace('\n', ' ')
                append_csv_row(csv_path, [
                    volet_num, T, D, N, C,
                    "hybrid", s,
                    "", "", "", "", "", "", "", "",
                    f"error: {msg}",
                ])
                log(volet_num, idx, total, T, D, N, C,
                    f"hybrid s={s}", f"ERROR: {msg}")

    # End of volet
    print(f"\n{'═'*72}")
    print(f"  Volet {volet_num} done — {total} instances × 9 methods = {total*9} rows")
    print(f"  CSV  → {csv_path}")
    print(f"{'═'*72}")


# =============================================================================
#  Run both volets
# =============================================================================

print(f"\n{'#'*72}")
print(f"  VOLET 3  —  {len(volet3_params)} instances")
print(f"  Grid: T∈{{50,150,300}} × D∈{{6,10}} × N∈{{4,5}} × C∈{{5,10}}")
print(f"{'#'*72}")
run_volet(3, volet3_params)

print(f"\n{'#'*72}")
print(f"  VOLET 4  —  {len(volet4_params)} instances")
print(f"  Grid: T∈{{50,150,300}} × D∈{{6,10}} × N∈{{1,2,3}} × C∈{{1,2,3}}")
print(f"{'#'*72}")
run_volet(4, volet4_params)

print(f"\n{'='*72}")
print(f"  ALL DONE  —  {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  results/  →  {RESULTS_DIR}")
print(f"{'='*72}")

PYEOF

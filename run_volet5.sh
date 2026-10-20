#!/usr/bin/env bash
# =============================================================================
#  run_volet5.sh — OCP Volet 5 Experimental Pipeline
#  Pharmacy constraint extension — hybrid scalarization only
#
#  Usage:
#      cd IMPLEMENTATION
#      bash run_volet5.sh 2>&1 | tee volet5.log
#
#  Outputs (inside results/volet5/):
#      instances/          — 60 JSON instance files (5 versions × 12 combinations)
#      figures/            — 72 PDF figures (6 per combination)
#      results.json        — all YN + max_WL + min_OT schedules
# =============================================================================
set -uo pipefail

IMPL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$IMPL_DIR/results"
V5_DIR="$RESULTS_DIR/volet5"

mkdir -p "$V5_DIR/instances" "$V5_DIR/figures"

echo "================================================================"
echo "  OCP Volet 5 — Pharmacy Extension Pipeline"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  IMPL_DIR : $IMPL_DIR"
echo "  V5_DIR   : $V5_DIR"
echo "================================================================"

python3 - "$IMPL_DIR" "$V5_DIR" <<'PYEOF'
# =============================================================================
#  Inline Python — Volet 5 runner
# =============================================================================
import sys, os, json, time, traceback

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Directories ───────────────────────────────────────────────────────────────
IMPL_DIR  = sys.argv[1]
V5_DIR    = sys.argv[2]
INST_DIR  = os.path.join(V5_DIR, 'instances')
FIG_DIR   = os.path.join(V5_DIR, 'figures')
JSON_PATH = os.path.join(V5_DIR, 'results.json')

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, IMPL_DIR)
sys.path.insert(0, os.path.join(IMPL_DIR, 'volet5'))

# ── Imports ───────────────────────────────────────────────────────────────────
from generator              import generate_instance as gen_base
from generator_pharmacy1    import generate_instance as gen_pharm1
from generator_pharmacy2    import generate_instance as gen_pharm2
from hybrid_scala           import run_chalmet       as run_base
from hybrid_scala_pharmacy1 import run_chalmet       as run_pharm1
from hybrid_scala_pharmacy2 import run_chalmet       as run_pharm2

# ── Constants ─────────────────────────────────────────────────────────────────
SEED       = 42
TIME_LIMIT = 600   # 10 minutes per solve
S_VALUES   = [1, 0.1]

# versions: (label, generator, runner, extra_generator_kwargs)
VERSIONS = [
    ("base",         gen_base,   run_base,   {}),
    ("pharm1_cap20", gen_pharm1, run_pharm1, {"Pd": (20, 20)}),
    ("pharm1_cap40", gen_pharm1, run_pharm1, {"Pd": (40, 40)}),
    ("pharm2_np2",   gen_pharm2, run_pharm2, {"Np": 2}),
    ("pharm2_np10",  gen_pharm2, run_pharm2, {"Np": 10}),
]

COLORS = {
    "base":         "steelblue",
    "pharm1_cap20": "tomato",
    "pharm1_cap40": "salmon",
    "pharm2_np2":   "seagreen",
    "pharm2_np10":  "lightgreen",
}

# ── Experimental grid ─────────────────────────────────────────────────────────
GRID = [
    (T, D, N, C)
    for T in [50, 150, 300]
    for D in [10]
    for N in [2, 5]
    for C in [3, 10]
]

# =============================================================================
#  Helper functions
# =============================================================================

def build_patients_json(schedule, instance):
    """Convert {tid: day_or_None} to patient-level JSON."""
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


def save_figure(points, title, fig_path):
    """Save a single Pareto front as PDF."""
    try:
        pairs   = sorted((p["OT"], p["WL"]) for p in points)
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
    except Exception as e:
        print(f"    [WARN] Figure not saved ({fig_path}): {e}", flush=True)


def save_combined_figure(all_yn, combo_key, fig_path):
    """Save all 5 fronts on one plot."""
    try:
        fig, ax = plt.subplots(figsize=(10, 7))
        for version, points in all_yn.items():
            if not points:
                continue
            pairs   = sorted((p["OT"], p["WL"]) for p in points)
            ot_vals = [pr[0] for pr in pairs]
            wl_vals = [pr[1] for pr in pairs]
            ax.plot(ot_vals, wl_vals, linestyle='-', marker='o',
                    markersize=4, linewidth=1.0,
                    color=COLORS.get(version, 'gray'),
                    label=version, alpha=0.85)
        ax.set_xlabel("OT — Overtime (min)", fontsize=12)
        ax.set_ylabel("WL — Weighted Workload", fontsize=12)
        ax.set_title(f"All fronts — {combo_key}", fontsize=11, pad=10)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, linestyle='--')
        fig.tight_layout()
        fig.savefig(fig_path, format='pdf', bbox_inches='tight')
        plt.close(fig)
    except Exception as e:
        print(f"    [WARN] Combined figure not saved ({fig_path}): {e}", flush=True)


def log(idx, total, T, D, N, C, version, detail):
    tag = f"[V5 | {idx:2d}/{total}] T={T:<3} D={D:<2} N={N:<2} C={C:<2}"
    print(f"{tag}  — {version:<20}  {detail}", flush=True)


# =============================================================================
#  Load existing results.json if present (progressive saving)
# =============================================================================
if os.path.exists(JSON_PATH):
    with open(JSON_PATH) as f:
        all_results = json.load(f)
    print(f"[INFO] Loaded existing results.json ({len(all_results)} combinations already done)")
else:
    all_results = {}

# =============================================================================
#  Main loop
# =============================================================================
total = len(GRID)

for idx, (T, D, N, C) in enumerate(GRID, start=1):
    combo_key     = f"T{T}_D{D}_N{N}_C{C}"
    combo_fig_dir = os.path.join(FIG_DIR, f"T{T}_D10_N{N}_C{C}")
    os.makedirs(combo_fig_dir, exist_ok=True)

    print(f"\n{'─'*72}")
    print(f"  [{idx}/{total}]  {combo_key}  (seed={SEED}  time_limit={TIME_LIMIT}s)")
    print(f"{'─'*72}")

    combo_results  = {}
    all_yn_for_fig = {}   # version → YN, used for combined figure

    for version, generator, runner, pharm_kwargs in VERSIONS:

        # ── 1. Generate instance ──────────────────────────────────────────────
        inst_filename = f"{combo_key}_{version}.json"
        inst_path     = os.path.join(INST_DIR, inst_filename)

        try:
            instance = generator(T, D, N, C, seed=SEED, **pharm_kwargs)
            with open(inst_path, 'w') as f:
                json.dump(instance, f, indent=2)
            log(idx, total, T, D, N, C, version,
                f"instance generated → {inst_filename}")
        except Exception as e:
            msg = str(e)
            log(idx, total, T, D, N, C, version, f"GENERATION ERROR: {msg}")
            print(traceback.format_exc(), flush=True)
            combo_results[version] = {"error": msg}
            continue

        # ── 2. Run hybrid scalarization s=1 then s=0.1, keep richest ─────────
        try:
            t0     = time.time()
            yn_s1  = runner(instance, s=1,   time_limit=TIME_LIMIT, verbose=False)
            yn_s01 = runner(instance, s=0.1, time_limit=TIME_LIMIT, verbose=False)
            cpu    = time.time() - t0

            if len(yn_s1) >= len(yn_s01):
                yn     = yn_s1
                s_used = 1
            else:
                yn     = yn_s01
                s_used = 0.1

            log(idx, total, T, D, N, C, version,
                f"DONE  |YN|={len(yn)}  s_used={s_used}  cpu={cpu:.1f}s")

        except Exception as e:
            msg = str(e)
            log(idx, total, T, D, N, C, version, f"SOLVER ERROR: {msg}")
            print(traceback.format_exc(), flush=True)
            combo_results[version] = {"error": msg}
            continue

        if not yn:
            log(idx, total, T, D, N, C, version, "EMPTY FRONT — skipping")
            combo_results[version] = {"error": "empty front"}
            continue

        # ── 3. Extract max_WL and min_OT anchor points ────────────────────────
        max_wl_point = max(yn, key=lambda p: p["WL"])
        min_ot_point = min(yn, key=lambda p: p["OT"])

        max_wl_schedule = build_patients_json(
            max_wl_point.get("schedule", {}), instance
        )
        min_ot_schedule = build_patients_json(
            min_ot_point.get("schedule", {}), instance
        )

        # ── 4. Save individual figure ─────────────────────────────────────────
        fig_path = os.path.join(combo_fig_dir, f"{version}.pdf")
        save_figure(
            yn,
            f"Pareto Front — {version}\n{combo_key}",
            fig_path
        )

        # ── 5. Accumulate for combined figure + store results ─────────────────
        all_yn_for_fig[version] = yn

        combo_results[version] = {
            "s_used":   s_used,
            "cpu_time": round(cpu, 2),
            "YN": [{"WL": p["WL"], "OT": p["OT"]} for p in yn],
            "max_WL_point": {
                "WL":       max_wl_point["WL"],
                "OT":       max_wl_point["OT"],
                "schedule": max_wl_schedule,
            },
            "min_OT_point": {
                "WL":       min_ot_point["WL"],
                "OT":       min_ot_point["OT"],
                "schedule": min_ot_schedule,
            },
        }

    # ── 6. Save combined figure ───────────────────────────────────────────────
    combined_fig_path = os.path.join(combo_fig_dir, "combined.pdf")
    save_combined_figure(all_yn_for_fig, combo_key, combined_fig_path)
    log(idx, total, T, D, N, C, "combined figure",
        f"saved → {combined_fig_path}")

    # ── 7. Save results.json progressively ───────────────────────────────────
    all_results[combo_key] = combo_results
    with open(JSON_PATH, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"  → results.json updated ({combo_key})", flush=True)


# =============================================================================
#  Done
# =============================================================================
print(f"\n{'='*72}")
print(f"  VOLET 5 DONE — {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  results → {V5_DIR}")
print(f"{'='*72}")

PYEOF

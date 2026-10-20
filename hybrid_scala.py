import time
from collections import deque

import gurobipy as gp
from gurobipy import GRB

from epsilon_constraint import (
    _extract_sets,
    _extract_params,
    _compute_bounds,
    _build_eligible_sets,
    _tighten_overtime,
    _keep_efficient,
)

def _ocp_solve(instance,
               T, F, T_prime, D,
               t, t_prime, first, last, rmin, rmax, succ,
               R, C, N, O_max, w, ed, et, O_star,
               objective,
               lb_wl=None, ub_ot=None,
               lam1=1.0, lam2=1.0,
               s=1,
               time_limit=300, verbose=False):

    m = gp.Model("OCP_chalmet")
    m.setParam("OutputFlag", 1 if verbose else 0)
    m.setParam("TimeLimit",  time_limit)

    x    = {(i, d): m.addVar(vtype=GRB.BINARY, name=f"x_{i}_{d}")
            for i in T for d in ed[i]}
    y    = m.addVars(T, vtype=GRB.BINARY, name="y")
    O_v  = m.addVars(D, lb=0.0, name="O")
    Load = m.addVars(D, lb=0.0, name="Load")

    if objective == "max_WL":
        m.setObjective(
            gp.quicksum(w[d] * Load[d] for d in D),
            GRB.MAXIMIZE
        )
    elif objective == "min_OT":
        m.setObjective(
            gp.quicksum(O_v[d] for d in D),
            GRB.MINIMIZE
        )
    elif objective == "hybrid":
        m.setObjective(
            -lam1 * gp.quicksum(w[d] * Load[d] for d in D)
            + lam2 * gp.quicksum(O_v[d] for d in D),
            GRB.MINIMIZE
        )
        m.addConstr(
            gp.quicksum(w[d] * Load[d] for d in D) >= lb_wl + s,
            name="corner_WL_lb"
        )
        m.addConstr(
            gp.quicksum(O_v[d] for d in D) <= ub_ot - s,
            name="corner_OT_ub"
        )
    else:
        raise ValueError(f"Unknown objective '{objective}'")

    for d in D:
        m.addConstr(
            Load[d] == gp.quicksum(t[i] * x[i, d] for i in et[d]),
            name=f"load_{d}"
        )

    for i in T:
        m.addConstr(
            gp.quicksum(x[i, d] for d in ed[i]) + y[i] == 1,
            name=f"assign_{i}"
        )

    for i in F:
        m.addConstr(
            gp.quicksum(d * x[i, d] for d in ed[i]) >= first[i] * (1 - y[i]),
            name=f"first_min_{i}"
        )
        m.addConstr(
            gp.quicksum(d * x[i, d] for d in ed[i]) <= last[i] * (1 - y[i]),
            name=f"first_max_{i}"
        )

    for i in T_prime:
        j = succ[i]
        m.addConstr(
            gp.quicksum(d * x[j, d] for d in ed[j])
            <= gp.quicksum(d * x[i, d] for d in ed[i]) + rmax[i] * (1 - y[i]),
            name=f"rmax_{i}"
        )
        m.addConstr(
            gp.quicksum(d * x[j, d] for d in ed[j])
            >= gp.quicksum(d * x[i, d] for d in ed[i]) + rmin[i] * (1 - y[i]),
            name=f"rmin_{i}"
        )

    for d in D:
        m.addConstr(Load[d] <= C[d] * (R[d] + O_v[d]), name=f"chairs_{d}")

    for d in D:
        m.addConstr(O_v[d] <= O_star[d], name=f"ot_cap_{d}")

    for d in D:
        m.addConstr(
            gp.quicksum(t_prime[i] * x[i, d] for i in et[d])
            <= N[d] * R[d] + O_v[d] * C[d],
            name=f"nurses_{d}"
        )

    t0 = time.time()
    m.optimize()
    cpu = time.time() - t0

    if m.SolCount == 0:
        return None
        
    schedule = {}
    for i in T:
        if y[i].X > 0.5:
            schedule[i] = None
        else:
            for d in ed[i]:
                if x[i, d].X > 0.5:
                    schedule[i] = d
                    break

    return {
        "WL":       sum(w[d] * Load[d].X for d in D),
        "OT":       sum(O_v[d].X         for d in D),
        "status":   m.Status,
        "cpu_time": cpu,
        "schedule": schedule,
    }


def run_chalmet(instance, s=1, time_limit=300, verbose=False):

    T, F, T_prime, D = _extract_sets(instance)
    t, t_prime, first, last, rmin, rmax, succ, R, C, N, O_max, w = \
        _extract_params(instance)
    lb_t, ub_t = _compute_bounds(T, F, T_prime, D, first, last, rmin, rmax, succ)
    ed, et     = _build_eligible_sets(T, D, lb_t, ub_t)
    O_star     = _tighten_overtime(D, R, O_max, et, t)

    _kw = dict(
        T=T, F=F, T_prime=T_prime, D=D,
        t=t, t_prime=t_prime, first=first, last=last,
        rmin=rmin, rmax=rmax, succ=succ,
        R=R, C=C, N=N, O_max=O_max, w=w,
        ed=ed, et=et, O_star=O_star,
        time_limit=time_limit, verbose=verbose,
    )

    print(f"[Chalmet]  Phase 1: extreme points  (s={s}) …")

    p_A = _ocp_solve(instance, objective="max_WL", s=s, **_kw)
    if p_A is None:
        print("[Chalmet]  Instance infeasible (max WL solve).")
        return []
    print(f"  p_A  max-WL extreme : WL={p_A['WL']:.1f}  OT={p_A['OT']:.1f}")

    p_B = _ocp_solve(instance, objective="min_OT", s=s, **_kw)
    if p_B is None:
        print("[Chalmet]  Instance infeasible (min OT solve).")
        return []
    print(f"  p_B  min-OT extreme : WL={p_B['WL']:.1f}  OT={p_B['OT']:.1f}")

    all_points = [p_A, p_B]

    if p_A["WL"] <= p_B["WL"] + s or p_A["OT"] <= p_B["OT"] + s:
        print("[Chalmet]  Extremes coincide or too close — single-region front.")
        return _keep_efficient(all_points)

    print(f"\n[Chalmet]  Phase 2: rectangle exploration …")

    queue    = deque([(p_A["WL"], p_A["OT"], p_B["WL"], p_B["OT"])])
    n_rect   = 0
    n_found  = 0

    while queue:
        x1_wl, x1_ot, x2_wl, x2_ot = queue.popleft()
        n_rect += 1

        lam1 = x1_ot - x2_ot
        lam2 = x1_wl - x2_wl
        wl_lb = x2_wl
        ot_ub = x1_ot

        print(f"  rect {n_rect:3d} : WL≥{wl_lb:.0f}+{s}  OT≤{ot_ub:.0f}-{s}"
              f"  λ=({lam1:.1f},{lam2:.1f}) … ", end="", flush=True)

        result = _ocp_solve(
            instance, objective="hybrid",
            lb_wl=wl_lb, ub_ot=ot_ub,
            lam1=lam1, lam2=lam2, s=s,
            **_kw
        )

        if result is None:
            print("infeasible (empty).")
        else:
            wl_new = result["WL"]
            ot_new = result["OT"]
            n_found += 1
            print(f"WL={wl_new:.1f}  OT={ot_new:.1f}  "
                  f"t={result['cpu_time']:.2f}s")

            all_points.append(result)

            if wl_new + s < x1_wl - 0.5:
                queue.append((x1_wl, x1_ot, wl_new, ot_new))

            if ot_new - s > x2_ot + 0.5:
                queue.append((wl_new, ot_new, x2_wl, x2_ot))

    efficient = _keep_efficient(all_points)

    print(f"\n[Chalmet]  Done.  "
          f"{n_rect} rectangles explored  ·  "
          f"{n_found} new points found  ·  "
          f"{len(efficient)} efficient solutions on Pareto front.")

    cpu_times = [p["cpu_time"] for p in all_points]
    total_cpu = sum(cpu_times)
    avg_cpu   = total_cpu / len(cpu_times) if cpu_times else 0.0
    print(f"[Chalmet]  CPU time : total={total_cpu:.2f}s  "
          f"avg/solve={avg_cpu:.2f}s  "
          f"min={min(cpu_times):.2f}s  max={max(cpu_times):.2f}s")

    return efficient

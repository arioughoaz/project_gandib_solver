import time
import gurobipy as gp
from gurobipy import GRB


def _extract_sets(instance):

    T, F, T_prime = [], [], []
    for patient in instance["patients"]:
        for tr in patient["treatments"]:
            tid = tr["treatment_id"]
            T.append(tid)
            if tr["is_first"]:
                F.append(tid)
            if not tr["is_last"]:
                T_prime.append(tid)

    D = list(range(1, instance["parameters"]["D"] + 1))
    return T, F, T_prime, D


def _extract_params(instance):

    t, t_prime, first, last, rmin, rmax, succ = {}, {}, {}, {}, {}, {}, {}
    for patient in instance["patients"]:
        for tr in patient["treatments"]:
            tid          = tr["treatment_id"]
            t[tid]       = tr["duration"]
            t_prime[tid] = tr["nurse_workload"]
            if tr["is_first"]:
                first[tid] = tr["first_day"]
                last[tid]  = tr["last_day"]
            if not tr["is_last"]:
                rmin[tid] = tr["rmin"]
                rmax[tid] = tr["rmax"]
                succ[tid] = tr["successor_id"]

    R, C, N, O_max, w = {}, {}, {}, {}, {}
    for d_str, data in instance["days"].items():
        d        = int(d_str)
        R[d]     = data["R"]
        C[d]     = data["C"]
        N[d]     = data["N"]
        O_max[d] = data["O_max"]
        w[d]     = data["w"]

    return t, t_prime, first, last, rmin, rmax, succ, R, C, N, O_max, w


def _compute_bounds(T, F, T_prime, D, first, last, rmin, rmax, succ):
    D_max = max(D)
    lb, ub = {}, {}

    for i in F:
        lb[i] = first[i]
        ub[i] = last[i]

    for i in T_prime:
        j     = succ[i]
        lb[j] = lb[i] + rmin[i] + 1
        ub[j] = ub[i] + rmax[i]

    for i in T:
        lb[i] = max(1,     lb[i])
        ub[i] = min(D_max, ub[i])

    return lb, ub


def _build_eligible_sets(T, D, lb, ub):
    ed = {i: [d for d in D if lb[i] <= d <= ub[i]] for i in T}
    et = {d: [i for i in T if lb[i] <= d <= ub[i]] for d in D}
    return ed, et


def _tighten_overtime(D, R, O_max, et, t):
    O_star = {}
    for d in D:
        max_load  = sum(t[i] for i in et[d])
        O_star[d] = min(max(0, max_load - R[d]), O_max[d])
    return O_star


def _solve_subproblem(instance, eps_ot, T, F, T_prime, D,
                      t, t_prime, first, last, rmin, rmax, succ,
                      R, C, N, O_max, w,
                      ed, et, O_star,
                      time_limit, verbose):

    model = gp.Model("OCP_eps")
    model.setParam("OutputFlag", 1 if verbose else 0)
    model.setParam("TimeLimit",  time_limit/2)

    x = {
        (i, d): model.addVar(vtype=GRB.BINARY, name=f"x_{i}_{d}")
        for i in T for d in ed[i]
    }

    y = model.addVars(T, vtype=GRB.BINARY, name="y")

    O = model.addVars(D, lb=0.0, name="O")

    Load = model.addVars(D, lb=0.0, name="Load")

    model.setObjective(
        gp.quicksum(w[d] * Load[d] for d in D),
        GRB.MAXIMIZE
    )

    model.addConstr(
        gp.quicksum(O[d] for d in D) <= eps_ot,
        name="epsilon_OT"
    )

    for d in D:
        model.addConstr(
            Load[d] == gp.quicksum(t[i] * x[i, d] for i in et[d]),
            name=f"load_{d}"
        )

    for i in T:
        model.addConstr(
            gp.quicksum(x[i, d] for d in ed[i]) + y[i] == 1,
            name=f"assign_{i}"
        )

    for i in F:
        model.addConstr(
            gp.quicksum(d * x[i, d] for d in ed[i]) >= first[i] * (1 - y[i]),
            name=f"first_min_{i}"
        )

    for i in F:
        model.addConstr(
            gp.quicksum(d * x[i, d] for d in ed[i]) <= last[i] * (1 - y[i]),
            name=f"first_max_{i}"
        )

    for i in T_prime:
        j = succ[i]
        model.addConstr(
            gp.quicksum(d * x[j, d] for d in ed[j])
            <= gp.quicksum(d * x[i, d] for d in ed[i]) + rmax[i] * (1 - y[i]),
            name=f"rmax_{i}"
        )

    for i in T_prime:
        j = succ[i]
        model.addConstr(
            gp.quicksum(d * x[j, d] for d in ed[j])
            >= gp.quicksum(d * x[i, d] for d in ed[i]) + rmin[i] * (1 - y[i]),
            name=f"rmin_{i}"
        )

    for d in D:
        model.addConstr(
            Load[d] <= C[d] * (R[d] + O[d]),
            name=f"chairs_{d}"
        )

    for d in D:
        model.addConstr(O[d] <= O_star[d], name=f"ot_cap_{d}")

    for d in D:
        model.addConstr(
            gp.quicksum(t_prime[i] * x[i, d] for i in et[d])
            <= N[d] * R[d] + O[d] * C[d],
            name=f"nurses_{d}"
        )

    t0 = time.time()
    model.optimize()
    cpu = time.time() - t0
    

    if model.SolCount == 0:
        return None

    wl_star = sum(w[d] * Load[d].X for d in D)

    model2 = gp.Model("OCP_eps_phase2")
    model2.setParam("OutputFlag", 0)
    model2.setParam("TimeLimit", time_limit/2)

    x2    = {(i, d): model2.addVar(vtype=GRB.BINARY) for i in T for d in ed[i]}
    y2    = model2.addVars(T, vtype=GRB.BINARY)
    O2    = model2.addVars(D, lb=0.0)
    Load2 = model2.addVars(D, lb=0.0)

    model2.setObjective(gp.quicksum(O2[d] for d in D), GRB.MINIMIZE)

    model2.addConstr(
        gp.quicksum(w[d] * Load2[d] for d in D) >= wl_star,
        name="fix_WL"
    )

    model2.addConstr(gp.quicksum(O2[d] for d in D) <= eps_ot, name="epsilon_OT")

    for d in D:
        model2.addConstr(Load2[d] == gp.quicksum(t[i] * x2[i, d] for i in et[d]))
    for i in T:
        model2.addConstr(gp.quicksum(x2[i, d] for d in ed[i]) + y2[i] == 1)
    for i in F:
        model2.addConstr(gp.quicksum(d * x2[i, d] for d in ed[i]) >= first[i] * (1 - y2[i]))
        model2.addConstr(gp.quicksum(d * x2[i, d] for d in ed[i]) <= last[i]  * (1 - y2[i]))
    for i in T_prime:
        j = succ[i]
        model2.addConstr(gp.quicksum(d * x2[j, d] for d in ed[j]) <= gp.quicksum(d * x2[i, d] for d in ed[i]) + rmax[i] * (1 - y2[i]))
        model2.addConstr(gp.quicksum(d * x2[j, d] for d in ed[j]) >= gp.quicksum(d * x2[i, d] for d in ed[i]) + rmin[i] * (1 - y2[i]))
    for d in D:
        model2.addConstr(Load2[d] <= C[d] * (R[d] + O2[d]))
    for d in D:
        model2.addConstr(O2[d] <= O_star[d])
    for d in D:
        model2.addConstr(gp.quicksum(t_prime[i] * x2[i, d] for i in et[d]) <= N[d] * R[d] + O2[d] * C[d])

    model2.optimize()
    

    ot_star = sum(O2[d].X for d in D) if model2.SolCount > 0 else sum(O[d].X for d in D)
    
    schedule = {}
    if model2.SolCount > 0:
        for i in T:
            if y2[i].X > 0.5:
                schedule[i] = None
            else:
                for d in ed[i]:
                    if x2[i, d].X > 0.5:
                        schedule[i] = d
                        break

    return {
        "WL":       wl_star,
        "OT":       ot_star,
        "status":   model.Status,
        "cpu_time": time.time() - t0,
        "epsilon":  eps_ot,
        "schedule": schedule,
    }


def _keep_efficient(points):
    efficient = []
    for p in points:
        dominated = any(
            q["WL"] >= p["WL"] and q["OT"] <= p["OT"]
            and (q["WL"] > p["WL"] or q["OT"] < p["OT"])
            for q in points if q is not p
        )
        if not dominated:
            efficient.append(p)

    efficient.sort(key=lambda p: p["OT"])
    return efficient


def run_epsilon_constraint(instance, s=1, time_limit=300, verbose=False):

    T, F, T_prime, D = _extract_sets(instance)
    t, t_prime, first, last, rmin, rmax, succ, R, C, N, O_max, w = \
        _extract_params(instance)

    lb, ub     = _compute_bounds(T, F, T_prime, D, first, last, rmin, rmax, succ)

    ed, et     = _build_eligible_sets(T, D, lb, ub)

    O_star     = _tighten_overtime(D, R, O_max, et, t)

    ot_max_possible = sum(O_max[d] for d in D)

    print(f"[ε-constraint]  s = {s} min | solving first point (unconstrained WL)…")
    result0 = _solve_subproblem(
        instance, ot_max_possible,
        T, F, T_prime, D,
        t, t_prime, first, last, rmin, rmax, succ,
        R, C, N, O_max, w,
        ed, et, O_star,
        time_limit, verbose
    )

    if result0 is None:
        print("[ε-constraint]  instance infeasible at k=0, aborting.")
        return []

    all_points = [result0]
    print(f"  k=0 : WL={result0['WL']:.1f}  OT={result0['OT']:.1f}  "
          f"t={result0['cpu_time']:.2f}s")

    eps = result0["OT"] - s

    k = 1
    while eps >= 0:

        print(f"  k={k} : ε={eps:.1f} min … ", end="", flush=True)

        result = _solve_subproblem(
            instance, eps,
            T, F, T_prime, D,
            t, t_prime, first, last, rmin, rmax, succ,
            R, C, N, O_max, w,
            ed, et, O_star,
            time_limit, verbose
        )

        if result is None:
            print("infeasible — front complete.")
            break

        print(f"WL={result['WL']:.1f}  OT={result['OT']:.1f}  "
              f"t={result['cpu_time']:.2f}s")

        all_points.append(result)

        eps = result["OT"] - s
        k  += 1

    efficient = _keep_efficient(all_points)

    print(f"\n[ε-constraint]  {len(all_points)} total points → "
          f"{len(efficient)} efficient solutions on Pareto front.")

    cpu_times = [p["cpu_time"] for p in all_points]
    total_cpu = sum(cpu_times)
    avg_cpu   = total_cpu / len(cpu_times) if cpu_times else 0.0
    print(f"[ε-constraint]  CPU time : total={total_cpu:.2f}s  "
          f"avg/solve={avg_cpu:.2f}s  "
          f"min={min(cpu_times):.2f}s  max={max(cpu_times):.2f}s")

    return efficient

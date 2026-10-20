import time
import gurobipy as gp
from gurobipy import GRB


def _extract_sets(instance):
    T       = []   
    F       = []  
    T_prime = []
    
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
    t       = {}   
    t_prime = {}   
    first   = {}   
    last    = {}   
    rmin    = {}
    rmax    = {}
    succ    = {}

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

    R     = {}  
    C     = {}   
    N     = {}   
    O_max = {}   
    w     = {}  

    for d_str, data in instance["days"].items():
        d        = int(d_str)
        R[d]     = data["R"]
        C[d]     = data["C"]
        N[d]     = data["N"]
        O_max[d] = data["O_max"]
        w[d]     = data["w"]

    eps_L = instance["parameters"]["eps_L"]

    return t, t_prime, first, last, rmin, rmax, succ, R, C, N, O_max, w, eps_L


def solve_base_model(instance, time_limit=1800, verbose=False):

    T, F, T_prime, D = _extract_sets(instance)
    t, t_prime, first, last, rmin, rmax, succ, R, C, N, O_max, w, eps_L = _extract_params(instance)

    model = gp.Model("OCP_Base")
    model.setParam("OutputFlag", 1 if verbose else 0)
    model.setParam("TimeLimit",  time_limit)


    x = model.addVars(T, D, vtype=GRB.BINARY, name="x")   
    y = model.addVars(T,    vtype=GRB.BINARY, name="y")   
    O = model.addVars(D,    lb=0.0,           name="O")


    model.setObjective(
        gp.quicksum(w[d] * t[i] * x[i, d] for i in T for d in D)
        - eps_L * gp.quicksum(O[d] for d in D),
        GRB.MAXIMIZE
    )


    for i in T:
        model.addConstr(
            gp.quicksum(x[i, d] for d in D) + y[i] == 1,
            name=f"assign_{i}"
        )

    for i in F:
        model.addConstr(
            gp.quicksum(d * x[i, d] for d in D) >= first[i] * (1 - y[i]),
            name=f"first_min_{i}"
        )

    for i in F:
        model.addConstr(
            gp.quicksum(d * x[i, d] for d in D) <= last[i] * (1 - y[i]),
            name=f"first_max_{i}"
        )

    for i in T_prime:
        j = succ[i]
        model.addConstr(
            gp.quicksum(d * x[j, d] for d in D)
            <= gp.quicksum(d * x[i, d] for d in D) + rmax[i] * (1 - y[i]),
            name=f"rmax_{i}"
        )


    for i in T_prime:
        j = succ[i]
        model.addConstr(
            gp.quicksum(d * x[j, d] for d in D)
            >= gp.quicksum(d * x[i, d] for d in D) + rmin[i] * (1 - y[i]),
            name=f"rmin_{i}"
        )

    for d in D:
        model.addConstr(
            gp.quicksum(t[i] * x[i, d] for i in T) <= C[d] * (R[d] + O[d]),
            name=f"chairs_{d}"
        )

    for d in D:
        model.addConstr(O[d] <= O_max[d], name=f"overtime_cap_{d}")

    for d in D:
        model.addConstr(
            gp.quicksum(t_prime[i] * x[i, d] for i in T) <= N[d] * R[d] + O[d] * C[d],
            name=f"nurses_{d}"
        )

    start_time = time.time()
    model.optimize()
    cpu_time = time.time() - start_time

    result = {
        "status":    model.Status,
        "cpu_time":  cpu_time,
        "objective": None,
        "WL":        None,
        "OT":        None,
        "x":         {},
        "y":         {},
        "O":         {},
        "n_vars":    model.NumVars,
        "n_constrs": model.NumConstrs,
        "bb_nodes":  int(model.NodeCount),   # B&B nodes explored
    }

    if model.Status in (GRB.OPTIMAL, GRB.TIME_LIMIT) and model.SolCount > 0:
        result["objective"] = model.ObjVal
        result["WL"] = sum(w[d] * t[i] * x[i, d].X for i in T for d in D)
        result["OT"] = sum(O[d].X for d in D)
        result["x"]  = {(i, d): round(x[i, d].X) for i in T for d in D}
        result["y"]  = {i: round(y[i].X) for i in T}
        result["O"]  = {d: O[d].X for d in D}

    return result

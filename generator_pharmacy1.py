import json
import random
import os




CLASS_PROPORTIONS = [0.2696, 0.0785, 0.3333, 0.3186]   # classes 1-4
INFUSION_RANGES   = [(16, 44), (29, 80), (74, 132), (125, 217)]  # minutes
R       = 480   
O_MAX   = 120   
T_PRIME = 15    

def _sample_class(rng):

    return rng.choices([1, 2, 3, 4], weights=CLASS_PROPORTIONS, k=1)[0]


def _generate_patient(patient_id, treatment_id_start, D, rng):
    
    cls       = _sample_class(rng)
    low, high = INFUSION_RANGES[cls - 1]
    
    rmin1 = rng.randint(1, 2)  
    rmax1 = rng.randint(3, 4)
    rmin2 = rng.randint(1, 2)
    rmax2 = rng.randint(3, 4)
    
    first_i = rng.randint(1, D - rmin1 - rmin2)
    last_i  = rng.randint(first_i + rmin1, D - rmin2)
    
    treatments = []
    tid = treatment_id_start

    for position in range(3):
        infusion = rng.randint(low, high)
        is_first = (position == 0)
        is_last  = (position == 2)

        tr = {
            "treatment_id":   tid,
            "is_first":       is_first,
            "is_last":        is_last,
            "duration":       T_PRIME + infusion,   
            "nurse_workload": T_PRIME,               
        }

        if is_first:
            tr["first_day"] = first_i
            tr["last_day"]  = last_i

        if not is_last:
            tr["rmin"] = rmin1 if position == 0 else rmin2
            tr["rmax"] = rmax1 if position == 0 else rmax2
            tr["successor_id"] = tid + 1

        treatments.append(tr)
        tid += 1

    return {"patient_id": patient_id, "class": cls, "treatments": treatments}


def _to_range(value):
    return (value, value) if isinstance(value, int) else tuple(value)


def _generate_days(D, N_range, C_range, Pd_range, rng):

    days = {}
    for d in range(1, D + 1):
        day = {
            "R":     R,
            "C":     rng.randint(*C_range),
            "N":     rng.randint(*N_range),
            "O_max": O_MAX,
            "w":     D + 1 - d,
        }
        if Pd_range is not None:
            day["P_d"] = rng.randint(*Pd_range)
        days[str(d)] = day
    return days


def generate_instance(T, D, N, C, Pd=None, seed=None):
    rng      = random.Random(seed)
    N_range  = _to_range(N)
    C_range  = _to_range(C)
    Pd_range = tuple(Pd) if Pd is not None else None
    P        = T // 3

    patients = []
    tid = 1
    for pid in range(1, P + 1):
        patients.append(_generate_patient(pid, tid, D, rng))
        tid += 3

    days  = _generate_days(D, N_range, C_range, Pd_range, rng)
    eps_L = 1.0 / (D * O_MAX)

    params = {
        "T":     T,
        "D":     D,
        "N":     list(N_range),
        "C":     list(C_range),
        "P":     P,
        "eps_L": eps_L,
    }
    if Pd_range is not None:
        params["Pd"] = list(Pd_range)

    return {
        "parameters": params,
        "days":       days,
        "patients":   patients,
    }


def generate_batch(T, D, N, C, n_instances, output_dir, Pd=None, base_seed=0):

    os.makedirs(output_dir, exist_ok=True)
    N_range = _to_range(N)
    C_range = _to_range(C)

    n_tag  = str(N_range[0]) if N_range[0] == N_range[1] else f"{N_range[0]}-{N_range[1]}"
    c_tag  = str(C_range[0]) if C_range[0] == C_range[1] else f"{C_range[0]}-{C_range[1]}"
    pd_tag = f"_Pd{Pd[0]}-{Pd[1]}" if Pd is not None else ""

    for k in range(1, n_instances + 1):
        instance = generate_instance(T, D, N, C, Pd=Pd, seed=base_seed + k)
        filename = f"T{T}_D{D}_N{n_tag}_C{c_tag}{pd_tag}_inst{k:02d}.json"
        with open(os.path.join(output_dir, filename), "w") as f:
            json.dump(instance, f, indent=2)

    print(f"Generated {n_instances} instances → {output_dir}")

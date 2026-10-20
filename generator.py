import json
import random
import os


# ── Fixed clinical/operational constants 

CLASS_PROPORTIONS = [0.2696, 0.0785, 0.3333, 0.3186]   # classes 1-4
INFUSION_RANGES   = [(16, 44), (29, 80), (74, 132), (125, 217)]  # minutes
R       = 480   # regular working time per day (min)
O_MAX   = 120   # maximum overtime per day (min)
T_PRIME = 15    # nurse active workload per treatment (premedication, min)


# ── Private helpers ──────────────────────────────────────────────────────────

def _sample_class(rng):
    """Draw a patient class (1-4) according to empirical proportions."""
    return rng.choices([1, 2, 3, 4], weights=CLASS_PROPORTIONS, k=1)[0]


def _generate_patient(patient_id, treatment_id_start, D, rng):
    """
    Build one patient with exactly 3 consecutive treatments.

    Admission window [first_day, last_day] constrains the solver for the
    first treatment only.  Treatments that cannot fit within the horizon are
    handled by the skip variable y_i in the model — no feasibility check here.
    Each inter-treatment interval pair draws its own rmin/rmax independently.
    """
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
            "duration":       T_PRIME + infusion,   # t_i = t'_i + infusion
            "nurse_workload": T_PRIME,               # t'_i fixed
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
    """
    Normalise a resource specification to a (min, max) tuple.
      int  → (value, value)   fixed — same every day
      tuple → as-is           variable — drawn per day from [min, max]
    """
    return (value, value) if isinstance(value, int) else tuple(value)


def _generate_days(D, N_range, C_range, rng):
    """
    Build the day dictionary.
    With a fixed range (x, x) every day gets the same value.
    With a wider range (a, b) each day draws independently.
    Day weights decrease linearly: earlier days are preferred (w_d = D+1-d).
    """
    days = {}
    for d in range(1, D + 1):
        days[str(d)] = {
            "R":     R,
            "C":     rng.randint(*C_range),
            "N":     rng.randint(*N_range),
            "O_max": O_MAX,
            "w":     D + 1 - d,
        }
    return days


# ── Public API ───────────────────────────────────────────────────────────────

def generate_instance(T, D, N, C, seed=None):
    """
    Generate one problem instance.

    Parameters
    ----------
    T    : int            — total number of treatments  (P = T // 3 patients)
    D    : int            — planning horizon (days)
    N    : int or (a, b)  — nurses per day; int → fixed, tuple → drawn in [a,b]
    C    : int or (a, b)  — chairs per day; int → fixed, tuple → drawn in [a,b]
    seed : int or None    — RNG seed for reproducibility

    Returns
    -------
    dict with keys: "parameters", "days", "patients"
    """
    rng     = random.Random(seed)
    N_range = _to_range(N)
    C_range = _to_range(C)
    P       = T // 3

    patients = []
    tid = 1
    for pid in range(1, P + 1):
        patients.append(_generate_patient(pid, tid, D, rng))
        tid += 3

    days  = _generate_days(D, N_range, C_range, rng)
    eps_L = 1.0 / (D * O_MAX)

    return {
        "parameters": {
            "T":     T,
            "D":     D,
            "N":     list(N_range),   # [n, n] or [a, b]
            "C":     list(C_range),   # [c, c] or [a, b]
            "P":     P,
            "eps_L": eps_L,
        },
        "days":     days,
        "patients": patients,
    }


def generate_batch(T, D, N, C, n_instances, output_dir, base_seed=0):
    """
    Generate n_instances instances and write each to a JSON file.

    File naming:
      fixed    → T75_D6_N2_C5_inst01.json
      variable → T75_D6_N2-3_C4-6_inst01.json
    """
    os.makedirs(output_dir, exist_ok=True)
    N_range = _to_range(N)
    C_range = _to_range(C)

    n_tag = str(N_range[0]) if N_range[0] == N_range[1] else f"{N_range[0]}-{N_range[1]}"
    c_tag = str(C_range[0]) if C_range[0] == C_range[1] else f"{C_range[0]}-{C_range[1]}"

    for k in range(1, n_instances + 1):
        instance = generate_instance(T, D, N, C, seed=base_seed + k)
        filename = f"T{T}_D{D}_N{n_tag}_C{c_tag}_inst{k:02d}.json"
        with open(os.path.join(output_dir, filename), "w") as f:
            json.dump(instance, f, indent=2)

    print(f"Generated {n_instances} instances → {output_dir}")

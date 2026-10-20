import time


SLOTS = [
    {"start":   0, "end":  240}, 
    {"start": 300, "end":  540},
]


class DayState:

    def __init__(self, n_chairs, R, O_max):
        self.n_chairs      = n_chairs
        self.R             = R
        self.O_max         = O_max
        self.chair_free    = [0] * n_chairs
        self.overtime_used = 0.0

    def try_assign(self, duration):
        end_of_day = self.R + self.O_max

        best = None

        for slot in SLOTS:
            for chair_idx in range(self.n_chairs):
                start  = max(self.chair_free[chair_idx], slot["start"])
                finish = start + duration

                if finish > end_of_day:
                    continue

                ot = max(0.0, finish - self.R)
                if self.overtime_used + ot > self.O_max:
                    continue

                if start >= 240 and start < 300:
                    start  = 300
                    finish = start + duration
                    if finish > end_of_day:
                        continue
                    ot = max(0.0, finish - self.R)
                    if self.overtime_used + ot > self.O_max:
                        continue

                if best is None or start < best[0]:
                    best = (start, chair_idx, ot)

        if best is None:
            return False

        start_time, chair_idx, ot = best
        self.chair_free[chair_idx] = start_time + duration
        self.overtime_used        += ot
        return True


def run_baseline(instance):
    t0 = time.time()

    params = instance["parameters"]
    D_max  = params["D"]
    D      = list(range(1, D_max + 1))

    # Day parameters
    R     = {int(d): instance["days"][d]["R"]     for d in instance["days"]}
    C     = {int(d): instance["days"][d]["C"]     for d in instance["days"]}
    O_max = {int(d): instance["days"][d]["O_max"] for d in instance["days"]}
    w     = {int(d): instance["days"][d]["w"]     for d in instance["days"]}

    treatments = {}
    for patient in instance["patients"]:
        for tr in patient["treatments"]:
            treatments[tr["treatment_id"]] = tr

    ready = {}
    for patient in instance["patients"]:
        for tr in patient["treatments"]:
            if tr["is_first"]:
                ready[tr["treatment_id"]] = {
                    "lo": tr["first_day"],
                    "hi": tr["last_day"],
                }

    x_assign = {}   
    y_skip   = {}

    day_state = {d: DayState(C[d], R[d], O_max[d]) for d in D}

    for d in D:

        eligible = [
            tid for tid, window in ready.items()
            if window["lo"] <= d <= window["hi"]
        ]

        eligible.sort(key=lambda tid: treatments[tid]["duration"], reverse=True)

        for tid in eligible:
            duration = treatments[tid]["duration"]
            assigned = day_state[d].try_assign(duration)

            if assigned:
                x_assign[tid] = d
                y_skip[tid]   = 0
                ready.pop(tid)

                tr = treatments[tid]
                if not tr["is_last"]:
                    j = tr["successor_id"]
                    ready[j] = {
                        "lo": d + tr["rmin"],
                        "hi": d + tr["rmax"],
                    }

        expired = [tid for tid, window in ready.items() if window["hi"] <= d]
        for tid in expired:
            _cascade_skip(tid, treatments, ready, x_assign, y_skip)

    for tid in list(ready.keys()):
        _cascade_skip(tid, treatments, ready, x_assign, y_skip)

    O_result = {d: day_state[d].overtime_used for d in D}

    WL = sum(
        w[x_assign[tid]] * treatments[tid]["duration"]
        for tid in x_assign
        if x_assign[tid] is not None
    )
    OT = sum(O_result.values())

    x_dict = {}
    for tid in treatments:
        day = x_assign.get(tid)
        for d in D:
            x_dict[(tid, d)] = 1 if day == d else 0

    cpu_time = time.time() - t0

    return {
        "status":    "baseline",
        "cpu_time":  cpu_time,
        "objective": None,
        "WL":        WL,
        "OT":        OT,
        "x":         x_dict,
        "y":         y_skip,
        "O":         O_result,
        "n_vars":    None,
        "n_constrs": None,
    }


def _cascade_skip(tid, treatments, ready, x_assign, y_skip):
    if tid in y_skip:
        return

    x_assign[tid] = None
    y_skip[tid]   = 1
    ready.pop(tid, None)

    tr = treatments[tid]
    if not tr["is_last"]:
        j = tr["successor_id"]
        _cascade_skip(j, treatments, ready, x_assign, y_skip)

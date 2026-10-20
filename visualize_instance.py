import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np



CLASS_COLORS = {1: "#4C72B0", 2: "#DD8452", 3: "#55A868", 4: "#C44E52"}
CLASS_LABELS = {1: "Class 1", 2: "Class 2", 3: "Class 3", 4: "Class 4"}

R     = 480   
T_PRI = 15    

def visualize_instance(instance, save_path=None):
    params   = instance["parameters"]
    days     = instance["days"]
    patients = instance["patients"]

    T, D, P = params["T"], params["D"], params["P"]
    N_range  = params["N"]   # [n, n] or [a, b]
    C_range  = params["C"]

    day_ids = list(range(1, D + 1))


    N_vals = [days[str(d)]["N"] for d in day_ids]
    C_vals = [days[str(d)]["C"] for d in day_ids]

    MEAN_INFUSION = {1: 30, 2: 54, 3: 103, 4: 171}   
    max_demand_min = np.zeros(D)
    for pat in patients:
        cls      = pat["class"]
        dur      = T_PRI + MEAN_INFUSION[cls]
        first_tr = pat["treatments"][0]
        fd = first_tr.get("first_day", 1)
        ld = first_tr.get("last_day",  D)
        for d in range(fd, ld + 1):
            max_demand_min[d - 1] += dur


    reg_capacity_min = [C_vals[d - 1] * R for d in day_ids]


    max_patients_day = np.zeros(D, dtype=int)
    for pat in patients:
        first_tr = pat["treatments"][0]
        fd = first_tr.get("first_day", 1)
        ld = first_tr.get("last_day",  D)
        for d in range(fd, ld + 1):
            max_patients_day[d - 1] += 1

    PAGE_LIMIT   = 10.0 
    panel1_h     = max(3, P * 0.28)
    panel_h      = 2.8
    fig_w        = max(10, D * 1.1)
    other_h      = 3 * panel_h + 1.0 

    split = (panel1_h + other_h) > PAGE_LIMIT

    if not split:
        total_h = panel1_h + other_h + 1.5
        fig  = plt.figure(figsize=(fig_w, total_h))
        gs   = fig.add_gridspec(4, 1,
                                height_ratios=[panel1_h, panel_h, panel_h, panel_h],
                                hspace=0.65)
        axes = [fig.add_subplot(gs[i]) for i in range(4)]
        fig2 = None
    else:
        fig  = plt.figure(figsize=(fig_w, panel1_h + 1.5)) 
        gs   = fig.add_gridspec(1, 1)
        ax0  = fig.add_subplot(gs[0])

        fig2 = plt.figure(figsize=(fig_w, other_h + 1.5))   
        gs2  = fig2.add_gridspec(3, 1,height_ratios=[panel_h, panel_h, panel_h],hspace=0.65)
        
        axes = [ax0,
                fig2.add_subplot(gs2[0]),
                fig2.add_subplot(gs2[1]),
                fig2.add_subplot(gs2[2])]

    n_str = str(N_range[0]) if N_range[0] == N_range[1] else f"{N_range[0]}-{N_range[1]}"
    c_str = str(C_range[0]) if C_range[0] == C_range[1] else f"{C_range[0]}-{C_range[1]}"
    title_str = f"Instance  T={T}  D={D}  N={n_str}  C={c_str}  —  {P} patients"
    fig.suptitle(title_str + (" (page 1/2)" if split else ""),
                 fontsize=13, fontweight="bold")
    if split:
        fig2.suptitle(title_str + " (page 2/2)", fontsize=13, fontweight="bold")


    ax1 = axes[0]
    for idx, pat in enumerate(patients):
        cls      = pat["class"]
        first_tr = pat["treatments"][0]
        fd = first_tr.get("first_day", 1)
        ld = first_tr.get("last_day",  D)
        color = CLASS_COLORS[cls]
        # admission window bar
        ax1.barh(idx, ld - fd + 1, left=fd - 0.5, height=0.6,
                 color=color, alpha=0.75, edgecolor="white", linewidth=0.4)

    ax1.set_xlim(0.5, D + 0.5)
    ax1.set_ylim(-0.5, P - 0.5)
    ax1.set_yticks(range(P))
    ax1.set_yticklabels([f"P{p['patient_id']}" for p in patients], fontsize=6)
    ax1.set_xticks(day_ids)
    ax1.set_xlabel("Day", fontsize=9)
    ax1.set_title("Patient admission windows for treatment 1  (colour = class)", fontsize=9)
    ax1.invert_yaxis()
    ax1.grid(axis="x", linestyle="--", alpha=0.4)

    # legend for classes present
    classes_present = sorted({p["class"] for p in patients})
    legend_patches = [mpatches.Patch(color=CLASS_COLORS[c], label=CLASS_LABELS[c])
                      for c in classes_present]
    ax1.legend(handles=legend_patches, loc="lower right", fontsize=7, framealpha=0.7)

    ax2 = axes[1]
    x     = np.array(day_ids)
    width = 0.35
    ax2.bar(x - width/2, N_vals, width, label="Nurses (N)", color="#4C72B0", alpha=0.8)
    ax2.bar(x + width/2, C_vals, width, label="Chairs (C)", color="#55A868", alpha=0.8)
    ax2.set_xlim(0.5, D + 0.5)
    ax2.set_xticks(day_ids)
    ax2.set_xlabel("Day", fontsize=9)
    ax2.set_ylabel("Count", fontsize=9)
    ax2.set_title("Resources per day", fontsize=9)
    ax2.legend(fontsize=8)
    ax2.grid(axis="y", linestyle="--", alpha=0.4)

    ax3 = axes[2]
    ax3.bar(x, max_demand_min, width=0.6, label="Max possible demand (min)",
            color="#C44E52", alpha=0.75, edgecolor="#a03030", linewidth=0.5)
    ax3.plot(x, reg_capacity_min, marker="o", color="#2196F3", linewidth=2,
             markersize=5, label=f"Regular capacity = C × {R} min")
    ax3.set_xlim(0.5, D + 0.5)
    ax3.set_xticks(day_ids)
    ax3.set_xlabel("Day", fontsize=9)
    ax3.set_ylabel("Minutes", fontsize=9)
    ax3.set_title("Time pressure: max possible demand vs regular capacity (minutes)", fontsize=9)
    ax3.legend(fontsize=8)
    ax3.grid(axis="y", linestyle="--", alpha=0.4)

    ax4 = axes[3]
    ax4.bar(x, max_patients_day, width=0.6, label="Max possible patients on day",
            color="#FF9800", alpha=0.75, edgecolor="#e65100", linewidth=0.5)
    ax4.plot(x, C_vals, marker="s", color="#4CAF50", linewidth=2,
             markersize=5, label="Available chairs (C)")
    ax4.set_xlim(0.5, D + 0.5)
    ax4.set_xticks(day_ids)
    ax4.set_xlabel("Day", fontsize=9)
    ax4.set_ylabel("Count", fontsize=9)
    ax4.set_title("Chair pressure: max possible patients vs available chairs", fontsize=9)
    ax4.legend(fontsize=8)
    ax4.grid(axis="y", linestyle="--", alpha=0.4)

    fig.subplots_adjust(top=0.95, bottom=0.05)
    if split:
        fig2.subplots_adjust(top=0.95, bottom=0.05)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
        if split:
            base, ext = save_path.rsplit(".", 1)
            path2 = f"{base}_p2.{ext}"
            fig2.savefig(path2, dpi=150, bbox_inches="tight")
            print(f"Saved → {path2}")
    else:
        plt.show()

    return (fig, fig2) if split else fig


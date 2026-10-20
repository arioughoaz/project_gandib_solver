import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np


def plot_pareto_front(front, title="Pareto Front — OCP bi-objective", save_path=None):

    if not front:
        print("Empty front — nothing to plot.")
        return

    pts = sorted(front, key=lambda p: p["OT"])
    ot  = np.array([p["OT"] for p in pts])
    wl  = np.array([p["WL"] for p in pts])
    n   = len(pts)


    fig, ax = plt.subplots(figsize=(8, 5.5))
    fig.patch.set_facecolor("#F9F9F9")
    ax.set_facecolor("#F9F9F9")

    ax.plot(ot, wl, color="#BDBDBD", linewidth=1.5, zorder=1, solid_capstyle="round")

    cmap   = plt.cm.coolwarm
    norm   = mcolors.Normalize(vmin=ot.min(), vmax=ot.max())
    colors = cmap(norm(ot))

    ms = max(12, min(60, 2000 // max(n, 1)))

    sc = ax.scatter(ot, wl, c=ot, cmap=cmap, norm=norm,
                    s=ms, zorder=3, linewidths=0.4,
                    edgecolors="white")


    cbar = fig.colorbar(sc, ax=ax, pad=0.02, fraction=0.035)
    cbar.set_label("Total Overtime OT (min)", fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    ax.set_xlabel("Total Overtime  OT  (minutes)", fontsize=11)
    ax.set_ylabel("Weighted Workload  WL", fontsize=11)
    ax.set_title(
        f"{title}\n{n} efficient solution{'s' if n != 1 else ''}  ·  "
        f"OT ∈ [{ot.min():.0f}, {ot.max():.0f}]  ·  "
        f"WL ∈ [{wl.min():.0f}, {wl.max():.0f}]",
        fontsize=10.5, fontweight="bold", pad=12
    )

    ax.grid(True, color="#E0E0E0", linewidth=0.7, linestyle="--", zorder=0)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#BDBDBD")
    ax.spines["bottom"].set_color("#BDBDBD")
    ax.tick_params(colors="#555555", labelsize=9)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Saved → {save_path}")
    else:
        plt.show()

    return fig



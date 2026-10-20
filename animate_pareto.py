import matplotlib.pyplot as plt
import matplotlib.animation as animation


def animate_pareto(discovery_order):

    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor("white")


    ax.set_title("hybrid scalarization execution", fontsize=13, fontweight="bold")
    ax.set_xlabel("OT — Total Overtime (min)", fontsize=11)
    ax.set_ylabel("WL — Weighted Workload", fontsize=11)

    all_ot = [p["OT"] for p in discovery_order[-1]]
    all_wl = [p["WL"] for p in discovery_order[-1]]

    ot_min, ot_max = min(all_ot), max(all_ot)
    wl_min, wl_max = min(all_wl), max(all_wl)

    ot_pad = (ot_max - ot_min) * 0.05 + 1
    wl_pad = (wl_max - wl_min) * 0.05 + 1

    ax.set_xlim(ot_min - ot_pad, ot_max + ot_pad)
    ax.set_ylim(wl_min - wl_pad, wl_max + wl_pad)
    ax.grid(True, linestyle="--", alpha=0.4)

    def update(frame_idx):
        ax.cla()         
        ax.set_title("hybrid scalarization execution", fontsize=13, fontweight="bold")
        ax.set_xlabel("OT — Total Overtime (min)", fontsize=11)
        ax.set_ylabel("WL — Weighted Workload", fontsize=11)
        ax.set_xlim(ot_min - ot_pad, ot_max + ot_pad)
        ax.set_ylim(wl_min - wl_pad, wl_max + wl_pad)
        ax.grid(True, linestyle="--", alpha=0.4)

        snapshot = discovery_order[frame_idx]


        previous = snapshot[:-1]

        newest   = snapshot[-1]


        if previous:
            ot_prev = [p["OT"] for p in previous]
            wl_prev = [p["WL"] for p in previous]
            ax.scatter(
                ot_prev, wl_prev,
                color="steelblue",
                s=25,
                alpha=0.7,
                zorder=2,
                label="discovered"
            )


        ax.scatter(
            newest["OT"], newest["WL"],
            color="crimson",
            s=70,
            zorder=3,
            label="new point"
        )

        ax.legend(loc="lower right", fontsize=9)




    anim = animation.FuncAnimation(
        fig,
        update,
        frames=len(discovery_order),
        interval=200,
        repeat=False,   
    )

    plt.tight_layout()
    plt.show()
    anim.save("front.gif")

    return anim 

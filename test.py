from generator import generate_instance
from epsilon_constraint import run_epsilon_constraint
from hybrid_scala import run_chalmet

# ── Instance ref : T=75, D=6, N=2, C=5, seed=42 ─────────────────────────────
instance = generate_instance(T=150, D=6, N=2, C=3, seed=42)
print(f"Instance ref : {instance['parameters']['P']} patients  "
      f"D={instance['parameters']['D']}  "
      f"N={instance['parameters']['N']}  "
      f"C={instance['parameters']['C']}\n")

# ── ε-contrainte ─────────────────────────────────────────────────────────────
print("=" * 60)
print("ε-CONTRAINTE  (s=1)")
print("=" * 60)
yn_eps = run_epsilon_constraint(instance, s=1, time_limit=300, verbose=False)

print(f"\nFront YN (ε-contrainte) — {len(yn_eps)} points :")
for p in yn_eps:
    print(f"  WL={p['WL']:.1f}  OT={p['OT']:.1f}")

# ── Chalmet (hybrid scalarization) ───────────────────────────────────────────
print("\n" + "=" * 60)
print("CHALMET / HYBRID SCALARIZATION  (s=1)")
print("=" * 60)
yn_chalmet = run_chalmet(instance, s=1, time_limit=300, verbose=False)

print(f"\nFront YN (Chalmet) — {len(yn_chalmet)} points :")
for p in yn_chalmet:
    print(f"  WL={p['WL']:.1f}  OT={p['OT']:.1f}")

# ── Comparaison rapide ────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("COMPARAISON")
print("=" * 60)
eps_set    = {(round(p["WL"], 1), round(p["OT"], 1)) for p in yn_eps}
chalmet_set = {(round(p["WL"], 1), round(p["OT"], 1)) for p in yn_chalmet}

non_supported = eps_set - chalmet_set
print(f"  |YN| ε-contrainte : {len(eps_set)}")
print(f"  |YN| Chalmet      : {len(chalmet_set)}")
print(f"  Points non-supportés manqués par Chalmet : {len(non_supported)}")
if non_supported:
    for pt in sorted(non_supported):
        print(f"    WL={pt[0]}  OT={pt[1]}")
        
# ── Vérification schedules ────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("VERIFICATION SCHEDULES")
print("=" * 60)

if yn_eps:
    p = yn_eps[0]
    print(f"\nε-contrainte — point 0 : WL={p['WL']:.1f}  OT={p['OT']:.1f}")
    if "schedule" in p and p["schedule"]:
        for tid, day in sorted(p["schedule"].items()):
            print(f"  traitement {tid:3d} → {'jour ' + str(day) if day is not None else 'NON PLANIFIE'}")
    else:
        print("  !! schedule absent ou vide")

if yn_chalmet:
    p = yn_chalmet[0]
    print(f"\nHybrid — point 0 : WL={p['WL']:.1f}  OT={p['OT']:.1f}")
    if "schedule" in p and p["schedule"]:
        for tid, day in sorted(p["schedule"].items()):
            print(f"  traitement {tid:3d} → {'jour ' + str(day) if day is not None else 'NON PLANIFIE'}")
    else:
        print("  !! schedule absent ou vide")

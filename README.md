# OCP — Planification de chimiothérapie ambulatoire
## Implémentation — Structure & Guide d'utilisation

> **Travail en cours.** Ce document reflète l'état actuel de l'implémentation (octobre 2026). Le code, les noms de fichiers et les interfaces peuvent encore évoluer avant la soumission finale. En cas de doute, se référer directement aux fichiers sources.

---

## Ce qu'il reste à faire

### Expériences
Lancer la suite d'instances suivante — chaque instance est traitée par **baseline + ε-contrainte + Chalmet** :

| Famille | T | D | N | C | Seeds | Utilisée dans |
|---|---|---|---|---|---|---|
| small | 30 | 6 | 2 | 5 | 5 | Volet 3 — cas facile, YN trivial |
| ref | 75 | 6 | 2 | 5 | 5 | Volet 3 — instance de référence |
| bigD | 75 | 9 | 2 | 5 | 5 | Volet 3 — effet de l'horizon D |
| bigC | 75 | 6 | 2 | 6 | 5 | Volet 3 — effet des fauteuils C |
| large | 150 | 6 | 2 | 5 | 3 | Volet 3 — effet du passage à l'échelle |
| realiste-med | 75 | 6 | (2,3) | (5,6) | 3 | Volet 4 — capacité variable, tension réaliste |
| realiste-large | 150 | 6 | (2,3) | (5,6) | 3 | Volet 4 — tension réaliste, grande taille |
| pharmacie | 75 | 6 | 2 | 5 | 3 | Volet 5 — base vs v1 vs v2 |

Pour chaque exécution, enregistrer : `WL`, `OT`, `|YN|`, `cpu_time`, `WL_baseline`, `OT_baseline`.

### Rapport
Le rapport suit les cinq volets du sujet :

**Volet 1 — État de l'art**
Nature combinatoire du problème, revue de la littérature sur la planification hospitalière, positionnement du papier Dagistanli & Azizoğlu (2026).

**Volet 2 — Modèle et méthodes de résolution**
Modèle MILP de base, modèle renforcé (PL), algorithme baseline, méthode ε-contrainte (deux phases), Chalmet (exploration de rectangles), limites du modèle.

**Volet 3 — Étude de XE et YN (instances synthétiques)**
- Calcul et analyse de YN sur les familles small / ref / bigD / bigC / large
- Comparaison avec la baseline : amplitude du gain potentiel
- Conflictualité des objectifs : YN étendu ou concentré ?
- ε-contrainte vs Chalmet : trouvent-ils les mêmes points ? Cas où l'un dépasse l'autre
- Analyse de sensibilité : quel paramètre (T, D, C) influe le plus sur la richesse de YN ?

**Volet 4 — Instances réalistes sous tension**
- Construction des instances realiste-med et realiste-large (capacité proche de la demande, proportions réelles de classes de patients)
- Résultats : YN, heures supplémentaires par jour, patients planifiés vs ignorés
- Comparaison avec la baseline : sur quelles journées et pour quels patients le gain est-il le plus marqué ?

**Volet 5 — Extensions et propositions**
- Incohérence de la contrainte 6 (discussion théorique)
- Perspectives non développées : nombre de séances variable par patient, pauses infirmières, extension multi-unité (problème de plus court chemin — hors périmètre)
- Extension pharmacie (v1 comptage de slots + v2 temps de préparation pondéré) : formalisation, expériences sur l'instance ref, trois fronts superposés (base / v1 / v2)

---

## Structure du projet

```
IMPLEMENTATION/
├── generator.py               # Générateur d'instances
├── baseline.py                # Heuristique gloutonne (sans MILP)
├── model_base.py              # Modèle MILP de base (mono-objectif)
├── model_pl.py                # Modèle MILP renforcé (ensembles éligibles + bornes serrées)
├── epsilon_constraint.py      # Méthode ε-contrainte → front de Pareto complet
├── hybrid_scala.py            # Chalmet / scalarisation hybride → front de Pareto complet
├── visualize_front.py         # Tracé du front de Pareto (WL vs OT)
├── visualize_instance.py      # Visualisation d'une instance générée
├── test.py                    # Test rapide d'intégration
└── volet5/
    ├── generator_pharmacy1.py           # Générateur + capacité pharmacie v1 (Pd slots)
    ├── generator_pharmacy2.py           # Générateur + capacité pharmacie v2 (temps pondéré)
    ├── model_pl_pharmacy1.py            # Modèle PL + contrainte pharmacie v1
    ├── model_pl_pharmacy2.py            # Modèle PL + contrainte pharmacie v2
    ├── epsilon_constraint_pharmacy1.py  # ε-contrainte sur modèle pharmacie v1
    ├── epsilon_constraint_pharmacy2.py  # ε-contrainte sur modèle pharmacie v2
    ├── hybrid_scala_pharmacy1.py        # Chalmet sur modèle pharmacie v1
    ├── hybrid_scala_pharmacy2.py        # Chalmet sur modèle pharmacie v2
    ├── visualize_instance_pharmacy1.py  # Visualisation instance pharmacie v1
    └── animate_pareto.py                # Animation de la construction du front de Pareto
```

> **Note :** Les fichiers terminant par `~` (ex. `model_pl.py~`) sont des sauvegardes automatiques de l'éditeur — les ignorer.

---

## Description fichier par fichier

### `generator.py`
Génère des instances synthétiques du problème OCP au format JSON, en respectant les paramètres cliniques du papier Dagistanli & Azizoğlu (2026).

**Constantes fixées d'après le papier :**
- `R = 480` min — durée journalière régulière
- `O_MAX = 120` min — heures supplémentaires maximales par jour
- `T_PRIME = 15` min — charge infirmière active par traitement
- Proportions de classes de patients et plages de durée d'infusion issues du Tableau 2 du papier

**Paramètres :**

| Paramètre | Type | Description |
|---|---|---|
| `T` | int | Nombre total de traitements (P = T // 3 patients) |
| `D` | int | Horizon de planification (jours) |
| `N` | int ou (a, b) | Infirmières par jour — fixe si int, tiré dans [a,b] si tuple |
| `C` | int ou (a, b) | Fauteuils par jour — même logique |
| `seed` | int | Graine aléatoire pour la reproductibilité |

**Utilisation :**
```python
from generator import generate_instance, generate_batch

# Instance unique en mémoire
inst = generate_instance(T=75, D=6, N=2, C=5, seed=42)

# Lot de 5 instances sauvegardées sur disque
generate_batch(T=75, D=6, N=2, C=5, n_instances=5,
               output_dir="instances/", base_seed=0)
# → produit : T75_D6_N2_C5_inst01.json … inst05.json
```

**Format de sortie :** dictionnaire avec les clés `parameters`, `days`, `patients`.

---

### `baseline.py`
Heuristique gloutonne qui reproduit la pratique actuelle du service : affecte les traitements jour par jour, sur le fauteuil disponible le plus tôt, en priorisant les traitements les plus longs.

**Fonctionnement :** parcourt les jours dans l'ordre, maintient un `DayState` (disponibilité des fauteuils et heures sup. utilisées), affecte un maximum de traitements éligibles chaque jour, ignore les autres. Pas de MILP — s'exécute en quelques millisecondes.

**Utilisation :**
```python
from baseline import run_baseline

result = run_baseline(instance)
print(result["WL"], result["OT"])
```

**Retourne :** `{status, cpu_time, WL, OT, x, y, O}` — même format que les solveurs MILP pour faciliter la comparaison.

---

### `model_base.py`
Modèle MILP de base issu de Dagistanli & Azizoğlu (2026), formulé comme un problème **mono-objectif** (maximiser WL avec une pénalité sur OT via ε_L).

**Variables de décision :**
- `x[i, d]` ∈ {0,1} — traitement i affecté au jour d
- `y[i]` ∈ {0,1} — traitement i ignoré
- `O[d]` ≥ 0 — heures supplémentaires utilisées le jour d

**Contraintes :** affectation, fenêtre d'admission, intervalles inter-traitements (rmin/rmax), capacité fauteuils, plafond heures sup., capacité infirmières.

**Utilisation :**
```python
from model_base import solve_base_model

result = solve_base_model(instance, time_limit=1800, verbose=False)
print(result["WL"], result["OT"], result["n_vars"], result["n_constrs"])
```

---

### `model_pl.py`
Version **renforcée** du modèle de base, implémentant la formulation « PL » du papier.

**Améliorations clés par rapport à `model_base.py` :**
1. **Ensembles éligibles** — `ed[i]` (jours auxquels le traitement i peut être affecté) et `et[d]` (traitements éligibles le jour d) précalculés par propagation de bornes. Les variables `x[i,d]` ne sont créées que pour les paires (i,d) faisables → moins de variables.
2. **Borne sur les heures sup. resserrée** — `O_star[d]` est le maximum d'heures sup. atteignable le jour d compte tenu des traitements éligibles, remplaçant le `O_max[d]` global.
3. **Variable explicite `Load[d]`** — charge du jour d en variable dédiée, renforçant la relaxation LP.
4. **ε_L recalculé** — basé sur `sum(O_star)` plutôt que sur le maximum global.

**Utilisation :** même interface que `model_base.py` :
```python
from model_pl import solve_pl_model

result = solve_pl_model(instance, time_limit=1800, verbose=False)
```

> **Quand utiliser lequel :** utiliser `model_base` pour reproduire les résultats bruts du papier ou comparer les temps de résolution. Utiliser `model_pl` pour tout le reste — il est plus rapide et sert de base à toutes les méthodes de calcul du front de Pareto.

---

### `epsilon_constraint.py`
Calcule le **front de Pareto complet (YN)** par la méthode ε-contrainte sur le problème bi-objectif (maximiser WL, minimiser OT).

**Algorithme :** itère sur des budgets OT décroissants (ε), en résolvant à chaque étape un sous-problème MILP avec la contrainte `∑ O[d] ≤ ε`. Chaque sous-problème est **en deux phases** : phase 1 maximise WL, phase 2 minimise OT parmi toutes les solutions WL-optimales (raffinement lexicographique). Le pas `s` contrôle la granularité.

**Utilisation :**
```python
from epsilon_constraint import run_epsilon_constraint

front = run_epsilon_constraint(instance, s=1, time_limit=300, verbose=False)
# front = liste de {"WL": ..., "OT": ..., "cpu_time": ..., "epsilon": ...}
```

**Paramètre `s` :** pas en minutes. `s=1` → exhaustif (lent sur grandes instances). `s=10` → plus rapide, peut manquer des points non dominés.

**Retourne :** liste de points non dominés triés par OT croissant.

---

### `hybrid_scala.py`
Calcule le **front de Pareto complet (YN)** par l'**algorithme de Chalmet** (scalarisation hybride / somme pondérée avec exploration de rectangles).

**Algorithme :**
1. **Phase 1** — calcule les deux points extrêmes : `p_A` (max WL) et `p_B` (min OT).
2. **Phase 2** — explore les rectangles dans l'espace objectif récursivement via une file. Pour chaque rectangle défini par les coins `(x1, x2)`, résout un problème à somme pondérée avec `λ = (x1_OT - x2_OT, x1_WL - x2_WL)` et des contraintes de boîte. Si un nouveau point est trouvé, divise en deux sous-rectangles.

**Propriété clé :** trouve tous les points non dominés *supportés* (ceux sur l'enveloppe convexe de YN). Peut manquer les points non supportés — contrairement à ε-contrainte qui les trouve tous avec un pas suffisamment fin.

**Utilisation :**
```python
from hybrid_scala import run_chalmet

front = run_chalmet(instance, s=1, time_limit=300, verbose=False)
```

**Retourne :** liste de points non dominés (même format que `run_epsilon_constraint`).

> **Note :** `hybrid_scala` importe directement des fonctions utilitaires de `epsilon_constraint.py` (extraction des ensembles, bornes, ensembles éligibles). Les deux fichiers doivent être dans le même répertoire.

---

### `visualize_front.py`
Trace le front de Pareto (WL vs OT) pour une ou plusieurs méthodes sur la même instance. Marque le point baseline pour comparaison.

### `visualize_instance.py`
Affiche un résumé d'une instance générée : classes de patients, fenêtres d'admission, paramètres journaliers.

### `test.py`
Test d'intégration rapide — génère une petite instance et lance tous les solveurs. Permet de vérifier que l'installation fonctionne avant de lancer les expériences.

---

## Volet 5 — Extension pharmacie

Tous les fichiers dans `volet5/` étendent la formulation de base avec une **contrainte de capacité pharmacie**. Deux versions sont implémentées :

### v1 — Contrainte de comptage de slots (`pharmacy1`)
**Contrainte ajoutée :** le nombre de traitements préparés chaque jour d ne peut pas dépasser une capacité journalière `P_d` :
```
∑_{i} x[i,d] ≤ P_d    ∀d
```
`P_d` est ajouté comme nouveau champ dans les données de chaque jour (généré par `generator_pharmacy1.py`).

### v2 — Contrainte de temps de préparation pondéré (`pharmacy2`)
**Contrainte ajoutée :** le temps total de préparation pharmacie le jour d ne peut pas dépasser le temps disponible `Np_d × R_d` :
```
∑_{i} p_i · x[i,d] ≤ Np_d · R_d    ∀d
```
où `p_i` est le temps de préparation du traitement i selon la classe du patient :
| Classe | p_i |
|---|---|
| 1 | 10 min |
| 2 | 20 min |
| 3 | 30 min |
| 4 | 40 min |

`Np_d` (nombre de pharmaciens par jour) est généré comme valeur fixe ou variable.

### Correspondance des fichiers

Chaque algorithme a son équivalent pharmacie avec la même interface :

| Base | Pharmacie v1 | Pharmacie v2 |
|---|---|---|
| `generator.py` | `generator_pharmacy1.py` | `generator_pharmacy2.py` |
| `model_pl.py` | `model_pl_pharmacy1.py` | `model_pl_pharmacy2.py` |
| `epsilon_constraint.py` | `epsilon_constraint_pharmacy1.py` | `epsilon_constraint_pharmacy2.py` |
| `hybrid_scala.py` | `hybrid_scala_pharmacy1.py` | `hybrid_scala_pharmacy2.py` |

**Utilisation (même interface que la base) :**
```python
from volet5.epsilon_constraint_pharmacy2 import run_epsilon_constraint

front = run_epsilon_constraint(instance, s=1, time_limit=300)
```

### `animate_pareto.py`
Anime la construction pas-à-pas du front de Pareto (utile pour la présentation orale).

### `visualize_instance_pharmacy1.py`
Étend la visualisation de base pour afficher la capacité journalière pharmacie `P_d`.

---

## Démarrage rapide

```python
from generator import generate_instance
from baseline import run_baseline
from model_pl import solve_pl_model
from epsilon_constraint import run_epsilon_constraint
from hybrid_scala import run_chalmet

# 1. Générer une instance
inst = generate_instance(T=75, D=6, N=2, C=5, seed=42)

# 2. Baseline
b = run_baseline(inst)
print(f"Baseline     → WL={b['WL']:.0f}  OT={b['OT']:.0f}")

# 3. Optimum mono-objectif
r = solve_pl_model(inst)
print(f"Modèle PL    → WL={r['WL']:.0f}  OT={r['OT']:.0f}")

# 4. Front de Pareto complet — les deux méthodes
front_eps = run_epsilon_constraint(inst, s=1)
front_cha = run_chalmet(inst, s=1)

print(f"ε-contrainte : {len(front_eps)} points non dominés")
print(f"Chalmet      : {len(front_cha)} points non dominés")
```

---

## Dépendances

```
gurobipy   # Gurobi 10+ avec licence académique valide
matplotlib # pour visualize_*.py et animate_pareto.py
```

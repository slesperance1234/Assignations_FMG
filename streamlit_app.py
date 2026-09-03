import pandas as pd
import streamlit as st
from ortools.linear_solver import pywraplp

st.set_page_config(page_title="Assignation FMG", page_icon="🎈", layout="wide")
st.title("🎈 Optimisation des passagers FMG")

st.write("Remplir les sections **Ballons** et **Passagers**")

# === Saisie interactive via tableaux éditables ===
st.subheader("📦 Ballons")
defaut_ballons = pd.DataFrame([
    {"id": "03", "max_poids": 400, "max_passagers": 2},
    {"id": "09", "max_poids": 350, "max_passagers": 2},
    {"id": "11", "max_poids": 350, "max_passagers": 2},
    {"id": "02", "max_poids": 500, "max_passagers": 3},
    {"id": "07", "max_poids": 2100, "max_passagers": 12},
    {"id": "08", "max_poids": 1300, "max_passagers": 8},
    {"id": "10", "max_poids": 300, "max_passagers": 3},
])
df_ballons = st.data_editor(defaut_ballons, num_rows="dynamic", width=500)

st.subheader("👥 Passagers")
defaut_passagers = pd.DataFrame([
  {"contrat": "88132", "poids": 185},
  {"contrat": "88132", "poids": 225},
  {"contrat": "88132", "poids": 130},
  {"contrat": "119420", "poids": 220},
  {"contrat": "119420", "poids": 145},
  {"contrat": "134645", "poids": 165},
  {"contrat": "134645", "poids": 187},
  {"contrat": "145629", "poids": 200},
  {"contrat": "145629", "poids": 145},
  {"contrat": "168087", "poids": 185},
  {"contrat": "168087", "poids": 125},
  {"contrat": "171618", "poids": 230},
  {"contrat": "171618", "poids": 128},
  {"contrat": "172827", "poids": 140},
  {"contrat": "172827", "poids": 100},
  {"contrat": "172827", "poids": 220},
  {"contrat": "172827", "poids": 225},
  {"contrat": "178771", "poids": 130},
  {"contrat": "178771", "poids": 155},
  {"contrat": "179404", "poids": 154},
  {"contrat": "179404", "poids": 136},
  {"contrat": "185212", "poids": 140},
  {"contrat": "185212", "poids": 143},
  {"contrat": "185272", "poids": 270},
  {"contrat": "185272", "poids": 140},
  {"contrat": "185698", "poids": 159},
  {"contrat": "185698", "poids": 165},
  {"contrat": "185698", "poids": 195},
  {"contrat": "185698", "poids": 113}
])
df_passagers = st.data_editor(defaut_passagers, num_rows="dynamic", width=300)

# Convertir en listes de dictionnaires
ballons = df_ballons.to_dict(orient="records")

passagers = []
for contrat, groupe in df_passagers.groupby("contrat"):
    passagers.append({"contrat": str(contrat), "poids": groupe["poids"].dropna().astype(int).tolist()})

# Préparer les groupes (contrat indivisible)
groupes = [
    {"contrat": p["contrat"], "nb": len(p["poids"]), "poids": sum(p["poids"])}
    for p in passagers if len(p["poids"]) > 0
]

if st.button("🚀 Lancer l'optimisation", type="primary"):
    solver = pywraplp.Solver.CreateSolver('SCIP')
    if solver is None:
        st.error("Le solveur SCIP n'est pas disponible. Vérifie l'installation d'OR-Tools.")
        st.stop()

    # Variables x[g,b] = 1 si le groupe g va dans le ballon b
    x = {}
    for g_idx, g in enumerate(groupes):
        for b_idx, b in enumerate(ballons):
            x[(g_idx, b_idx)] = solver.BoolVar(f"x_{g['contrat']}_{b['id']}")

    # Chaque groupe dans au plus 1 ballon
    for g_idx, g in enumerate(groupes):
        solver.Add(sum(x[(g_idx, b_idx)] for b_idx in range(len(ballons))) <= 1)

    # Contraintes de capacité par ballon
    for b_idx, b in enumerate(ballons):
        solver.Add(sum(groupes[g_idx]["nb"] * x[(g_idx, b_idx)] for g_idx in range(len(groupes))) <= b["max_passagers"])
        solver.Add(sum(groupes[g_idx]["poids"] * x[(g_idx, b_idx)] for g_idx in range(len(groupes))) <= b["max_poids"])

    # Objectif : maximiser le nombre total de passagers
    solver.Maximize(sum(groupes[g_idx]["nb"] * x[(g_idx, b_idx)] for g_idx in range(len(groupes)) for b_idx in range(len(ballons))))

    status = solver.Solve()

    if status != pywraplp.Solver.OPTIMAL:
        st.error("Pas de solution optimale trouvée 😥")
        st.stop()

    st.success("✅ Solution optimale trouvée !")

    # === Tableau récap par ballon ===
    #sorted_ballons = sorted(ballons, key=lambda k: int(k['id']))  #ancienne version
    sorted_ballons = sorted(ballons, key=lambda k: int(str(k['id']).strip() or 0))
    recap = []
    for b in sorted_ballons:
        original_b_idx = ballons.index(b)
        contrats_b = []
        nb_b, poids_b = 0, 0
        for g_idx, g in enumerate(groupes):
            if x[(g_idx, original_b_idx)].solution_value() > 0.5:
                contrats_b.append(g["contrat"])
                nb_b += g["nb"]
                poids_b += g["poids"]
        recap.append({
            "Ballon": b['id'],
            "Contrats": ", ".join(contrats_b) if contrats_b else "-",
            "Passagers": f"{nb_b}/{b['max_passagers']}",
            "Poids utilisé": f"{poids_b}/{b['max_poids']}",
            "Poids restant": b["max_poids"] - poids_b,
        })

    st.subheader("📋 Répartition par ballon")
    df_recap = pd.DataFrame(recap)
    st.dataframe(df_recap, width="content", hide_index=True, height=(35 * len(df_recap) + 50))

    # === Affectations par contrat ===
    affectations = []
    for g_idx, g in enumerate(groupes):
        assigned = "-"
        for b_idx, b in enumerate(ballons):
            if x[(g_idx, b_idx)].solution_value() > 0.5:
                assigned = b['id']
                break
        affectations.append({
            "Contrat": g["contrat"],
            "Nb passagers": g["nb"],
            "Poids total": g["poids"],
            "Ballon": assigned,
        })

    df_aff = pd.DataFrame(affectations)
    try:
        df_aff["_cnum"] = df_aff["Contrat"].astype(int)
        df_aff = df_aff.sort_values("_cnum").drop(columns=["_cnum"])
    except Exception:
        df_aff = df_aff.sort_values("Contrat")

    st.subheader("📑 Affectations par contrat")
    st.dataframe(df_aff, width="content", hide_index=True, height=(35 * len(df_aff) + 50))

    # Téléchargements CSV
    csv_aff = df_aff.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Télécharger les affectations (CSV)", data=csv_aff, file_name="affectations_par_contrat.csv", mime="text/csv")


    # === Résumé global & contrats non embarqués ===
    total_objectif = int(solver.Objective().Value())
    total_demandes = sum(g["nb"] for g in groupes)
    st.info(f"**Passagers transportés : {total_objectif} / {total_demandes}**")

    non_embarques = df_aff[df_aff["Ballon"] == "-"]
    if len(non_embarques) > 0:
        st.divider()
        st.warning("❌ Contrats non embarqués")
        st.dataframe(non_embarques, width="content", hide_index=True,column_config={"Ballon": None})
    else:
        st.success("Tous les contrats ont été embarqués ! 🎉")

import io
import re
import pandas as pd
import streamlit as st
from ortools.linear_solver import pywraplp

st.set_page_config(page_title="Optimisation de l'assignation des passagers", page_icon="🎈", layout="wide")
st.title("🎈 Optimisation des passagers")

st.write("Remplir les sections **Montgolfières** et **Passagers**, cliquez ensuite sur **Lancer l'optimisation**")

# === Données par défaut ===
DEFAUT_BALLONS = [
    {"id": "03", "max_poids_AM": 400, "max_poids_PM": 400, "max_passagers": 2},
    {"id": "09", "max_poids_AM": 350, "max_poids_PM": 400, "max_passagers": 2},
    {"id": "11", "max_poids_AM": 350, "max_poids_PM": 375, "max_passagers": 2},
    {"id": "02", "max_poids_AM": 500, "max_poids_PM": 600, "max_passagers": 3},
    {"id": "07", "max_poids_AM": 2100, "max_poids_PM": 2100, "max_passagers": 12},
    {"id": "08", "max_poids_AM": 1300, "max_poids_PM": 1300, "max_passagers": 8},
    {"id": "10", "max_poids_AM": 300, "max_poids_PM": 350, "max_passagers": 3},
]

# === Upload PDF pour remplacer la liste des passagers ===
st.subheader("📥 Importer une liste de passagers")
uploaded = st.file_uploader("Déposez un fichier PDF contenant le tableau des passagers (contrat en 1ère colonne, poids en 3ème colonne).", type=["pdf"])

def parse_pdf_passengers(file_bytes):
    try:
        import pdfplumber
    except Exception:
        raise RuntimeError("Le package 'pdfplumber' n'est pas installé. Installez-le avec `pip install pdfplumber`.")
    buf = io.BytesIO(file_bytes)
    rows = []
    with pdfplumber.open(buf) as pdf:
        for page in pdf.pages:
            # try to extract tables
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []
            for table in tables:
                for row in table:
                    # ignore header-like rows
                    if not row:
                        continue
                    # normalize row entries
                    row_vals = [("" if v is None else str(v).strip()) for v in row]
                    # If row has at least 3 columns, take col0 as contrat and col2 as poids
                    if len(row_vals) >= 3:
                        contrat = row_vals[0]
                        poids = row_vals[2]
                        # skip header lines
                        if re.search(r'(?i)nom|poids|#|contrat', " ".join(row_vals)):
                            continue
                        rows.append((contrat, poids))
            # fallback: if no tables or coarse text, try regex on page text
            if not rows:
                text = page.extract_text() or ""
                # lines like: 83683  Rodeghiero Sylvie  152  Non ...
                for line in text.splitlines():
                    m = re.match(r'^\s*(\d{3,})\b.*?\b(\d{2,3})\b', line)
                    if m:
                        rows.append((m.group(1), m.group(2)))
    # Post-process rows into DataFrame
    cleaned = []
    for contrat, poids in rows:
        # extract digits from contract
        c = re.sub(r'\D', '', contrat)
        p = re.search(r'(\d+)', str(poids))
        if c and p:
            try:
                cleaned.append({"contrat": c, "poids": int(p.group(1))})
            except ValueError:
                continue
    if not cleaned:
        raise RuntimeError("Aucune donnée exploitables trouvée dans le PDF.")
    return pd.DataFrame(cleaned)

def parse_csv_or_excel(uploaded_file):
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        raise RuntimeError(f"Erreur lors de la lecture du fichier: {e}")
    # heuristique : chercher colonnes contenant 'contrat' et 'poids' ou prendre la 1ère et 3ème
    cols = [c.lower() for c in df.columns.astype(str)]
    contrat_col = None
    poids_col = None
    for c in df.columns:
        lc = str(c).lower()
        if 'contrat' in lc or '#' == lc.strip():
            contrat_col = c
        if 'poids' in lc:
            poids_col = c
    if contrat_col is None:
        contrat_col = df.columns[0]
    if poids_col is None:
        # try third column if exists
        if len(df.columns) >= 3:
            poids_col = df.columns[2]
        else:
            poids_col = df.columns[1] if len(df.columns) >= 2 else df.columns[0]
    out = pd.DataFrame({
        "contrat": df[contrat_col].astype(str).str.extract(r'(\d+)')[0],
        "poids": pd.to_numeric(df[poids_col], errors='coerce').astype('Int64')
    }).dropna(subset=["contrat", "poids"])
    out["poids"] = out["poids"].astype(int)
    return out


df_passagers = None
if uploaded is not None:
    try:
        if uploaded.type == "application/pdf" or uploaded.name.lower().endswith(".pdf"):
            try:
                df_parsed = parse_pdf_passengers(uploaded.read())
            except RuntimeError as e:
                st.error(str(e))
                df_parsed = None
        else:
            # CSV or Excel
            try:
                df_parsed = parse_csv_or_excel(uploaded)
            except RuntimeError as e:
                st.error(str(e))
                df_parsed = None
        if df_parsed is not None:
            # Les poids provenant du PDF sont en livres (lbs) et seront conservés tels quels
            st.write("Importation réussie. Vous pouvez modifier ci-dessous au besoin.")
            df_passagers = st.data_editor(df_parsed.rename(columns={"contrat": "contrat", "poids": "poids"}), num_rows="dynamic", width=300)
    except Exception as e:
        st.error(f"Erreur lors de l'import : {e}")

# === Saisie interactive via tableaux éditables si pas d'import ou après import ===
if df_passagers is None:
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
     ])
    df_passagers = st.data_editor(defaut_passagers, num_rows="dynamic", width=300)

st.subheader("📦 Montgolfières")
df_ballons = st.data_editor(pd.DataFrame(DEFAUT_BALLONS), num_rows="dynamic", width=500)

# radio choix AM/PM
st.write("")
periode_selection = st.radio("Période à utiliser pour les capacités (poids)", options=["AM", "PM"], index=0, horizontal=True)

# Convertir en listes de dictionnaires
ballons = df_ballons.to_dict(orient="records")

passagers = []
for contrat, groupe in df_passagers.groupby("contrat"):
    passagers.append({"contrat": str(contrat), "poids": groupe["poids"].dropna().astype(int).tolist()})

# Préparer les groupes (contrat indivisible)
groupes = [
    {"contrat": p["contrat"], "nb": len(p["poids"]), "poids": sum(p["poids"]) }
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
    max_poids_key = f"max_poids_{periode_selection}"
    for b_idx, b in enumerate(ballons):
        # support backward-compat: si l'utilisateur a une colonne max_poids, on la prend en fallback
        b_max_poids = b.get(max_poids_key, b.get("max_poids", 0))
        solver.Add(sum(groupes[g_idx]["nb"] * x[(g_idx, b_idx)] for g_idx in range(len(groupes))) <= b["max_passagers"]) 
        solver.Add(sum(groupes[g_idx]["poids"] * x[(g_idx, b_idx)] for g_idx in range(len(groupes))) <= b_max_poids) 

    # Objectif : maximiser le nombre total de passagers
    solver.Maximize(sum(groupes[g_idx]["nb"] * x[(g_idx, b_idx)] for g_idx in range(len(groupes)) for b_idx in range(len(ballons))))

    status = solver.Solve()

    if status != pywraplp.Solver.OPTIMAL:
        st.error("Pas de solution optimale trouvée 😥")
        st.stop()

    st.success("✅ Solution optimale trouvée !")

    # === Tableau récap par ballon ===
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
        b_max_poids = b.get(max_poids_key, b.get("max_poids", 0))
        recap.append({
            "Ballon": b['id'],
            "Contrats": ", ".join(contrats_b) if contrats_b else "-",
            "Passagers": f"{nb_b}/{b['max_passagers']}",
            "Poids utilisé": f"{poids_b}/{b_max_poids}",
            "Poids restant": b_max_poids - poids_b,
        })

    st.subheader("📋 Répartition par montgolfière")
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
   # csv_aff = df_aff.to_csv(index=False).encode("utf-8")
   # st.download_button("⬇️ Télécharger les affectations (CSV)", data=csv_aff, file_name="affectations_par_contrat.csv", mime="text/csv")


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

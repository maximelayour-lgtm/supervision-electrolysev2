import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ==========================================
# CONSTANTES DU PROCÉDÉ
# ==========================================
F = 96485
M_HCL = 36.46
M_CL2 = 71.0
N_CELLULES = 108
CONC_HCL = 0.35
DENSITE_HCL = 1.17
RENDEMENT_ANO = 0.98
U0_APPROX = 310.0

MAX_PERTE_CE_PAR_MOIS = -0.15
MAX_HAUSSE_R_PAR_MOIS = 0.005
SEUIL_CE_CRITIQUE = 90.0

st.set_page_config(page_title="Suivi Électrolyse", layout="wide")

def calculer_rendement(row):
    I_A = row['I_kA'] * 1000
    if I_A <= 0:
        return np.nan

    if row['QHCl_L_h'] > 0:
        masse_pure_hcl = row['QHCl_L_h'] * DENSITE_HCL * CONC_HCL
        destr_oh_kmol_h = masse_pure_hcl / M_HCL
    else:
        prod_cl2_kg = (I_A * M_CL2 * 3600 * RENDEMENT_ANO * N_CELLULES) / (2 * F * 1000)
        moles_cl2 = prod_cl2_kg / M_CL2
        pct_o2 = row['%O2_Mesure']
        moles_o2 = moles_cl2 * (pct_o2 / (100 - pct_o2)) if pct_o2 < 100 else 0
        destr_oh_kmol_h = moles_o2 * 4

    perte_ce_fraction = (destr_oh_kmol_h / 3.6) * F / (I_A * N_CELLULES)
    return (1 - perte_ce_fraction) * 100

# ==========================================
# MENU LATÉRAL (NAVIGATION & DONNÉES)
# ==========================================
st.sidebar.title("Navigation")
page_choisie = st.sidebar.radio("Allez vers :", ["📊 Tableau de Bord", "⚙️ Aide au réglage débit HCl"])

st.sidebar.markdown("---")
st.sidebar.header("📂 Chargement des données")

fichier_upload = st.sidebar.file_uploader("1. Chargez votre propre CSV", type=["csv"])

st.sidebar.markdown("**OU**")

exemple_choisi = st.sidebar.selectbox(
    "2. Utilisez un fichier d'exemple :",
    ("Aucun",
     "01 - Début de vie",
     "02 - Milieu de vie",
     "03 - Fin de vie",
     "04 - Panne soudaine",
     "05 - Année complète avec arrêts",
     "06 - test alerte HCl",
     "07 - Test complet O2/HCl (4 phases)")
)

df = None

if fichier_upload is not None:
    df = pd.read_csv(fichier_upload, sep=';', decimal=',')
    st.sidebar.success("Fichier personnel chargé !")

elif exemple_choisi != "Aucun":
    fichiers_exemples = {
        "01 - Début de vie": "01_debut_vie.csv",
        "02 - Milieu de vie": "02_milieu_vie.csv",
        "03 - Fin de vie": "03_fin_vie.csv",
        "04 - Panne soudaine": "04_panne_soudaine.csv",
        "05 - Année complète avec arrêts": "05_annee_complete_incidents.csv",
        "06 - test alerte HCl": "06_test_alerte_hcl.csv",
        "07 - Test complet O2/HCl (4 phases)": "07_test_complet_o2_hcl.csv"
    }
    fichier_a_charger = fichiers_exemples[exemple_choisi]
    try:
        df = pd.read_csv(fichier_a_charger, sep=';', decimal=',')
    except FileNotFoundError:
        st.sidebar.error("Fichier d'exemple introuvable.")

# ==========================================
# PRÉ-TRAITEMENT GLOBAL DES DONNÉES
# ==========================================
if df is not None:
    df['Date'] = pd.to_datetime(df['Date'])
    df['Electrolyseur'] = df['Electrolyseur'].astype(str)
    df['CE_Calcule'] = df.apply(calculer_rendement, axis=1)
    df['Resistance'] =
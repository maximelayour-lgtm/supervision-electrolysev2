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
page_choisie = st.sidebar.radio("Allez vers :", ["📊 Tableau de Bord", "⚙️ Simulateur & Réglages"])

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
     "07 - Test complet O2/HCl (4 phases)") # <-- MODIFIÉ ICI
)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Paramètres d'analyse")
tolerance_hcl = st.sidebar.slider("Tolérance Écart HCl (%)", min_value=3, max_value=8, value=5, step=1)

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
        "07 - Test complet O2/HCl (4 phases)": "07_test_complet_o2_hcl.csv" # <-- MODIFIÉ ICI
    }
    fichier_a_charger = fichiers_exemples[exemple_choisi]
    try:
        df = pd.read_csv(fichier_a_charger, sep=';', decimal=',')
        st.sidebar.info(f"Données d'exemple activées : {exemple_choisi}")
    except FileNotFoundError:
        st.sidebar.error("Fichier d'exemple introuvable. L'avez-vous bien uploadé sur GitHub ?")

# Pré-traitement global
if df is not None:
    df['Date'] = pd.to_datetime(df['Date'])
    df['CE_Calcule'] = df.apply(calculer_rendement, axis=1)
    df['Resistance'] = np.where(df['I_kA'] > 0, (df['U_V'] - U0_APPROX) / df['I_kA'], np.nan)

# ==========================================
# PAGE 1 : TABLEAU DE BORD CLASSIQUE
# ==========================================
if page_choisie == "📊 Tableau de Bord":
    st.title("📊 Tableau de Bord : Suivi des Électrolyseurs")

    if df is not None:
        resultats = []
        for nom, groupe in df.groupby('Electrolyseur'):
            groupe = groupe.sort_values('Date')
            groupe_propre = groupe.dropna(subset=['CE_Calcule', 'Resistance']).copy()
            if len(groupe_propre) == 0: continue
                
            date_max = groupe_propre['Date'].max()
            date_limite = date_max - pd.Timedelta(days=30)
            groupe_recent = groupe_propre[groupe_propre['Date'] >= date_limite].copy()
            
            if len(groupe_recent) < 3:
                continue
                
            jours_ecoules = (groupe_recent['Date'] - groupe_recent['Date'].min()).dt.days
            pente_ce_jour, _ = np.polyfit(jours_ecoules, groupe_recent['CE_Calcule'], 1)
            pente_r_jour, _ = np.polyfit(jours_ecoules, groupe_recent['Resistance'], 1)
            
            ce_moyen_recent = groupe_recent['CE_Calcule'].tail(5).mean() 
            
            derniere_ligne = groupe_recent.iloc[-1]
            I_actuel_kA = derniere_ligne['I_kA']
            Q_HCl_mesure = derniere_ligne['QHCl_L_h']
            
            diag_coherence = "✅ Cohérent"
            if I_actuel_kA > 0:
                I_A = I_actuel_kA * 1000
                perte_rendement = 1 - (ce_moyen_recent / 100)
                destr_oh_kmol_h = (I_A * N_CELLULES * perte_rendement / F) * 3.6
                q_hcl_theorique = ((destr_oh_kmol_h * M_HCL) / CONC_HCL) / DENSITE_HCL
                
                if q_hcl_theorique > 0:
                    ecart_pct = ((Q_HCl_mesure - q_hcl_theorique) / q_hcl_theorique) * 100
                    if ecart_pct <= -tolerance_hcl:
                        diag_coherence = f"⚠️ Trop faible ({ecart_pct:.0f}%)"
                    elif ecart_pct >= tolerance_hcl:
                        diag_coherence = f"⚠️ Fort (+{ecart_pct:.0f}%)"
            else:
                diag_coherence = "Arrêt usine"
                
            resultats.append({
                'Électro.': nom,
                'CE Actuel (%)': f"{ce_moyen_recent:.1f}",
                'Δ CE/mois': f"{(pente_ce_jour * 30):+.3f} %",
                'Δ R/mois': f"{(pente_r_jour * 30):+.4f} Ω",
                'Membrane': "🔴 FIN DE VIE" if ce_moyen_recent < SEUIL_CE_CRITIQUE else ("⚠️ CHUTE" if (pente_ce_jour * 30) < MAX_PERTE_CE_PAR_MOIS else "✅ Normal"),
                'Revêtement': "⚠️ USURE" if (pente_r_jour * 30) > MAX_HAUSSE_R_PAR_MOIS else "✅ Normal",
                'Injection HCl': diag_coherence
            })

        col_titre, col_filtre = st.columns([2, 1])
        with col_titre: st.subheader("📋 Bilan électrolyseurs (30 derniers jours)")
        with col_filtre:
            liste_electro = sorted(df['Electrolyseur'].unique())
            selection_electro = st.multiselect("🔍 Filtrer :", liste_electro, default=liste_electro)

        df_res = pd.DataFrame(resultats)
        st.dataframe(df_res[df_res['Électro.'].isin(selection_electro)], use_container_width=True)
        
        st.markdown("---")
        col_graphe_titre, col_lissage = st.columns([2, 1])
        with col_graphe_titre: st.subheader("📈 Visualisation des Performances")
        with col_lissage: lissage = st.slider("📏 Lissage (jours)", 1, 14, 7)

        df_plot = df[df['Electrolyseur'].isin(selection_electro)].sort_values('Date').copy()
        if lissage > 1:
            df_plot['CE_Affiche'] = df_plot.groupby('Electrolyseur')['CE_Calcule'].transform(lambda x: x.rolling(lissage, min_periods=1).mean())
            df_plot['R_Affiche'] = df_plot.groupby('Electrolyseur')['Resistance'].transform(lambda x: x.rolling(lissage, min_periods=1).mean())
        else:
            df_plot['CE_Affiche'], df_plot['R_Affiche'] = df_plot['CE_Calcule'], df_plot['Resistance']
            
        col1, col2 = st.columns(2)
        with col1:
            fig_ce = px.line(df_plot, x='Date', y='CE_Affiche', color='Electrolyseur', title="Rendement Cathodique (CE)")
            fig_ce.add_hline(y=SEUIL_CE_CRITIQUE, line_dash="dash", line_color="red")
            fig_ce.update_traces(connectgaps=False)
            st.plotly_chart(fig_ce, use_container_width=True)
        with col2:
            fig_r = px.line(df_plot, x='Date', y='R_Affiche', color='Electrolyseur', title="Résistance (Revêtements)")
            fig_r.update_traces(connectgaps=False)
            st.plotly_chart(fig_r, use_container_width=True)
    else:
        st.info("Veuillez charger des données dans le menu latéral.")

# ==========================================
# PAGE 2 : SIMULATEUR ET RÉGLAGES
# ==========================================
elif page_choisie == "⚙️ Simulateur & Réglages":
    st.title("⚙️ Simulateur et Préconisation de Réglages")
    st.markdown("Ce module calcule les besoins théoriques de l'usine selon la charge des deux transformateurs, en se basant sur l'usure récente des membranes.")
    
    if df is not None:
        ce_moyens = {}
        for nom, groupe in df.groupby('Electrolyseur'):
            groupe_propre = groupe.dropna(subset=['CE_Calcule']).copy()
            if len(groupe_propre) > 0:
                date_limite = groupe_propre['Date'].max() - pd.Timedelta(days=30)
                groupe_recent = groupe_propre[groupe_propre['Date'] >= date_limite]
                if len(groupe_recent) > 0:
                    ce_moyens[nom] = groupe_recent['CE_Calcule'].mean()
        
        st.subheader("1. Définir la consigne des Transformateurs")
        
        tr1_presents = [e for e in ['303', '304', '305'] if e in ce_moyens]
        tr2_presents = [e for e in ['306', '307'] if e in ce_moyens]
        
        col_tr1, col_tr2 = st.columns(2)
        
        with col_tr1:
            st.markdown("⚡ **Transformateur 1 (303, 304, 305)**")
            if tr1_presents:
                min_tr1 = len(tr1_presents) * 7.0
                max_tr1 = len(tr1_presents) * 100.0
                val_tr1 = len(tr1_presents) * 15.0
                i_tr1 = st.number_input("Consigne globale TR1 (kA)", min_value=min_tr1, max_value=max_tr1, value=val_tr1, step=1.0)
                i_par_elec_tr1 = i_tr1 / len(tr1_presents)
                st.info(f"➡️ **{i_par_elec_tr1:.1f} kA** distribués par électrolyseur ({', '.join(tr1_presents)})")
            else:
                st.warning("Aucun électrolyseur du TR1 n'est actif.")
                i_par_elec_tr1 = 0
                
        with col_tr2:
            st.markdown("⚡ **Transformateur 2 (306, 307)**")
            if tr2_presents:
                min_tr2 = len(tr2_presents) * 7.0
                max_tr2 = len(tr2_presents) * 100.0
                val_tr2 = len(tr2_presents) * 15.0
                i_tr2 = st.number_input("Consigne globale TR2 (kA)", min_value=min_tr2, max_value=max_tr2, value=val_tr2, step=1.0)
                i_par_elec_tr2 = i_tr2 / len(tr2_presents)
                st.info(f"➡️ **{i_par_elec_tr2:.1f} kA** distribués par électrolyseur ({', '.join(tr2_presents)})")
            else:
                st.warning("Aucun électrolyseur du TR2 n'est actif.")
                i_par_elec_tr2 = 0

        st.markdown("---")
        st.subheader("2. Saisie des mesures réelles & Diagnostics")
        
        cols = st.columns(len(ce_moyens))
        
        for i, (nom, ce_moyen) in enumerate(ce_moyens.items()):
            with cols[i]:
                st.markdown(f"### Élec. {nom}")
                st.write(f"*(Rendement : {ce_moyen:.1f}%)*")
                
                if nom in ['303', '304', '305']:
                    cadence_kA = i_par_elec_tr1
                elif nom in ['306', '307']:
                    cadence_kA = i_par_elec_tr2
                else:
                    cadence_kA = 0
                    
                if cadence_kA > 0:
                    I_A = cadence_kA * 1000
                    perte_rendement = 1 - (ce_moyen / 100)
                    
                    destr_oh_kmol_h = (I_A * N_CELLULES * perte_rendement / F) * 3.6
                    q_hcl_theorique = ((destr_oh_kmol_h * M_HCL) / CONC_HCL) / DENSITE_HCL
                    
                    prod_cl2_kg = (I_A * M_CL2 * 3600 * RENDEMENT_ANO * N_CELLULES) / (2 * F * 1000)
                    moles_cl2 = prod_cl2_kg / M_CL2
                    eq_o2 = destr_oh_kmol_h / 4
                    pct_o2_theorique = (eq_o2 / (moles_cl2 + eq_o2)) * 100
                    
                    st.info(f"**Cibles Théoriques :**\n\n💧 HCl : {q_hcl_theorique:.1f} L/h\n\n💨 O2 : {pct_o2_theorique:.2f} %")
                    
                    hcl_mesure = st.number_input(f"HCl mesuré (L/h)", min_value=0.0, value=float(round(q_hcl_theorique, 1)), step=1.0, key=f"hcl_{nom}")
                    o2_mesure = st.number_input(f"O2 mesuré (%)", min_value=0.0, value=float(round(pct_o2_theorique, 2)), step=0.1, key=f"o2_{nom}")
                    
                    ecart_hcl_pct = ((hcl_mesure - q_hcl_theorique) / q_hcl_theorique) * 100 if q_hcl_theorique > 0 else 0
                    ecart_o2 = o2_mesure - pct_o2_theorique
                    
                    tol_hcl = 5.0
                    tol_o2 = 0.3
                    
                    if abs(ecart_o2) <= tol_o2 and ecart_hcl_pct > tol_hcl:
                        st.warning("📉 **Baisser la pompe d'acide** (Surdosage inutile, l'O2 est normal).")
                    elif ecart_o2 > tol_o2 and ecart_hcl_pct < -tol_hcl:
                        st.error("📈 **Augmenter l'acide !** (Manque de neutralisation, O2 trop haut).")
                    elif abs(ecart_o2) <= tol_o2 and abs(ecart_hcl_pct) <= tol_hcl:
                        st.success("✅ **Réglage Optimal.**")
                    else:
                        st.warning("⚠️ **Anomalie terrain.** Les deux sondes (O2 et débitmètre) divergent anormalement. Vérifiez l'analyseur O2.")
                else:
                    st.write("Équipement à l'arrêt.")
                
    else:
        st.info("Veuillez charger des données dans le menu latéral pour utiliser le simulateur.")
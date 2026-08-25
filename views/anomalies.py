import sys
from pathlib import Path
import datetime
import streamlit as st
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

def generate_id(prefix: str) -> str:
    now = datetime.datetime.now()
    return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"

def show():
    st.title("⚠️ Anomalies & Points de Vigilance Site")

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get("user_profile", {"full_name": "Éric KUTER", "role": "agent"})
    role = user_info.get("role", "agent")
    agent_nom = user_info.get("full_name", "Agent")

    st.markdown(f"### 📍 Liste des Anomalies Actives — Site **{site_actuel}**")

    # --- 1. RÉCUPÉRATION DES ANOMALIES ACTIVES ---
    try:
        res = supabase.table("anomalies") \
            .select("*") \
            .eq("site_id", site_actuel) \
            .neq("statut", "RESOLUE") \
            .order("created_at", desc=True) \
            .execute()
        
        anomalies_actives = res.data if res.data else []
    except Exception as e:
        st.error(f"Erreur de chargement des anomalies : {e}")
        anomalies_actives = []

    # --- 2. AFFICHAGE DANS UN CONTENEUR À HAUTEUR FIXE (ASCENSEUR) ---
    if anomalies_actives:
        st.info(f"🔔 **{len(anomalies_actives)} anomalie(s) active(s)** sur ce site.")
        
        # Hauteur bloquée à 320px : l'écran ne s'allonge plus vers le bas !
        with st.container(height=320):
            for ano in anomalies_actives:
                crit = ano.get("criticite", "MOYENNE")
                badge = "🔴" if crit in ["CRITIQUE", "ELEVEE"] else "🟠"
                
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"{badge} **[{ano['reference']}] {ano['titre']}** `({ano['statut']})`")
                    st.write(f"└ {ano['description']}")
                    st.caption(f"Signale par : **{ano['cree_par']}** | Priorite : **{crit}**")
                
                with col_btn:
                    if role in ["habilite", "charge_surete"]:
                        if st.button("✅ Résoudre", key=f"btn_res_{ano['id']}", use_container_width=True):
                            supabase.table("anomalies").update({"statut": "RESOLUE"}).eq("id", ano["id"]).execute()
                            st.toast("Anomalie marquée comme résolue !", icon="✅")
                            st.rerun()
                st.markdown("---")
    else:
        st.success("✅ Aucune anomalie signalée sur ce site. Tout est nominal !")

    st.markdown("---")

    # --- 3. FORMULAIRE DE DÉCLARATION (RESERVÉ ADMIN / HABILITÉ) ---
    if role in ["habilite", "charge_surete"]:
        st.subheader("➕ Déclarer une nouvelle anomalie (Admin / Habilité)")

        with st.form("form_add_anomalie", clear_on_submit=True):
            titre = st.text_input("Titre de l'anomalie *", placeholder="Ex: Lampadaire HS parking P2, Véhicule hors site...")
            
            col_c, col_st = st.columns(2)
            with col_c:
                criticite = st.selectbox("Niveau de priorité *", ["FAIBLE", "MOYENNE", "ELEVEE", "CRITIQUE"])
            with col_st:
                statut_init = st.selectbox("Statut initial", ["EN_COURS", "ATTENTE_PRESTATAIRE"])

            description = st.text_area("Détails complémentaires *", placeholder="Précisez la localisation, l'impact sûreté...")

            submitted = st.form_submit_button("💾 Enregistrer l'anomalie site", use_container_width=True)

            if submitted:
                if not titre.strip() or not description.strip():
                    st.error("Le titre et la description sont obligatoires.")
                else:
                    ano_ref = generate_id("ANO")
                    payload = {
                        "reference": ano_ref,
                        "site_id": site_actuel,
                        "titre": titre,
                        "description": description,
                        "criticite": criticite,
                        "statut": statut_init,
                        "cree_par": agent_nom
                    }
                    try:
                        supabase.table("anomalies").insert(payload).execute()
                        st.success(f"Anomalie **{ano_ref}** enregistrée !")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur d'enregistrement : {e}")
    else:
        st.info("ℹ️ *Seuls les chargés de sûreté et personnes habilitées peuvent déclarer ou clôturer des anomalies.*")
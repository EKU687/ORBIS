import sys
from pathlib import Path
import datetime
import zoneinfo
import streamlit as st
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

# Fuseau horaire Nouvelle-Calédonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


def generate_id(prefix: str) -> str:
    """Génère un identifiant horodaté unique basé sur l'heure locale NC."""
    now = get_now_nc()
    return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"


def show():
    st.title("⚠️ Anomalies & Points de Vigilance Site")

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get("user_profile", {"full_name": "Éric KUTER", "role": "agent"})
    
    raw_role = user_info.get("role") or st.session_state.get("role", "agent")
    agent_nom = user_info.get("full_name") or st.session_state.get("full_name", "Agent")

    # Normalisation du rôle
    role_clean = str(raw_role).strip().lower()

    # Rôles habilités à déclarer / résoudre les anomalies
    roles_privilegies = ["habilite", "charge_surete", "admin", "super_admin"]
    est_autorise = role_clean in roles_privilegies

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
        
        with st.container(height=320):
            for ano in anomalies_actives:
                crit = ano.get("criticite", "MOYENNE")
                badge = "🔴" if crit in ["CRITIQUE", "ELEVEE"] else "🟠"
                
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"{badge} **[{ano['reference']}] {ano['titre']}** `({ano['statut']})`")
                    st.write(f"└ {ano['description']}")
                    st.caption(f"Signalé par : **{ano['cree_par']}** | Priorité : **{crit}**")
                
                with col_btn:
                    if est_autorise:
                        if st.button("✅ Résoudre", key=f"btn_res_{ano['id']}", use_container_width=True):
                            try:
                                supabase.table("anomalies").update({"statut": "RESOLUE"}).eq("id", ano["id"]).execute()
                                st.toast("Anomalie marquée comme résolue !", icon="✅")
                                st.rerun()
                            except Exception as err:
                                st.error(f"Erreur lors de la résolution : {err}")
                st.markdown("---")
    else:
        st.success("✅ Aucune anomalie signalée sur ce site. Tout est nominal !")

    st.markdown("---")

    # --- 3. FORMULAIRE DE DÉCLARATION (RÉSERVÉ ADMIN / SUPERVISION / HABILITÉ) ---
    if est_autorise:
        st.subheader("➕ Déclarer une nouvelle anomalie (Admin / Supervision / Habilité)")

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
        st.info("ℹ️ *Seuls les chargés de sûreté, administrateurs et personnes habilitées peuvent déclarer ou clôturer des anomalies.*")
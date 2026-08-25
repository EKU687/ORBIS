import sys
from pathlib import Path
import datetime
import uuid
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase


def get_or_create_vacation_id(site_id: str, agent_nom: str) -> str:
    if st.session_state.get("vacation_id"):
        return st.session_state["vacation_id"]

    try:
        res = (
            supabase.table("vacations")
            .select("id")
            .eq("site_id", site_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            vac_id = res.data[0]["id"]
            st.session_state["vacation_id"] = vac_id
            return vac_id
    except Exception:
        pass

    new_id = str(uuid.uuid4())
    payload_vacation = {
        "id": new_id,
        "site_id": site_id,
        "agent_nom": agent_nom,
        "statut": "OUVERTE",
        "created_at": datetime.datetime.now().isoformat()
    }
    try:
        supabase.table("vacations").insert(payload_vacation).execute()
        st.session_state["vacation_id"] = new_id
        return new_id
    except Exception:
        return new_id


def show():
    st.title("✍️ Enregistrement Visiteur Imprévu")
    st.caption("Saisie rapide des demandes d'accès spontanées au poste de garde.")

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get("user_profile", {"full_name": "Éric KUTER"})
    agent_connecte = user_info["full_name"]

    if "visiteurs_presents" not in st.session_state:
        st.session_state["visiteurs_presents"] = {}
    if "visiteurs_imprevus_enregistres" not in st.session_state:
        st.session_state["visiteurs_imprevus_enregistres"] = []

    vac_id = get_or_create_vacation_id(site_actuel, agent_connecte)

    # FILTER DES BADGES DISPONIBLES (ANTI-DOUBLON GLOBAL)
    badges_occupes = [info["badge"] for info in st.session_state["visiteurs_presents"].values()]
    tous_badges = [f"V.{i:03d}" for i in range(1, 31)]
    badges_disponibles = ["Sélectionner un badge..."] + [b for b in tous_badges if b not in badges_occupes]

    with st.form("form_visiteur_imprevu", clear_on_submit=True):
        col_nom, col_org, col_hote = st.columns([1.5, 1.5, 2])
        with col_nom:
            nom_visiteur = st.text_input("Nom & Prénom du visiteur *", placeholder="Ex: DUPONT Jean")
        with col_org:
            organisme = st.text_input("Société / Organisme", placeholder="Ex: OPT, Privé, etc.")
        with col_hote:
            agent_referent = st.text_input("Agent référent / Hôte demandé *", placeholder="Ex: Olivier PAIMAN")

        st.markdown("---")
        col_badge, col_dec = st.columns([2, 2])
        with col_badge:
            badge_sel = st.selectbox("Badge Visiteur attribué (si accepté) :", badges_disponibles)
        with col_dec:
            accord_hote = st.radio(
                "Accord de l'agent référent :",
                ["⏳ En attente de confirmation", "✅ ACCEPTÉ", "❌ REFUSÉ"],
                horizontal=True
            )

        btn_valider = st.form_submit_button("💾 Enregistrer la décision", type="primary", use_container_width=True)

    if btn_valider:
        if not nom_visiteur.strip() or not agent_referent.strip():
            st.error("⚠️ Les champs 'Nom du visiteur' et 'Agent référent' sont obligatoires.")
        elif accord_hote == "⏳ En attente de confirmation":
            st.warning("⚠️ Veuillez contacter l'agent référent pour valider son accord.")
        elif accord_hote == "✅ ACCEPTÉ" and badge_sel == "Sélectionner un badge...":
            st.error("⚠️ Un badge doit être sélectionné pour un visiteur autorisé sur site.")
        else:
            now_dt = datetime.datetime.now()
            now_iso = now_dt.isoformat()
            ref_time = now_dt.strftime("%Y%m%d-%H%M%S")
            key_visiteur = f"{nom_visiteur.upper()}_{agent_referent.upper()}_IMP"

            if accord_hote == "❌ REFUSÉ":
                payload_mc = {
                    "reference": f"REF-VIS-REFUSE-{ref_time}",
                    "vacation_id": vac_id,
                    "site_id": site_actuel,
                    "agent_nom": agent_connecte,
                    "horodatage": now_iso,
                    "type_evenement": "VISITEUR",
                    "description": f"Refus d'accès : Visiteur imprévu {nom_visiteur.upper()} ({organisme or 'N/A'}) refoulé. Refusé par {agent_referent}.",
                    "actions_menees": "Visiteur informé et invité à reprendre rendez-vous."
                }
                try:
                    supabase.table("mc_evenements").insert(payload_mc).execute()
                    st.warning(f"🚫 Accès refusé consigné en Main Courante pour {nom_visiteur}.")
                except Exception as e:
                    st.error(f"Erreur enregistrement MC : {e}")

            elif accord_hote == "✅ ACCEPTÉ":
                st.session_state["visiteurs_presents"][key_visiteur] = {
                    "badge": badge_sel,
                    "nom": nom_visiteur.upper(),
                    "hote": agent_referent,
                    "type": "IMPREVU"
                }
                st.session_state["visiteurs_imprevus_enregistres"].append({
                    "key": key_visiteur,
                    "nom": nom_visiteur.upper(),
                    "organisme": organisme or "N/A",
                    "hote": agent_referent,
                    "badge": badge_sel,
                    "heure_arrivee": now_dt.strftime("%H:%M")
                })

                payload_mc = {
                    "reference": f"REF-VIS-IMP-IN-{ref_time}",
                    "vacation_id": vac_id,
                    "site_id": site_actuel,
                    "agent_nom": agent_connecte,
                    "horodatage": now_iso,
                    "type_evenement": "VISITEUR",
                    "description": f"Arrivée visiteur imprévu : {nom_visiteur.upper()} ({organisme or 'N/A'}) - Badge {badge_sel}. Visite autorisée par {agent_referent}.",
                    "actions_menees": "Accord obtenu, badge remis et entrée autorisée."
                }
                try:
                    supabase.table("mc_evenements").insert(payload_mc).execute()
                    st.toast(f"Entrée de {nom_visiteur} enregistrée avec le Badge {badge_sel} !", icon="✅")
                except Exception as e:
                    st.error(f"Erreur enregistrement MC : {e}")
import sys
from pathlib import Path
import datetime
import uuid
import zoneinfo
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

# Fuseau horaire Nouvelle-Calédonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


@st.cache_data(ttl=300)
def fetch_hotes_referents_list() -> list[str]:
    """
    Récupère la liste unifiée des hôtes (Agents Publics + Prestataires)
    depuis Supabase pour alimenter le menu déroulant.
    """
    hotes = []

    # 1. Chargement des Agents Publics
    try:
        res_agents = (
            supabase.table("Agents_Publics")
            .select("nom, prenom")
            .order("nom")
            .execute()
        )
        if res_agents.data:
            for ag in res_agents.data:
                nom = str(ag.get("nom") or "").strip().upper()
                prenom = str(ag.get("prenom") or "").strip().capitalize()
                if nom:
                    hotes.append(f"{nom} {prenom} (Agent Public)")
    except Exception as e:
        st.warning(f"⚠️ Chargement Agents_Publics impossible : {e}")

    # 2. Chargement des Prestataires
    try:
        res_presta = (
            supabase.table("Prestataires")
            .select("nom, prenom")
            .order("nom")
            .execute()
        )
        if res_presta.data:
            for pr in res_presta.data:
                nom = str(pr.get("nom") or "").strip().upper()
                prenom = str(pr.get("prenom") or "").strip().capitalize()
                if nom:
                    hotes.append(f"{nom} {prenom} (Prestataire)")
    except Exception as e:
        st.warning(f"⚠️ Chargement Prestataires impossible : {e}")

    # Tri par ordre alphabétique sans doublons
    hotes_tries = sorted(list(set(hotes)))
    return ["Sélectionner un hôte / agent référent..."] + hotes_tries


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
        "created_at": get_now_nc().isoformat(),
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

    # FILTRE DES BADGES DISPONIBLES (ANTI-DOUBLON GLOBAL)
    badges_occupes = [
        info["badge"] for info in st.session_state["visiteurs_presents"].values()
    ]
    tous_badges = [f"V.{i:03d}" for i in range(1, 31)]
    badges_disponibles = ["Sélectionner un badge..."] + [
        b for b in tous_badges if b not in badges_occupes
    ]

    # Charger la liste dynamique des hôtes référents depuis la BDD
    liste_hotes = fetch_hotes_referents_list()

    with st.form("form_visiteur_imprevu", clear_on_submit=True):
        col_nom, col_org, col_hote = st.columns([1.5, 1.5, 2])
        
        with col_nom:
            nom_visiteur = st.text_input(
                "Nom & Prénom du visiteur *", placeholder="Ex: DUPONT Jean"
            )
        
        with col_org:
            organisme = st.text_input(
                "Société / Organisme", placeholder="Ex: OPT, Privé, etc."
            )
        
        with col_hote:
            agent_referent_sel = st.selectbox(
                "Agent référent / Hôte demandé *",
                options=liste_hotes,
                index=0,
            )

        st.markdown("---")
        col_badge, col_dec = st.columns([2, 2])
        
        with col_badge:
            badge_sel = st.selectbox(
                "Badge Visiteur attribué (si accepté) :", badges_disponibles
            )
        
        with col_dec:
            accord_hote = st.radio(
                "Accord de l'agent référent :",
                ["⏳ En attente de confirmation", "✅ ACCEPTÉ", "❌ REFUSÉ"],
                horizontal=True,
            )

        btn_valider = st.form_submit_button(
            "💾 Enregistrer la décision", type="primary", use_container_width=True
        )

    if btn_valider:
        hote_valide = (
            agent_referent_sel != "Sélectionner un hôte / agent référent..."
        )

        if not nom_visiteur.strip() or not hote_valide:
            st.error(
                "⚠️ Les champs 'Nom du visiteur' et 'Agent référent' sont obligatoires."
            )
        elif accord_hote == "⏳ En attente de confirmation":
            st.warning(
                "⚠️ Veuillez contacter l'agent référent pour valider son accord."
            )
        elif accord_hote == "✅ ACCEPTÉ" and badge_sel == "Sélectionner un badge...":
            st.error(
                "⚠️ Un badge doit être sélectionné pour un visiteur autorisé sur site."
            )
        else:
            now_nc = get_now_nc()
            now_iso = now_nc.isoformat()
            ref_time = now_nc.strftime("%Y%m%d-%H%M%S")
            agent_referent = agent_referent_sel
            key_visiteur = f"{nom_visiteur.upper()}_{agent_referent.upper()}_IMP"

            if accord_hote == "❌ REFUSÉ":
                payload_mc = {
                    "reference": f"REF-VIS-REFUSE-{ref_time}",
                    "vacation_id": vac_id,
                    "site_id": site_actuel,
                    "agent_nom": agent_connecte,
                    "horodatage": now_iso,
                    "type_evenement": "VISITEUR",
                    "description": (
                        f"Refus d'accès : Visiteur imprévu {nom_visiteur.upper()}"
                        f" ({organisme or 'N/A'}) refoulé. Refusé par {agent_referent}."
                    ),
                    "actions_menees": (
                        "Visiteur informé et invité à reprendre rendez-vous."
                    ),
                }
                try:
                    supabase.table("mc_evenements").insert(payload_mc).execute()
                    st.warning(
                        f"🚫 Accès refusé consigné en Main Courante pour {nom_visiteur}."
                    )
                except Exception as e:
                    st.error(f"Erreur enregistrement MC : {e}")

            elif accord_hote == "✅ ACCEPTÉ":
                st.session_state["visiteurs_presents"][key_visiteur] = {
                    "badge": badge_sel,
                    "nom": nom_visiteur.upper(),
                    "hote": agent_referent,
                    "type": "IMPREVU",
                }
                st.session_state["visiteurs_imprevus_enregistres"].append({
                    "key": key_visiteur,
                    "nom": nom_visiteur.upper(),
                    "organisme": organisme or "N/A",
                    "hote": agent_referent,
                    "badge": badge_sel,
                    "heure_arrivee": now_nc.strftime("%H:%M"),
                })

                payload_mc = {
                    "reference": f"REF-VIS-IMP-IN-{ref_time}",
                    "vacation_id": vac_id,
                    "site_id": site_actuel,
                    "agent_nom": agent_connecte,
                    "horodatage": now_iso,
                    "type_evenement": "VISITEUR",
                    "description": (
                        f"Arrivée visiteur imprévu : {nom_visiteur.upper()}"
                        f" ({organisme or 'N/A'}) - Badge {badge_sel}. Visite autorisée par"
                        f" {agent_referent}."
                    ),
                    "actions_menees": (
                        "Accord obtenu, badge remis et entrée autorisée."
                    ),
                }
                try:
                    supabase.table("mc_evenements").insert(payload_mc).execute()
                    st.toast(
                        f"Entrée de {nom_visiteur} enregistrée avec le Badge {badge_sel} !",
                        icon="✅",
                    )
                except Exception as e:
                    st.error(f"Erreur enregistrement MC : {e}")
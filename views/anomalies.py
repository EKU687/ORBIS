import datetime
from pathlib import Path
import sys
import zoneinfo
import pandas as pd
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


def generate_id(prefix: str) -> str:
    """Génère un identifiant horodaté unique basé sur l'heure locale NC."""
    now = get_now_nc()
    return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"


def show():
    st.title("🚨 Anomalies & Consignes Générales du Site")

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get(
        "user_profile", {"full_name": "Éric KUTER", "role": "agent"}
    )

    raw_role = user_info.get("role") or st.session_state.get("role", "agent")
    agent_nom = user_info.get("full_name") or st.session_state.get("full_name", "Agent")

    # Normalisation du rôle
    role_clean = str(raw_role).strip().lower()

    # Rôles habilités à déclarer / résoudre les anomalies et consignes
    roles_privilegies = ["habilite", "charge_surete", "admin", "super_admin"]
    est_autorise = role_clean in roles_privilegies

    # --- ONGLETS DE CONSULTATION (ANOMALIES VS CONSIGNES GÉNÉRALES) ---
    tab_ano, tab_csg = st.tabs(
        [
            "🚨 Anomalies Actives",
            "📌 Consignes Générales Site",
        ]
    )

    # ------------------------------------------------------------------
    # ONGLET 1 : ANOMALIES ACTIVES (DYSFONCTIONNEMENTS)
    # ------------------------------------------------------------------
    with tab_ano:
        try:
            res_ano = (
                supabase.table("anomalies")
                .select("*")
                .eq("site_id", site_actuel)
                .neq("statut", "RESOLUE")
                .order("created_at", desc=True)
                .execute()
            )
            anomalies_actives = res_ano.data if res_ano.data else []
        except Exception as e:
            st.error(f"Erreur de chargement des anomalies : {e}")
            anomalies_actives = []

        if anomalies_actives:
            st.info(
                f"🔔 **{len(anomalies_actives)} anomalie(s) active(s)** sur le"
                f" site **{site_actuel}**."
            )

            with st.container(height=320):
                for ano in anomalies_actives:
                    crit = ano.get("criticite", "MOYENNE")
                    badge = "🔴" if crit in ["CRITIQUE", "ELEVEE"] else "🟠"

                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(
                            f"{badge} **[{ano['reference']}] {ano['titre']}**"
                            f" `({ano['statut']})`"
                        )
                        st.write(f"└ {ano['description']}")
                        st.caption(
                            f"Signalé par : **{ano['cree_par']}** | Priorité :"
                            f" **{crit}**"
                        )

                    with col_btn:
                        if est_autorise:
                            if st.button(
                                "✅ Résoudre",
                                key=f"btn_res_{ano['id']}",
                                use_container_width=True,
                            ):
                                try:
                                    supabase.table("anomalies").update(
                                        {"statut": "RESOLUE"}
                                    ).eq("id", ano["id"]).execute()
                                    st.toast(
                                        "Anomalie marquée comme résolue !",
                                        icon="✅",
                                    )
                                    st.rerun()
                                except Exception as err:
                                    st.error("Erreur lors de la résolution :" f" {err}")
                    st.markdown("---")
        else:
            st.success(f"✅ Aucune anomalie signalée sur le site **{site_actuel}**.")

    # ------------------------------------------------------------------
    # ONGLET 2 : CONSIGNES GÉNÉRALES SITE (POUR TOUS LES AGENTS)
    # ------------------------------------------------------------------
    with tab_csg:
        now_iso = get_now_nc().isoformat()
        try:
            res_csg = (
                supabase.table("consignes")
                .select("*")
                .eq("site_id", site_actuel)
                .eq("statut", "ACTIVE")
                .gte("fin_at", now_iso)
                .order("created_at", desc=True)
                .execute()
            )
            raw_consignes = res_csg.data if res_csg.data else []

            # Filtrage des consignes générales (destinataires = ["TOUS"])
            consignes_generales = [
                c
                for c in raw_consignes
                if "TOUS" in [str(d).upper() for d in c.get("destinataires", [])]
            ]
        except Exception as e:
            st.error(f"Erreur de chargement des consignes générales : {e}")
            consignes_generales = []

        if consignes_generales:
            st.info(
                f"📌 **{len(consignes_generales)} consigne(s) générale(s)"
                f" active(s)** sur le site **{site_actuel}**."
            )

            with st.container(height=320):
                for csg in consignes_generales:
                    prio = csg.get("priorite", "NORMALE")
                    badge = "🔴 URGENT" if prio == "URGENTE" else "🔵 GENERAL"

                    st.markdown(f"**{badge} [{csg['reference']}] {csg['titre']}**")
                    st.write(f"└ {csg['description']}")
                    st.caption(
                        f"Publiée par : **{csg['cree_par']}** | Fin de"
                        f" validité : **{csg['fin_at'][:10]}**"
                    )
                    st.markdown("---")
        else:
            st.success(
                f"✅ Aucune consigne générale active pour le site"
                f" **{site_actuel}**."
            )

    st.markdown("---")

    # --- 3. FORMULAIRE DE DÉCLARATION UNIFIÉ (ADMIN / SUPERVISION / HABILITÉ) ---
    if est_autorise:
        st.subheader("➕ Déclarer un élément (Anomalie ou Consigne Générale)")

        with st.form("form_add_element", clear_on_submit=True):
            col_type, col_prio = st.columns([1.5, 1])
            with col_type:
                type_element = st.selectbox(
                    "Type d'enregistrement *",
                    [
                        "🚨 Anomalie (Dysfonctionnement / Matériel)",
                        "📌 Consigne Générale (Instruction Permanente Site)",
                    ],
                )
            with col_prio:
                criticite = st.selectbox(
                    "Niveau de priorité / Urgence *",
                    ["FAIBLE", "MOYENNE", "ELEVEE", "CRITIQUE"],
                )

            titre = st.text_input(
                "Titre de l'enregistrement *",
                placeholder="Ex: Portail Ouest coincé / Rappel : Port du badge obligatoire...",
            )

            description = st.text_area(
                "Détails & Instructions complémentaires *",
                placeholder="Saisissez tous les détails utiles...",
            )

            submitted = st.form_submit_button(
                "💾 Enregistrer l'élément site", use_container_width=True
            )

            if submitted:
                if not titre.strip() or not description.strip():
                    st.error("Le titre et la description sont obligatoires.")
                else:
                    now_dt = get_now_nc()

                    # CAS 1 : ENREGISTREMENT D'UNE ANOMALIE
                    if "Anomalie" in type_element:
                        ano_ref = generate_id("ANO")
                        payload_ano = {
                            "reference": ano_ref,
                            "site_id": site_actuel,
                            "titre": titre,
                            "description": description,
                            "criticite": criticite,
                            "statut": "EN_COURS",
                            "cree_par": agent_nom,
                        }
                        try:
                            supabase.table("anomalies").insert(payload_ano).execute()
                            st.success(
                                f"Anomalie **{ano_ref}** enregistrée avec" " succès !"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur d'enregistrement de l'anomalie : {e}")

                    # CAS 2 : ENREGISTREMENT D'UNE CONSIGNE GÉNÉRALE
                    else:
                        csg_ref = generate_id("CSG")
                        fin_validite = (
                            now_dt + datetime.timedelta(days=30)
                        ).isoformat()

                        payload_csg = {
                            "reference": csg_ref,
                            "site_id": site_actuel,
                            "titre": titre,
                            "description": description,
                            "priorite": criticite,
                            "statut": "ACTIVE",
                            "destinataires": ["TOUS"],
                            "debut_at": now_dt.isoformat(),
                            "fin_at": fin_validite,
                            "cree_par": agent_nom,
                        }
                        try:
                            supabase.table("consignes").insert(payload_csg).execute()
                            st.success(
                                f"Consigne générale **{csg_ref}** enregistrée"
                                " avec succès !"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error("Erreur d'enregistrement de la consigne :" f" {e}")
    else:
        st.info(
            "ℹ️ *Seuls les chargés de sûreté, administrateurs et personnes"
            " habilitées peuvent déclarer ou clôturer des éléments.*"
        )

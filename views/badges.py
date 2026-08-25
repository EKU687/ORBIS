import datetime
from pathlib import Path
import sys
import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase


def format_date_fr(date_str: str) -> str:
    if not date_str:
        return "Non renseignée"
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y à %H:%M")
    except Exception:
        return str(date_str)


@st.cache_data(ttl=60)
def get_referentiel_personnes() -> dict:
    """Récupère la liste des agents publics et des prestataires depuis Supabase."""
    data = {"AGENT": [], "PRESTATAIRE": []}

    # 1. Chargement des Agents Publics
    try:
        res_agents = (
            supabase.table("Agents_Publics")
            .select("id, id_ident, nom, prenom")
            .order("nom", desc=False)
            .execute()
        )
        if res_agents.data:
            for a in res_agents.data:
                ident = a.get("id_ident") or "N/A"
                data["AGENT"].append(
                    {
                        "id": a.get("id"),
                        "nom": (a.get("nom") or "").upper(),
                        "prenom": (a.get("prenom") or "").capitalize(),
                        "societe": "GNC (Agent Public)",
                        "display": f"👤 {a.get('nom', '').upper()} {a.get('prenom', '').capitalize()} (ID: {ident})",
                    }
                )
    except Exception:
        pass

    # 2. Chargement des Prestataires
    try:
        res_prest = (
            supabase.table("Prestataires")
            .select("id, id_ident, nom, prenom")
            .order("nom", desc=False)
            .execute()
        )
        if res_prest.data:
            for p in res_prest.data:
                ident = p.get("id_ident") or "N/A"
                data["PRESTATAIRE"].append(
                    {
                        "id": p.get("id"),
                        "nom": (p.get("nom") or "").upper(),
                        "prenom": (p.get("prenom") or "").capitalize(),
                        "societe": "Prestataire Extérieur",
                        "display": f"🪪 {p.get('nom', '').upper()} {p.get('prenom', '').capitalize()} (ID: {ident})",
                    }
                )
    except Exception:
        pass

    return data


def show():
    st.title("🏷️ Gestion des Badges Temporaires")
    st.caption(
        "Suivi des affectations et restitutions des badges de secours (T.001 à"
        " T.020)."
    )

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get("user_profile", {"full_name": "Éric KUTER"})
    agent_connecte = user_info["full_name"]

    # --- 1. RÉCUPÉRATION DES BADGES EN CIRCULATION ---
    try:
        res_actifs = (
            supabase.table("badges_temporaires")
            .select("*")
            .eq("site_id", site_actuel)
            .eq("statut", "EN_COURS")
            .order("remis_at", desc=True)
            .execute()
        )
        badges_en_cours = res_actifs.data if res_actifs.data else []
    except Exception as e:
        st.error(f"Erreur lors du chargement des badges : {e}")
        badges_en_cours = []

    # --- 2. BANDEAU KPI & VOYANT ALERTE ---
    nb_actifs = len(badges_en_cours)
    col_kpi1, col_kpi2 = st.columns([1, 2])

    with col_kpi1:
        if nb_actifs > 0:
            st.metric(
                "Badges non restitués",
                f"{nb_actifs} actif(s)",
                delta="⚠️ En circulation",
                delta_color="inverse",
            )
        else:
            st.metric(
                "Badges non restitués", "0 actif", delta="✅ Tous restitués"
            )

    with col_kpi2:
        if nb_actifs > 0:
            st.warning(
                f"⚠️ **{nb_actifs} badge(s) temporaire(s)** actuellement hors du"
                " PC Sécurité. Pensez à réclamer la restitution avant la fin"
                " de service."
            )
        else:
            st.success(
                "✅ Aucun badge temporaire en circulation sur le site. Tous"
                " les badges sont au râtelier."
            )

    st.markdown("---")

    tab_affectation, tab_retour, tab_historique = st.tabs([
        "➕ Affecter un Badge",
        f"📥 Restitutions en attente ({nb_actifs})",
        "📜 Historique du jour",
    ])

    # --- TAB 1 : FORMULAIRE D'AFFECTATION ---
    with tab_affectation:
        st.subheader("Attribution d'un badge temporaire")

        badges_occupes = [b["numero_badge"] for b in badges_en_cours]
        t_list = [f"T.{i:03d}" for i in range(1, 21)]
        dispo_list = [t for t in t_list if t not in badges_occupes]

        if not dispo_list:
            st.error(
                "⛔ Tous les badges temporaires (T.001 à T.020) sont"
                " actuellement attribués !"
            )
        else:
            c_type, c_badge = st.columns([1, 1])
            with c_type:
                type_b = st.radio(
                    "Type de bénéficiaire *",
                    ["AGENT", "PRESTATAIRE"],
                    horizontal=True,
                )
            with c_badge:
                num_badge = st.selectbox(
                    "N° de Badge Temporaire disponible *", dispo_list
                )

            referentiel = get_referentiel_personnes()
            liste_personnes = referentiel.get(type_b, [])

            if liste_personnes:
                options_dict = {p["display"]: p for p in liste_personnes}
                choix_pers = st.selectbox(
                    f"🔎 Rechercher l'{type_b.lower()} dans le référentiel :",
                    options=list(options_dict.keys()),
                    index=0,
                )
                selected_person = options_dict[choix_pers]
            else:
                selected_person = None
                st.warning(
                    f"Aucun {type_b.lower()} trouvé dans la base de données."
                )

            with st.form("form_remise_badge", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    nom = st.text_input(
                        "Nom *",
                        value=(
                            selected_person["nom"] if selected_person else ""
                        ),
                    )
                    prenom = st.text_input(
                        "Prénom *",
                        value=(
                            selected_person["prenom"] if selected_person else ""
                        ),
                    )
                with col2:
                    societe = st.text_input(
                        "Organisme / Société *",
                        value=(
                            selected_person["societe"]
                            if selected_person
                            else ""
                        ),
                    )
                    obs = st.text_input(
                        "Observation / Motif",
                        placeholder="Ex: Oubli de badge personnel",
                    )

                submitted = st.form_submit_button(
                    "💾 Enregistrer la remise de badge",
                    use_container_width=True,
                )

                if submitted:
                    if not nom.strip() or not prenom.strip():
                        st.error(
                            "Le nom et le prénom du bénéficiaire sont"
                            " obligatoires."
                        )
                    else:
                        payload = {
                            "site_id": site_actuel,
                            "numero_badge": num_badge,
                            "beneficiaire_nom": nom.upper(),
                            "beneficiaire_prenom": prenom.capitalize(),
                            "societe_organisme": societe if societe else "GNC",
                            "type_beneficiaire": type_b,
                            "remis_par": agent_connecte,
                            "remis_at": datetime.datetime.now().isoformat(),
                            "statut": "EN_COURS",
                            "observations": obs,
                        }
                        try:
                            supabase.table("badges_temporaires").insert(
                                payload
                            ).execute()
                            st.toast(
                                f"Badge {num_badge} remis à {nom.upper()}"
                                f" {prenom.capitalize()} !",
                                icon="🏷️",
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur d'enregistrement : {e}")

    # --- TAB 2 : RESTITUTION DES BADGES EN CIRCULATION ---
    with tab_retour:
        st.subheader("Liste des badges actuellement en circulation")

        if badges_en_cours:
            with st.container(height=380):
                for b in badges_en_cours:
                    col_info, col_btn = st.columns([3, 1])
                    with col_info:
                        st.markdown(
                            f"🏷️ **Badge : `{b['numero_badge']}`** —"
                            f" **{b['beneficiaire_nom']}"
                            f" {b['beneficiaire_prenom']}**"
                            f" (`{b['societe_organisme']}`)"
                        )
                        st.caption(
                            f"Remis par **{b['remis_par']}** le"
                            f" {format_date_fr(b['remis_at'])} | Motif :"
                            f" *{b.get('observations') or 'N/A'}*"
                        )
                    with col_btn:
                        if st.button(
                            "✅ Restitué",
                            key=f"btn_ret_{b['id']}",
                            use_container_width=True,
                            type="primary",
                        ):
                            now = datetime.datetime.now().isoformat()
                            try:
                                supabase.table("badges_temporaires").update({
                                    "statut": "RESTITUE",
                                    "restitue_a": agent_connecte,
                                    "restitue_at": now,
                                }).eq("id", b["id"]).execute()

                                st.toast(
                                    f"Badge {b['numero_badge']} réintégré au"
                                    " râtelier !",
                                    icon="✅",
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(
                                    f"Erreur lors de la restitution : {e}"
                                )
                    st.markdown("---")
        else:
            st.info("Aucun badge temporaire à restituer pour le moment.")

    # --- TAB 3 : HISTORIQUE DU JOUR ---
    with tab_historique:
        try:
            res_hist = (
                supabase.table("badges_temporaires")
                .select("*")
                .eq("site_id", site_actuel)
                .order("remis_at", desc=True)
                .limit(50)
                .execute()
            )
            if res_hist.data:
                df = pd.DataFrame(res_hist.data)
                df_display = df[[
                    "numero_badge",
                    "beneficiaire_nom",
                    "beneficiaire_prenom",
                    "societe_organisme",
                    "statut",
                    "remis_at",
                    "restitue_at",
                ]].copy()
                df_display.columns = [
                    "Badge",
                    "Nom",
                    "Prénom",
                    "Société",
                    "Statut",
                    "Remis le",
                    "Restitué le",
                ]

                df_display["Remis le"] = df_display["Remis le"].apply(
                    format_date_fr
                )
                df_display["Restitué le"] = df_display["Restitué le"].apply(
                    format_date_fr
                )

                st.dataframe(df_display, use_container_width=True)
            else:
                st.info("Aucun historique disponible.")
        except Exception as e:
            st.error(f"Erreur de chargement de l'historique : {e}")
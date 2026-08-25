import datetime
import streamlit as st
from utils.db_client import supabase

DELAI_VALIDE_JOURS = 90


def calculer_statut_permis(
    date_dernier_controle: str, autorise_manual: bool
) -> tuple[str, datetime.date | None, bool]:
    """Calcule le statut exact du permis de conduire à l'instant T.

    Retourne:
        - statut_str: 'VALIDE', 'AVERTISSEMENT', 'EXPIRE' ou 'NON_CONTROLE'
        - dt_expiration: Date exacte d'expiration du contrôle (dt_ctrl + 90
          jours)
        - est_autorise: Booléen final d'autorisation d'utilisation des
          véhicules
    """
    if not date_dernier_controle:
        return "NON_CONTROLE", None, False

    try:
        dt_ctrl = datetime.date.fromisoformat(str(date_dernier_controle))
        dt_expiration = dt_ctrl + datetime.timedelta(days=DELAI_VALIDE_JOURS)
        aujourdhui = datetime.date.today()

        jours_restants = (dt_expiration - aujourdhui).days
        est_expire = jours_restants < 0

        # Condition cumulée : Pas expiré + Autorisation manuelle cochée
        est_autorise = (not est_expire) and bool(autorise_manual)

        if est_expire:
            statut = "EXPIRE"
        elif jours_restants <= 15:
            statut = "AVERTISSEMENT"
        else:
            statut = "VALIDE"

        return statut, dt_expiration, est_autorise

    except Exception:
        return "ERREUR", None, False


def show():
    st.title("🚗 Gestion des Permis de Conduire & Habilitations Véhicules")
    st.caption(
        "Contrôle réglementaire des autorisations de conduite des véhicules de"
        " service (Validité : 90 jours max)."
    )

    # 1. Vérification du rôle utilisateur pour les autorisations d'édition (Nouvelle Nomenclature)
    user_info = st.session_state.get("user_profile", {})
    role = str(user_info.get("role", "")).upper().strip()

    # 🎯 Rôles autorisés à éditer et valider les permis de conduire
    ROLES_HABILITES_PERMIS = [
        "HABI_ORBIS",
        "CHARGE_SURETE",
        "ADMIN",
        "COS",
        "HABILITE",
    ]
    est_admin_ou_habilite = role in ROLES_HABILITES_PERMIS

    # 2. Chargement des Agents Publics avec jointures Directions & Services
    try:
        res = (
            supabase.table("Agents_Publics")
            .select(
                "id, id_ident, nom, prenom, id_direction, id_service,"
                " permis_conduire, date_dernier_controle_permis,"
                " autorise_vehicule, Directions(sigle_direction),"
                " Services(sigle_service)"
            )
            .eq("statut", "ACTIF")
            .order("nom", desc=False)
            .execute()
        )
        agents = res.data or []
    except Exception as e:
        st.error(f"❌ Erreur de lecture de la base de données : {e}")
        return

    if not agents:
        st.info("ℹ️ Aucun agent public au statut ACTIF recensé dans la base.")
        return

    # 3. Calcul des compteurs globaux (Metrics)
    total_agents = len(agents)
    nb_autorises = 0
    nb_expires = 0

    for ag in agents:
        statut, _, est_autorise = calculer_statut_permis(
            ag.get("date_dernier_controle_permis"),
            ag.get("autorise_vehicule", False),
        )
        if est_autorise:
            nb_autorises += 1
        if statut in ["EXPIRE", "NON_CONTROLE"]:
            nb_expires += 1

    # Cartes d'indicateurs visuels
    c_m1, c_m2, c_m3 = st.columns(3)
    c_m1.metric("👥 Agents Publics Actifs", total_agents)
    c_m2.metric(
        "🟢 Autorisation Véhicule Valide",
        nb_autorises,
        delta=f"{(nb_autorises / total_agents) * 100:.0f}% des effectifs",
    )
    c_m3.metric(
        "🔴 Contrôles Dépassés / Suspendus", nb_expires, delta_color="inverse"
    )

    st.markdown("---")

    # 4. Barre de recherche et filtrage
    col_search, col_filter = st.columns([3, 1.5])
    with col_search:
        recherche = (
            st.text_input(
                "🔍 Rechercher un agent (Nom, Prénom, Service) :",
                placeholder="Ex: KUTER, DINUM...",
            )
            .strip()
            .upper()
        )

    with col_filter:
        filtre_statut = st.selectbox(
            "Filtrer par état :",
            ["Tous", "🟢 Valides uniquement", "🔴 Expirés / Suspendus"],
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # 5. Boucle d'affichage du registre
    aujourdhui_dt = datetime.date.today()

    for ag in agents:
        nom_complet = (
            f"{ag.get('nom', '').upper()} {ag.get('prenom', '').title()}"
        )

        # Extraction propre des jointures Supabase
        dir_dict = ag.get("Directions") or {}
        serv_dict = ag.get("Services") or {}
        sigle_dir = dir_dict.get("sigle_direction", "")
        sigle_serv = serv_dict.get("sigle_service", "")

        service = sigle_serv or sigle_dir or "Non précisé"
        id_ident = ag.get("id_ident", "N/A")

        date_ctrl_str = ag.get("date_dernier_controle_permis")
        autorise_manual = ag.get("autorise_vehicule", False)

        statut_permis, dt_exp, est_autorise = calculer_statut_permis(
            date_ctrl_str, autorise_manual
        )

        # Application du filtre de recherche
        if recherche and (
            recherche not in nom_complet and recherche not in service.upper()
        ):
            continue

        # Application du filtre par statut
        if filtre_statut == "🟢 Valides uniquement" and not est_autorise:
            continue
        if filtre_statut == "🔴 Expirés / Suspendus" and est_autorise:
            continue

        with st.container(border=True):
            col_info, col_dates, col_action = st.columns([2.5, 2.2, 2.3])

            # BLOC 1 : IDENTITÉ & STATUT
            with col_info:
                st.markdown(f"👤 **{nom_complet}** (`{id_ident}`)")
                st.caption(f"🏢 Service : **{service}**")

                if est_autorise:
                    st.success("🟢 **AUTORISÉ** à conduire les véhicules")
                else:
                    st.error("🔴 **SUSPENDU** / Non autorisé")

            # BLOC 2 : DATES & CALCUL DU RAPPEL
            with col_dates:
                if date_ctrl_str:
                    dt_ctrl = datetime.date.fromisoformat(str(date_ctrl_str))
                    st.markdown(
                        "📅 **Dernier contrôle :**"
                        f" `{dt_ctrl.strftime('%d/%m/%Y')}`"
                    )
                    st.markdown(
                        "⏳ **Expiration contrôle :**"
                        f" `{dt_exp.strftime('%d/%m/%Y')}`"
                    )

                    jours_restants = (dt_exp - aujourdhui_dt).days
                    if jours_restants > 0:
                        st.caption(
                            f"ℹ️ Il reste **{jours_restants} jour(s)** de"
                            " validité."
                        )
                    else:
                        st.caption(
                            "🚨 Contrôle périmé depuis"
                            f" **{abs(jours_restants)} jour(s)** !"
                        )
                else:
                    st.warning("⚠️ **Aucun contrôle enregistré**")

                if statut_permis == "EXPIRE":
                    st.error("🚨 Contrôle dépassé (> 90 jours)")
                elif statut_permis == "AVERTISSEMENT":
                    st.warning("⚠️ Renouvellement nécessaire (< 15 jours)")

            # BLOC 3 : FORMULAIRE ADMIN / HABILITÉ (HABI_ORBIS AUTORISÉ)
            with col_action:
                if est_admin_ou_habilite:
                    st.markdown("**⚙️ Mise à jour du Contrôle :**")

                    # Bouton d'action rapide : Revalidation immédiate à la date du jour
                    if st.button(
                        "✅ Valider contrôle AUJOURD'HUI",
                        key=f"btn_quick_{ag['id']}",
                        use_container_width=True,
                        type="primary",
                    ):
                        try:
                            supabase.table("Agents_Publics").update({
                                "date_dernier_controle_permis": (
                                    aujourdhui_dt.isoformat()
                                ),
                                "autorise_vehicule": True,
                                "permis_conduire": True,
                            }).eq("id", ag["id"]).execute()

                            st.toast(
                                f"Permis de {nom_complet} revalidé pour 90"
                                " jours !",
                                icon="✅",
                            )
                            st.rerun()
                        except Exception as err:
                            st.error(f"Erreur de mise à jour : {err}")

                    with st.expander("🛠️ Ajustement Manuel Date / Verrou"):
                        new_autorise = st.checkbox(
                            "Autorisation véhicules",
                            value=autorise_manual,
                            key=f"chk_{ag['id']}",
                        )

                        date_defaut = (
                            datetime.date.fromisoformat(str(date_ctrl_str))
                            if date_ctrl_str
                            else aujourdhui_dt
                        )
                        new_date_ctrl = st.date_input(
                            "Date de contrôle :",
                            value=date_defaut,
                            format="DD/MM/YYYY",  # Format Français
                            key=f"date_{ag['id']}",
                        )

                        if st.button(
                            "💾 Enregistrer ajustement",
                            key=f"btn_save_{ag['id']}",
                            use_container_width=True,
                        ):
                            try:
                                supabase.table("Agents_Publics").update({
                                    "date_dernier_controle_permis": (
                                        new_date_ctrl.isoformat()
                                    ),
                                    "autorise_vehicule": new_autorise,
                                    "permis_conduire": True,
                                }).eq("id", ag["id"]).execute()

                                st.toast(
                                    f"Modifications enregistrées pour"
                                    f" {nom_complet} !",
                                    icon="💾",
                                )
                                st.rerun()
                            except Exception as err:
                                st.error(f"Erreur de sauvegarde : {err}")
                else:
                    st.caption("🔒 Consultation uniquement (Rôle Agent)")
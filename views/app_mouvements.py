import datetime
from pathlib import Path
import sys
import uuid
import zoneinfo
import streamlit as st

# 🔧 CORRECTIF D'IMPORTATION RACINE
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 📦 IMPORTS DU PROJET
from utils.db_client import supabase

# Fuseau horaire Nouvelle-Calédonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


# ✉️ IMPORT DIRECT DE LA FONCTION DANS utils/email_sender.py
try:
    from utils.email_sender import envoyer_notification_passage_poste_securite

    HAS_EMAIL_SENDER = True
except Exception as e:
    HAS_EMAIL_SENDER = False

# Style CSS pour les cartes de comptage
st.markdown(
    """
    <style>
    .metric-box-arrivals {
        background-color: #e8f4f8;
        border-radius: 10px;
        padding: 15px;
        border-left: 6px solid #0288d1;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        text-align: center;
    }
    .metric-box-departures {
        background-color: #fde8e8;
        border-radius: 10px;
        padding: 15px;
        border-left: 6px solid #d32f2f;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        text-align: center;
    }
    .metric-number {
        font-size: 32px;
        font-weight: bold;
        margin: 5px 0;
    }
    .metric-arrivals-number { color: #0288d1; }
    .metric-departures-number { color: #d32f2f; }
    </style>
""",
    unsafe_allow_html=True,
)


def notifier_surete_passage(
    site: str,
    nom_personne: str,
    organisme: str,
    heure: str,
    type_piece: str,
    num_piece: str,
    agent_garde: str,
):
    """Envoie une alerte email au Chargé de Sûreté via utils.email_sender."""
    if not HAS_EMAIL_SENDER:
        return

    try:
        envoyer_notification_passage_poste_securite(
            site=site,
            nom_personne=nom_personne,
            organisme=organisme,
            heure=heure,
            type_piece=type_piece,
            num_piece=num_piece,
            agent_garde=agent_garde,
        )
    except Exception as err:
        print(f"⚠️ Erreur lors de l'envoi de l'email : {err}")


def fetch_sites_from_bdd() -> dict[str, dict]:
    """Récupère tous les sites depuis Supabase avec leur UUID et code_site."""
    sites_map = {}
    try:
        res = (
            supabase.table("Sites")
            .select("id, code_site, nom_site")
            .execute()
        )
        if res.data:
            for row in res.data:
                code = row.get("code_site", "").strip().upper()
                if code:
                    sites_map[code] = {
                        "uuid": str(row.get("id")),
                        "nom": row.get("nom_site") or code,
                    }
    except Exception as e:
        st.error(f"Erreur de lecture BDD Sites : {e}")

    if not sites_map:
        sites_map = {
            "DINUM": {"uuid": None, "nom": "SITE OUEMO"},
            "DOUMER": {"uuid": None, "nom": "SITE DOUMER"},
        }
    return sites_map


def fetch_mouvements_jour(
    site_code: str, site_uuid: str, date_cible: datetime.date
):
    """Interroge Agents_Publics et Prestataires pour récupérer :
    - Les ARRIVÉES EN ATTENTE (Statuts: IMPRIME, A_LIVRER, EN_COURS_NEDAP)
    - Les DÉPARTS PRÉVUS (Statuts: ACTIF, A_LIVRER, IMPRIME)
    """
    date_str = date_cible.isoformat()
    arrivants = []
    departs = []

    if not site_uuid:
        return arrivants, departs

    STATUTS_ARRIVEE = ["IMPRIME", "A_LIVRER", "EN_COURS_NEDAP"]
    STATUTS_DEPART = ["ACTIF", "A_LIVRER", "IMPRIME"]
    statuts_globaux = list(set(STATUTS_ARRIVEE + STATUTS_DEPART))

    try:
        res_dir = (
            supabase.table("Directions")
            .select("sigle_direction, code_direction")
            .eq("id_site", site_uuid)
            .execute()
        )

        directions_du_site = set()
        if res_dir.data:
            for d in res_dir.data:
                if d.get("sigle_direction"):
                    directions_du_site.add(d["sigle_direction"].upper())
                if d.get("code_direction"):
                    directions_du_site.add(d["code_direction"].upper())

        # Agents Publics
        res_agents = (
            supabase.table("Agents_Publics")
            .select("*")
            .in_("statut", statuts_globaux)
            .execute()
        )

        if res_agents.data:
            for ag in res_agents.data:
                ag_site_id = str(ag.get("id_site", ""))
                ag_dir = str(
                    ag.get("direction") or ag.get("service") or ""
                ).upper()
                ag_statut = ag.get("statut", "")

                match_site = (ag_site_id == str(site_uuid)) or (
                    ag_dir in directions_du_site
                )

                if match_site:
                    nom_complet = (
                        f"{ag.get('nom', '').upper()} {ag.get('prenom', '')}".strip()
                    )

                    if (ag.get("date_debut_validite") == date_str) and (ag_statut in STATUTS_ARRIVEE):
                        arrivants.append({
                            "id": ag.get("id"),
                            "id_ident": ag.get("id_ident"),
                            "nom": nom_complet,
                            "organisme": ag.get("direction")
                            or ag.get("organisme")
                            or "Agent Public (GNC)",
                            "type": "Agent Public",
                            "type_badge": ag.get("type_badge", "N/A"),
                            "niveau_hab": ag.get(
                                "niveau_habilitation", "Niveau 1"
                            ),
                            "service_str": ag.get("service")
                            or ag.get("direction")
                            or "Agent Public",
                            "source": "Agents_Publics",
                        })

                    if (ag.get("date_fin_validite") == date_str) and (ag_statut in STATUTS_DEPART):
                        departs.append({
                            "id": ag.get("id"),
                            "id_ident": ag.get("id_ident"),
                            "nom": nom_complet,
                            "organisme": ag.get("direction")
                            or ag.get("organisme")
                            or "Agent Public (GNC)",
                            "badge": ag.get("type_badge", "Standard"),
                            "source": "Agents_Publics",
                        })
    except Exception as e:
        st.warning(f"Note (Agents_Publics) : {e}")

    # Prestataires
    try:
        res_prest = (
            supabase.table("Prestataires")
            .select("*")
            .in_("statut", statuts_globaux)
            .execute()
        )

        if res_prest.data:
            for pr in res_prest.data:
                sites_prest = pr.get("id_sites") or []
                pr_site_id = str(pr.get("id_site", ""))
                pr_statut = pr.get("statut", "")

                match_site = (str(site_uuid) in sites_prest) or (
                    pr_site_id == str(site_uuid)
                )

                if match_site:
                    nom_complet = (
                        f"{pr.get('nom', '').upper()} {pr.get('prenom', '')}".strip()
                    )

                    if (pr.get("date_debut_validite") == date_str) and (pr_statut in STATUTS_ARRIVEE):
                        arrivants.append({
                            "id": pr.get("id"),
                            "id_ident": pr.get("id_ident"),
                            "nom": nom_complet,
                            "organisme": pr.get("agent_referent_gnc")
                            or "Prestataire Externe",
                            "type": "Prestataire",
                            "type_badge": pr.get("type_badge", "N/A"),
                            "niveau_hab": pr.get(
                                "niveau_habilitation", "Niveau 1"
                            ),
                            "service_str": pr.get("societe")
                            or "Prestataire Externe",
                            "source": "Prestataires",
                        })

                    if (pr.get("date_fin_prestation") == date_str) and (pr_statut in STATUTS_DEPART):
                        departs.append({
                            "id": pr.get("id"),
                            "id_ident": pr.get("id_ident"),
                            "nom": nom_complet,
                            "organisme": pr.get("agent_referent_gnc")
                            or "Prestataire Externe",
                            "badge": pr.get("type_badge", "Temporaire"),
                            "source": "Prestataires",
                        })
    except Exception as e:
        st.warning(f"Note (Prestataires) : {e}")

    return arrivants, departs


@st.fragment(run_every=300)
def render_mouvements_console(
    site_actuel: str, site_uuid: str, date_cible: datetime.date, site_cle: str
):
    now_str = get_now_nc().strftime("%H:%M:%S")
    st.info(
        f"🕒 **Console Active** | Auto-synchro BDD : {now_str} | Site :"
        f" **{site_actuel}**"
    )

    est_admin = site_cle in ["ADMIN", "SUPER_ADMIN"]

    liste_arrivants, liste_departs = fetch_mouvements_jour(
        site_actuel, site_uuid, date_cible
    )

    nb_arrivants = len(liste_arrivants)
    nb_departs = len(liste_departs)

    st.markdown("---")

    col_count_arr, col_count_dep = st.columns([1, 1])

    with col_count_arr:
        st.markdown(
            f"""
            <div class="metric-box-arrivals">
                <span style="font-size: 16px; font-weight: 600; color: #555;">📥 ARRIVÉES EN ATTENTE ({site_actuel})</span>
                <div class="metric-number metric-arrivals-number">{nb_arrivants}</div>
                <small style="color: #666;">Fil d'Ariane des arrivées du jour</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_count_dep:
        st.markdown(
            f"""
            <div class="metric-box-departures">
                <span style="font-size: 16px; font-weight: 600; color: #555;">🚨 BADGES À RÉCUPÉRER ({site_actuel})</span>
                <div class="metric-number metric-departures-number">{nb_departs}</div>
                <small style="color: #666;">Restitutions d'accès attendues avant départ</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    label_tab_arr = f"📥 ARRIVÉES EN ATTENTE ({nb_arrivants})"
    label_tab_dep = f"📤 DÉPARTS / BADGES À RÉCUPÉRER ({nb_departs})"

    tab_arrivants, tab_departs = st.tabs([label_tab_arr, label_tab_dep])
    agent_connecte = f"Agent PC ({site_actuel})"

    # --- TAB 1 : ARRIVÉES ---
    with tab_arrivants:
        st.subheader(
            f"📋 Nouveaux Arrivants du {date_cible.strftime('%d/%m/%Y')} sur"
            f" {site_actuel}"
        )

        if liste_arrivants:
            for item in liste_arrivants:
                titre_accordeon = (
                    f"👤 {item['nom']} — {item['type']} ({item['organisme']}) |"
                    f" Service: {item.get('service_str', 'Non défini')}"
                )

                key_passage_valide = f"passage_valide_{item['id']}"
                key_surete_valide = f"surete_valide_{item['id']}"

                passage_deja_enregistre = st.session_state.get(
                    key_passage_valide, False
                )
                surete_deja_enregistree = st.session_state.get(
                    key_surete_valide, False
                )

                with st.expander(titre_accordeon, expanded=False):
                    c_info1, c_info2, c_info3 = st.columns(3)
                    with c_info1:
                        st.markdown(
                            "🏢 **Service / Entité :**"
                            f" `{item.get('service_str', 'Non défini')}`"
                        )
                    with c_info2:
                        st.markdown(
                            "👤 **Responsable interne :**"
                            f" `{item.get('organisme', 'Non renseigné')}`"
                        )
                    with c_info3:
                        st.markdown(
                            "🔑 **Habilitation AEOS :**"
                            f" `{item.get('niveau_hab', 'Niveau 1')}`"
                        )

                    st.markdown("---")

                    st.markdown("##### 🛂 1. Contrôle d'Identité (Agent de Garde)")
                    f_col1, f_col2 = st.columns(2)

                    with f_col1:
                        type_piece = st.selectbox(
                            "Type de pièce contrôlée * :",
                            [
                                "Carte Nationale d'Identité",
                                "Passeport",
                                "Permis de conduire",
                                "Carte Professionnelle / Badge Officiel",
                                "Titre de Séjour",
                            ],
                            key=f"tp_{item['id']}",
                            disabled=passage_deja_enregistre,
                        )

                    with f_col2:
                        num_piece = st.text_input(
                            "N° de la pièce d'identité * :",
                            placeholder="Ex: 123456789",
                            key=f"num_{item['id']}",
                            disabled=passage_deja_enregistre,
                        )

                    libelle_bouton_p1 = (
                        "🔒 Passage déjà consigné au PC Sécurité"
                        if passage_deja_enregistre
                        else "📝 Enregistrer le passage au poste de garde"
                    )

                    btn_agent_passage = st.button(
                        libelle_bouton_p1,
                        key=f"btn_pass_{item['id']}",
                        type="secondary" if passage_deja_enregistre else "primary",
                        use_container_width=True,
                        disabled=passage_deja_enregistre,
                    )

                    if btn_agent_passage and not passage_deja_enregistre:
                        if not num_piece.strip():
                            st.error("⚠️ Saisissez le N° de pièce d'identité !")
                        else:
                            now_dt = get_now_nc()
                            heure_passage = now_dt.strftime("%H:%M")

                            st.session_state[key_passage_valide] = True

                            notifier_surete_passage(
                                site=site_actuel,
                                nom_personne=item["nom"],
                                organisme=item["organisme"],
                                heure=heure_passage,
                                type_piece=type_piece,
                                num_piece=num_piece.strip(),
                                agent_garde=agent_connecte,
                            )

                            st.success(
                                f"🎉 Passage de **{item['nom']}**"
                                f" enregistré à **{heure_passage}** !"
                            )
                            st.toast(
                                "Passage consigné & Sûreté notifiée ✉️",
                                icon="✅",
                            )
                            st.rerun()

                    st.markdown("---")

                    st.markdown(
                        "##### ⚙️ 2. Check-List de Conformité & Émargement"
                        " (Chargé de Sûreté / Admin)"
                    )

                    desactiver_p2 = (not est_admin) or surete_deja_enregistree

                    with st.container(border=True):
                        chk1, chk2, chk3, chk4 = st.columns(4)
                        with chk1:
                            st.checkbox(
                                "📷 Photo conforme",
                                key=f"photo_{item['id']}",
                                disabled=desactiver_p2,
                            )
                        with chk2:
                            st.checkbox(
                                "🚨 Consignes Incendie",
                                key=f"inc_{item['id']}",
                                disabled=desactiver_p2,
                            )
                        with chk3:
                            st.checkbox(
                                "🪪 Permis de conduire",
                                key=f"perm_{item['id']}",
                                disabled=desactiver_p2,
                            )
                        with chk4:
                            st.checkbox(
                                "🚲 Accès Parking Vélo",
                                key=f"velo_{item['id']}",
                                disabled=desactiver_p2,
                            )

                    if not est_admin:
                        st.caption(
                            "🔒 **Information Poste de Garde :** La check-list"
                            " et l'émargement final sont réservés au Chargé de Sûreté."
                        )
                    else:
                        st.markdown("<br>", unsafe_allow_html=True)

                        libelle_bouton_p2 = (
                            "🔒 Émargement Sûreté déjà validé"
                            if surete_deja_enregistree
                            else f"🏁 Valider l'Émargement Sûreté pour {item['nom']}"
                        )

                        btn_cloturer_final = st.button(
                            libelle_bouton_p2,
                            key=f"btn_cloture_{item['id']}",
                            type="secondary" if surete_deja_enregistree else "primary",
                            use_container_width=True,
                            disabled=surete_deja_enregistree,
                        )

                        if btn_cloturer_final and not surete_deja_enregistree:
                            st.session_state[key_surete_valide] = True
                            st.success(
                                f"🏁 Émargement Sûreté validé pour **{item['nom']}** !"
                            )
                            st.toast("Émargement verrouillé", icon="🔒")
                            st.rerun()

        else:
            st.info(
                f"ℹ️ Aucune arrivée prévue pour le site {site_actuel} à la date"
                f" du {date_cible.strftime('%d/%m/%Y')}."
            )

    # --- TAB 2 : DÉPARTS ---
    with tab_departs:
        st.subheader(
            "🚪 Fin d'Accès & Restitution de Badges du"
            f" {date_cible.strftime('%d/%m/%Y')} sur {site_actuel}"
        )

        if liste_departs:
            for item in liste_departs:
                st.markdown(
                    f"#### 👤 {item['nom']} — Organisme/Ref : {item['organisme']}"
                )
                col_dep_info, col_dep_action = st.columns([3, 1.5])

                with col_dep_info:
                    st.warning(
                        "⚠️ **Consigne :** Récupérer le badge temporaire/accès"
                        f" (Type: **{item['badge']}**) avant départ définitif."
                    )

                with col_dep_action:
                    key_dep_valide = f"depart_valide_{item['id']}"
                    dep_enregistre = st.session_state.get(
                        key_dep_valide, False
                    )

                    if st.button(
                        "🔒 Badge Récupéré & Validé"
                        if dep_enregistre
                        else "🚪 Valider Départ & Badge Récupéré",
                        key=f"btn_dep_{item['id']}",
                        type="secondary" if dep_enregistre else "primary",
                        use_container_width=True,
                        disabled=(not est_admin) or dep_enregistre,
                    ):
                        st.session_state[key_dep_valide] = True
                        st.toast("Départ validé !", icon="🚪")
                        st.rerun()
                st.markdown("---")
        else:
            st.info(
                "ℹ️ Aucun départ/fin d'accès prévu pour le site"
                f" {site_actuel} à la date du {date_cible.strftime('%d/%m/%Y')}."
            )


def show():
    """Point d'entrée principal pour le module Mouvements (Vues intégrées et Onglet dédié)."""
    st.title("🛡️ IDENTIS — Gestion des Mouvements Sécurité")
    st.caption("Console d'affichage permanent du Poste de Garde (Arrivées & Départs).")

    # 1. CHARGEMENT BDD SITES
    sites_dict = fetch_sites_from_bdd()
    codes_valides = list(sites_dict.keys())

    # 2. DÉTECTION DU SITE (query_params URL ou Session State ORBIS)
    query_params = st.query_params
    site_param = query_params.get("site", None)

    user_info = st.session_state.get("user_profile", {})
    raw_role = user_info.get("role") or st.session_state.get("role", "AGENT_SECU")
    role_clean = str(raw_role).upper().strip()

    if site_param:
        site_cle = str(site_param).upper().strip()
    else:
        site_cle = st.session_state.get("site_actif", "DINUM")

    col_site, col_date, col_refresh = st.columns([2, 1.5, 1])

    with col_site:
        if site_cle in ["ADMIN", "SUPER_ADMIN"] or role_clean in ["ADMIN", "SUPER_ADMIN", "CHARGE_SURETE"]:
            code_selectionne = st.selectbox(
                "📍 Site de sécurité (Admin) :",
                options=codes_valides,
                format_func=lambda x: f"{x} — {sites_dict[x]['nom']}",
            )
            site_actuel = code_selectionne
        elif site_cle in codes_valides:
            site_actuel = site_cle
            nom_complet = sites_dict[site_actuel]["nom"]
            st.text_input(
                "📍 Site du Poste :",
                value=f"{site_actuel} ({nom_complet})",
                disabled=True,
            )
        else:
            site_actuel = st.session_state.get("site_actif", "DINUM")
            st.info(f"📍 Site actif : **{site_actuel}**")

    site_uuid = sites_dict.get(site_actuel, {}).get("uuid")

    with col_date:
        date_selectionnee = st.date_input(
            "📅 Date contrôlée :", value=get_now_nc().date()
        )

    with col_refresh:
        st.write("")
        if st.button("🔄 Rafraîchir", use_container_width=True):
            st.rerun()

    # APPEL DU FRAGMENT AUTO-RAFRAÎCHI
    render_mouvements_console(
        site_actuel, site_uuid, date_selectionnee, site_cle
    )


if __name__ == "__main__":
    show()
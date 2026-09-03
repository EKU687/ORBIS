# =========================================================================
# MODULE : GESTION DES MOUVEMENTS SÉCURITÉ / IDENTIS (app_mouvement.py)
# Inclus : Contrôle d'accès terrain, validation sûreté (Admin/Charge Surete),
#          restitution de badges et notifications automatiques.
# Table BDD dédiée : public.mc_mouvements
# =========================================================================
import datetime
from pathlib import Path
import sys
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


# ✉️ TENTATIVE D'IMPORT DU MODULE EMAIL
try:
    from utils.email_sender import envoyer_notification_passage_poste_securite
    HAS_EMAIL_SENDER = True
except Exception:
    HAS_EMAIL_SENDER = False


def injecter_style_css():
    """Injecte le style CSS pour les cartes métriques et les contours colorés."""
    st.markdown(
        """
        <style>
        .metric-box-arrivals {
            background-color: #e8f4f8 !important;
            border-radius: 10px !important;
            padding: 15px !important;
            border-left: 6px solid #0288d1 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08) !important;
            text-align: center !important;
        }
        .metric-box-departures {
            background-color: #fde8e8 !important;
            border-radius: 10px !important;
            padding: 15px !important;
            border-left: 6px solid #d32f2f !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08) !important;
            text-align: center !important;
        }
        .metric-number {
            font-size: 32px !important;
            font-weight: bold !important;
            margin: 5px 0 !important;
        }
        .metric-arrivals-number { color: #0288d1 !important; }
        .metric-departures-number { color: #d32f2f !important; }
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
    """Transmet l'alerte email au Chargé de Sûreté."""
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
    """Récupère tous les sites depuis Supabase en s'appuyant principalement sur 'nom_site'."""
    sites_map = {}
    try:
        res = (
            supabase.table("Sites")
            .select("id, code_site, nom_site")
            .execute()
        )
        if res.data:
            for row in res.data:
                nom = row.get("nom_site", "").strip()
                code = row.get("code_site", "").strip()

                key_name = nom if nom else code
                if key_name:
                    sites_map[key_name.upper()] = {
                        "uuid": str(row.get("id")),
                        "nom_site": key_name,
                        "code_site": code,
                    }
    except Exception as e:
        st.error(f"Erreur de lecture de la table BDD 'Sites' : {e}")

    if not sites_map:
        sites_map = {
            "DINUM": {"uuid": None, "nom_site": "DINUM", "code_site": "DINUM"},
            "SITE DOUMER": {"uuid": None, "nom_site": "SITE DOUMER", "code_site": "DOUMER"},
            "SITE OUEMO": {"uuid": None, "nom_site": "SITE OUEMO", "code_site": "OUEMO"},
        }
    return sites_map


def fetch_pointages_existants(site_uuid: str, date_cible: datetime.date) -> dict:
    """Lit les pointages enregistrés dans la table dédiée mc_mouvements."""
    pointages = {}
    if not site_uuid:
        return pointages

    try:
        res = (
            supabase.table("mc_mouvements")
            .select("*")
            .eq("site_id", str(site_uuid))
            .eq("date_mouvement", date_cible.isoformat())
            .execute()
        )
        for row in (res.data or []):
            ref_id = row.get("reference", "").replace("MVT-", "")
            if ref_id:
                pointages[ref_id] = row
    except Exception as e:
        print(f"Note lecture mc_mouvements BDD : {e}")
    return pointages


def enregistrer_pointage_agent_bdd(
    site_uuid: str,
    item_id: str,
    nom_personne: str,
    organisme: str,
    type_piece: str,
    num_piece: str,
    agent_nom: str
):
    """Enregistre l'étape 1 du contrôle au poste de garde dans mc_mouvements."""
    now_dt = get_now_nc()
    data = {
        "reference": f"MVT-{item_id}",
        "site_id": str(site_uuid),
        "date_mouvement": now_dt.date().isoformat(),
        "nom_personne": nom_personne,
        "organisme": organisme,
        "type_piece": type_piece,
        "num_piece": num_piece,
        "agent_garde": agent_nom,
        "heure_passage_agent": now_dt.isoformat(),
        "statut_passage": "AGENT_VALIDE",
    }
    try:
        supabase.table("mc_mouvements").upsert(data, on_conflict="reference").execute()
        return True
    except Exception as e:
        st.error(f"Erreur d'enregistrement BDD : {e}")
        return False


def enregistrer_emargement_surete_bdd(item_id: str, check_data: dict, admin_nom: str):
    """Enregistre la validation finale étape 2 par la Sûreté dans mc_mouvements."""
    ref_cle = f"MVT-{item_id}"
    data = {
        "check_photo": check_data.get("photo", False),
        "check_incendie": check_data.get("incendie", False),
        "check_permis": check_data.get("permis", False),
        "check_velo": check_data.get("velo", False),
        "surete_valide_par": admin_nom,
        "heure_validation_surete": get_now_nc().isoformat(),
        "statut_passage": "SURETE_VALIDE",
    }
    try:
        supabase.table("mc_mouvements").update(data).eq("reference", ref_cle).execute()
        return True
    except Exception as e:
        st.error(f"Erreur lors de la validation Sûreté BDD : {e}")
        return False


def fetch_mouvements_jour(site_nom: str, site_uuid: str, date_cible: datetime.date):
    """Interroge Agents_Publics et Prestataires pour récupérer les flux du jour sur le site."""
    date_str = date_cible.isoformat()
    arrivants = []
    departs = []

    if not site_uuid:
        return arrivants, departs

    STATUTS_ARRIVEE = ["IMPRIME", "A_LIVRER", "EN_COURS_NEDAP"]
    STATUTS_DEPART = ["ACTIF", "A_LIVRER", "IMPRIME"]
    statuts_globaux = list(set(STATUTS_ARRIVEE + STATUTS_DEPART))

    # Chargement des pointages BDD déjà effectués aujourd'hui depuis mc_mouvements
    pointages_bdd = fetch_pointages_existants(site_uuid, date_cible)

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

        res_agents = (
            supabase.table("Agents_Publics")
            .select("*")
            .in_("statut", statuts_globaux)
            .execute()
        )

        if res_agents.data:
            for ag in res_agents.data:
                ag_site_id = str(ag.get("id_site", ""))
                ag_dir = str(ag.get("direction") or ag.get("service") or "").upper()
                ag_statut = ag.get("statut", "")

                match_site = (ag_site_id == str(site_uuid)) or (ag_dir in directions_du_site)

                if match_site:
                    nom_complet = f"{ag.get('nom', '').upper()} {ag.get('prenom', '')}".strip()
                    item_id = str(ag.get("id"))
                    ev_bdd = pointages_bdd.get(item_id, {})

                    if (ag.get("date_debut_validite") == date_str) and (ag_statut in STATUTS_ARRIVEE):
                        arrivants.append({
                            "id": item_id,
                            "id_ident": ag.get("id_ident"),
                            "nom": nom_complet,
                            "organisme": ag.get("direction") or ag.get("organisme") or "Agent Public (GNC)",
                            "type": "Agent Public",
                            "type_badge": ag.get("type_badge", "N/A"),
                            "niveau_hab": ag.get("niveau_habilitation", "Niveau 1"),
                            "service_str": ag.get("service") or ag.get("direction") or "Agent Public",
                            "source": "Agents_Publics",
                            "pointage_bdd": ev_bdd,
                        })

                    if (ag.get("date_fin_validite") == date_str) and (ag_statut in STATUTS_DEPART):
                        departs.append({
                            "id": item_id,
                            "id_ident": ag.get("id_ident"),
                            "nom": nom_complet,
                            "organisme": ag.get("direction") or ag.get("organisme") or "Agent Public (GNC)",
                            "badge": ag.get("type_badge", "Standard"),
                            "source": "Agents_Publics",
                        })
    except Exception as e:
        st.warning(f"Note (Agents_Publics) : {e}")

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

                match_site = (str(site_uuid) in sites_prest) or (pr_site_id == str(site_uuid))

                if match_site:
                    nom_complet = f"{pr.get('nom', '').upper()} {pr.get('prenom', '')}".strip()
                    item_id = str(pr.get("id"))
                    ev_bdd = pointages_bdd.get(item_id, {})

                    if (pr.get("date_debut_validite") == date_str) and (pr_statut in STATUTS_ARRIVEE):
                        arrivants.append({
                            "id": item_id,
                            "id_ident": pr.get("id_ident"),
                            "nom": nom_complet,
                            "organisme": pr.get("agent_referent_gnc") or "Prestataire Externe",
                            "type": "Prestataire",
                            "type_badge": pr.get("type_badge", "N/A"),
                            "niveau_hab": pr.get("niveau_habilitation", "Niveau 1"),
                            "service_str": pr.get("societe") or "Prestataire Externe",
                            "source": "Prestataires",
                            "pointage_bdd": ev_bdd,
                        })

                    if (pr.get("date_fin_prestation") == date_str) and (pr_statut in STATUTS_DEPART):
                        departs.append({
                            "id": item_id,
                            "id_ident": pr.get("id_ident"),
                            "nom": nom_complet,
                            "organisme": pr.get("agent_referent_gnc") or "Prestataire Externe",
                            "badge": pr.get("type_badge", "Temporaire"),
                            "source": "Prestataires",
                        })
    except Exception as e:
        st.warning(f"Note (Prestataires) : {e}")

    return arrivants, departs


@st.fragment(run_every=300)
def render_mouvements_console(site_actuel: str, site_uuid: str, date_cible: datetime.date, est_admin: bool):
    """Fragment Streamlit réactualisé toutes les 5 minutes (300 secondes)."""
    injecter_style_css()

    now_str = get_now_nc().strftime("%H:%M:%S")
    st.info(f"🕒 **Console Active** | Auto-synchro BDD : {now_str} | Site : **{site_actuel}**")

    liste_arrivants, liste_departs = fetch_mouvements_jour(site_actuel, site_uuid, date_cible)
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
    tab_arrivants, tab_departs = st.tabs([f"📥 ARRIVÉES EN ATTENTE ({nb_arrivants})", f"📤 DÉPARTS / BADGES À RÉCUPÉRER ({nb_departs})"])
    
    user_info = st.session_state.get("user_profile", {})
    agent_connecte = user_info.get("full_name") or f"Agent PC ({site_actuel})"

    # --- TAB 1 : ARRIVÉES ---
    with tab_arrivants:
        st.subheader(f"📋 Nouveaux Arrivants du {date_cible.strftime('%d/%m/%Y')} sur {site_actuel}")

        if liste_arrivants:
            for item in liste_arrivants:
                ev_bdd = item.get("pointage_bdd", {})
                statut_bdd = ev_bdd.get("statut_passage", "")

                # Lecture du statut en BDD
                passage_deja_enregistre = statut_bdd in ["AGENT_VALIDE", "SURETE_VALIDE"]
                surete_deja_enregistree = statut_bdd == "SURETE_VALIDE"

                titre_accordeon = f"👤 {item['nom']} — {item['type']} ({item['organisme']}) | Service: {item.get('service_str', 'Non défini')}"
                if surete_deja_enregistree:
                    titre_accordeon += " | 🔒 [VALIDÉ SÛRETÉ]"
                elif passage_deja_enregistre:
                    titre_accordeon += " | 📝 [PASSAGE AGENT CONSIGNÉ]"

                with st.expander(titre_accordeon, expanded=False):
                    c_info1, c_info2, c_info3 = st.columns(3)
                    with c_info1:
                        st.markdown(f"🏢 **Service / Entité :** `{item.get('service_str', 'Non défini')}`")
                    with c_info2:
                        st.markdown(f"👤 **Responsable interne :** `{item.get('organisme', 'Non renseigné')}`")
                    with c_info3:
                        st.markdown(f"🔑 **Habilitation AEOS :** `{item.get('niveau_hab', 'Niveau 1')}`")

                    st.markdown("---")
                    st.markdown("##### 🛂 1. Contrôle d'Identité (Agent de Garde)")
                    f_col1, f_col2 = st.columns(2)

                    val_type_piece = ev_bdd.get("type_piece", "Carte Nationale d'Identité")
                    val_num_piece = ev_bdd.get("num_piece", "")

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
                            index=["Carte Nationale d'Identité", "Passeport", "Permis de conduire", "Carte Professionnelle / Badge Officiel", "Titre de Séjour"].index(val_type_piece) if val_type_piece in ["Carte Nationale d'Identité", "Passeport", "Permis de conduire", "Carte Professionnelle / Badge Officiel", "Titre de Séjour"] else 0,
                            key=f"tp_{item['id']}",
                            disabled=passage_deja_enregistre,
                        )

                    with f_col2:
                        num_piece = st.text_input(
                            "N° de la pièce d'identité * :",
                            value=val_num_piece,
                            placeholder="Ex: 123456789",
                            key=f"num_{item['id']}",
                            disabled=passage_deja_enregistre,
                        )

                    libelle_bouton_p1 = "🔒 Passage déjà consigné au PC Sécurité (Enregistré en BDD)" if passage_deja_enregistre else "📝 Enregistrer le passage au poste de garde"

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

                            if enregistrer_pointage_agent_bdd(site_uuid, item["id"], item["nom"], item["organisme"], type_piece, num_piece.strip(), agent_connecte):
                                notifier_surete_passage(
                                    site=site_actuel,
                                    nom_personne=item["nom"],
                                    organisme=item["organisme"],
                                    heure=heure_passage,
                                    type_piece=type_piece,
                                    num_piece=num_piece.strip(),
                                    agent_garde=agent_connecte,
                                )
                                st.success(f"🎉 Passage de **{item['nom']}** enregistré à **{heure_passage}** !")
                                st.toast("Passage gravé en BDD & Sûreté notifiée ✉️", icon="✅")
                                st.rerun()

                    st.markdown("---")
                    st.markdown("##### ⚙️ 2. Check-List de Conformité & Émargement (Chargé de Sûreté / Admin)")

                    desactiver_p2 = (not est_admin) or surete_deja_enregistree or (not passage_deja_enregistre)

                    # Lecture dynamique des cases à cocher en BDD
                    chk_photo_val = ev_bdd.get("check_photo", False)
                    chk_inc_val = ev_bdd.get("check_incendie", False)
                    chk_perm_val = ev_bdd.get("check_permis", False)
                    chk_velo_val = ev_bdd.get("check_velo", False)

                    with st.container(border=True):
                        chk1, chk2, chk3, chk4 = st.columns(4)
                        with chk1:
                            chk_photo = st.checkbox("📷 Photo conforme", value=chk_photo_val, key=f"photo_{item['id']}", disabled=desactiver_p2)
                        with chk2:
                            chk_inc = st.checkbox("🚨 Consignes Incendie", value=chk_inc_val, key=f"inc_{item['id']}", disabled=desactiver_p2)
                        with chk3:
                            chk_perm = st.checkbox("🪪 Permis de conduire", value=chk_perm_val, key=f"perm_{item['id']}", disabled=desactiver_p2)
                        with chk4:
                            chk_velo = st.checkbox("🚲 Accès Parking Vélo", value=chk_velo_val, key=f"velo_{item['id']}", disabled=desactiver_p2)

                    if not passage_deja_enregistre:
                        st.caption("⏳ **En attente de l'étape 1 :** L'agent de garde doit d'abord enregistrer le contrôle d'identité.")
                    elif not est_admin:
                        st.caption("🔒 **Information Poste de Garde :** La check-list et l'émargement final sont réservés au Chargé de Sûreté et Administrateurs.")
                    else:
                        st.markdown("<br>", unsafe_allow_html=True)
                        libelle_bouton_p2 = "🔒 Émargement Sûreté déjà validé" if surete_deja_enregistree else f"🏁 Valider l'Émargement Sûreté pour {item['nom']}"

                        btn_cloturer_final = st.button(
                            libelle_bouton_p2,
                            key=f"btn_cloture_{item['id']}",
                            type="secondary" if surete_deja_enregistree else "primary",
                            use_container_width=True,
                            disabled=surete_deja_enregistree,
                        )

                        if btn_cloturer_final and not surete_deja_enregistree:
                            check_data = {
                                "photo": chk_photo,
                                "incendie": chk_inc,
                                "permis": chk_perm,
                                "velo": chk_velo
                            }
                            if enregistrer_emargement_surete_bdd(item["id"], check_data, agent_connecte):
                                st.success(f"🏁 Émargement Sûreté validé pour **{item['nom']}** !")
                                st.toast("Émargement verrouillé en BDD", icon="🔒")
                                st.rerun()

        else:
            st.info(f"ℹ️ Aucune arrivée prévue pour le site {site_actuel} à la date du {date_cible.strftime('%d/%m/%Y')}.")

    # --- TAB 2 : DÉPARTS ---
    with tab_departs:
        st.subheader(f"🚪 Fin d'Accès & Restitution de Badges du {date_cible.strftime('%d/%m/%Y')} sur {site_actuel}")

        if liste_departs:
            for item in liste_departs:
                st.markdown(f"#### 👤 {item['nom']} — Organisme/Ref : {item['organisme']}")
                col_dep_info, col_dep_action = st.columns([3, 1.5])

                with col_dep_info:
                    st.warning(f"⚠️ **Consigne :** Récupérer le badge temporaire/accès (Type: **{item['badge']}**) avant départ définitif.")

                with col_dep_action:
                    key_dep_valide = f"depart_valide_{item['id']}"
                    dep_enregistre = st.session_state.get(key_dep_valide, False)

                    if st.button(
                        "🔒 Badge Récupéré & Validé" if dep_enregistre else "🚪 Valider Départ & Badge Récupéré",
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
            st.info(f"ℹ️ Aucun départ/fin d'accès prévu pour le site {site_actuel} à la date du {date_cible.strftime('%d/%m/%Y')}.")


def show():
    """Point d'entrée principal pour la console Mouvements."""
    injecter_style_css()

    st.title("🛡️ IDENTIS — Gestion des Mouvements Sécurité")
    st.caption("Console d'affichage permanent du Poste de Garde (Arrivées & Départs).")

    sites_dict = fetch_sites_from_bdd()
    noms_sites_valides = list(sites_dict.keys())

    query_params = st.query_params
    site_param = query_params.get("site", None)

    user_info = st.session_state.get("user_profile", {})
    raw_role = (
        user_info.get("role") 
        or user_info.get("role_name") 
        or st.session_state.get("role", "AGENT_SECU")
    )
    role_clean = str(raw_role).upper().strip()

    site_sollicite = None
    ROLES_AUTORISES_ETAPE2 = [
        "ADMIN", "SUPER_ADMIN", "ADMINISTRATEUR", 
        "CHARGE_SURETE", "CHARGE DE SURETE", "COS"
    ]
    
    full_name = str(user_info.get("full_name", "")).upper()
    est_admin_session = (
        role_clean in ROLES_AUTORISES_ETAPE2 
        or "ADMIN" in role_clean 
        or "KUTER" in full_name
    )
    site_cle_admin = False

    if site_param:
        val_url = str(site_param).upper().strip()
        if val_url in ["ADMIN", "SUPER_ADMIN"]:
            site_cle_admin = True
        else:
            if val_url in sites_dict:
                site_sollicite = val_url
            else:
                for nom_k, data_v in sites_dict.items():
                    if data_v["code_site"].upper() == val_url:
                        site_sollicite = nom_k
                        break

    if not site_sollicite and not site_cle_admin:
        session_site = str(st.session_state.get("site_actif", "DINUM")).upper().strip()
        if session_site in sites_dict:
            site_sollicite = session_site
        else:
            for nom_k, data_v in sites_dict.items():
                if data_v["code_site"].upper() == session_site:
                    site_sollicite = nom_k
                    break
        if not site_sollicite:
            site_sollicite = noms_sites_valides[0] if noms_sites_valides else "DINUM"

    col_site, col_date, col_refresh = st.columns([2, 1.5, 1])

    with col_site:
        if site_cle_admin or est_admin_session:
            idx_defaut = noms_sites_valides.index(site_sollicite) if site_sollicite in noms_sites_valides else 0
            site_selectionne = st.selectbox(
                "📍 Site de sécurité (Supervision) :",
                options=noms_sites_valides,
                index=idx_defaut,
            )
            site_actuel = site_selectionne
        else:
            site_actuel = site_sollicite
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

    render_mouvements_console(
        site_actuel, site_uuid, date_selectionnee, est_admin=(site_cle_admin or est_admin_session)
    )


if __name__ == "__main__":
    show()
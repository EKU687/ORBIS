# =========================================================================
# MODULE : MAIN COURANTE SERVICE TERRAIN (views/main_courante.py)
# Inclus : Vacation site, pop-up de prise de poste avec filtrage dynamique
#          des consignes (Globales & Ciblées par agent), émargement unique,
#          saisie d'événements, journal BDD et clôture de vacation.
# =========================================================================
import datetime
from pathlib import Path
import sys
import zoneinfo
import pandas as pd
import streamlit as st

# Fix pour assurer que Python trouve le dossier 'utils' depuis 'views'
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase
from utils.email_sender import send_alert_email

# Fuseau horaire Nouvelle-Calédonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


def generate_id(prefix: str) -> str:
    """Génère un identifiant horodaté unique basé sur l'heure locale NC (ex: VAC-20260826-085500)."""
    now = get_now_nc()
    return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"


def get_active_vacation(site_id: str, agent_nom: str):
    """Récupère la vacation active en cours depuis Supabase pour le site."""
    try:
        response = (
            supabase.table("vacations")
            .select("*")
            .eq("site_id", site_id)
            .in_("statut", ["EN_COURS", "OUVERTE"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        st.error(f"Erreur lors de la récupération de la vacation : {e}")
        return None


def fetch_consignes_cibles_agent(
    site_id: str, agent_login: str, user_role: str = "AGENT_SECU"
) -> list[dict]:
    """Récupère les consignes actives du site.

    - Pour un ADMIN / SUPERVISION : retourne TOUTES les consignes actives (Visibilité 360°).
    - Pour un AGENT : filtre (Consignes globales "TOUS" OU ciblées sur son login).
    """
    now_iso = get_now_nc().isoformat()
    try:
        res_csg = (
            supabase.table("consignes")
            .select("*")
            .eq("site_id", site_id)
            .eq("statut", "ACTIVE")
            .gte("fin_at", now_iso)
            .execute()
        )

        raw_consignes = res_csg.data if res_csg.data else []

        # Bypass pour les rôles de supervision / administration
        role_clean = str(user_role).upper().strip()
        ROLES_BYPASS = ["ADMIN", "SUPER_ADMIN", "CHARGE_SURETE", "COS"]

        if role_clean in ROLES_BYPASS:
            return raw_consignes  # 🎯 Visibilité totale pour l'Admin

        # Filtrage strict pour les agents de terrain
        consignes_valides = []
        agent_login_clean = str(agent_login).lower().strip()

        for csg in raw_consignes:
            destinataires = csg.get("destinataires") or ["TOUS"]
            dest_list = [str(d).lower().strip() for d in destinataires]

            if "tous" in dest_list or agent_login_clean in dest_list:
                consignes_valides.append(csg)

        return consignes_valides
    except Exception as e:
        print(f"⚠️ Erreur lors du chargement des consignes : {e}")
        return []


# --- FENÊTRE MODALE POP-UP AVEC ONGLETS & ÉMARGEMENT INTELLIGENT ---
@st.dialog("📋 CONSIGNES & ANOMALIES SITE", width="large")
def show_consignes_dialog(
    site_id: str,
    agent_connecte: str,
    consignes_actives: list,
    anomalies_actives: list,
):
    st.info(f"📍 **Site : {site_id}** | 👤 **Agent : {agent_connecte}**")
    st.caption("Veuillez prendre connaissance des informations relatives au site.")

    tab_cibles, tab_generales = st.tabs(
        [
            f"🎯 Consignes Ciblées ({len(consignes_actives)})",
            f"🚨 Anomalies & Consignes Générales ({len(anomalies_actives)})",
        ]
    )

    # ------------------------------------------------------------------
    # ONGLET 1 : CONSIGNES PARTICULIÈRES & CIBLÉES
    # ------------------------------------------------------------------
    with tab_cibles:
        with st.container(height=350):
            if consignes_actives:
                for csg in consignes_actives:
                    priorite = csg.get("priorite", "NORMALE")
                    badge_prio = "🔴 URGENT" if priorite == "URGENTE" else "🔵 CONSIGNE"

                    destinataires = csg.get("destinataires") or ["TOUS"]
                    is_cibles = "TOUS" not in [str(d).upper() for d in destinataires]
                    badge_cible = (
                        "🎯 (Spécifique Agent)" if is_cibles else "🌐 (Globale)"
                    )

                    st.markdown(
                        f"**{badge_prio} [{csg.get('reference', 'CSG')}]"
                        f" {csg.get('titre', '')} {badge_cible}**"
                    )
                    st.write(f"{csg.get('description', '')}")
                    st.caption(
                        f"📅 Valable jusqu'au {csg.get('fin_at', '')[:10]} |"
                        f" 👤 Rédigée par : {csg.get('cree_par', 'Admin')}"
                    )
                    st.markdown("---")
            else:
                st.success("✅ Aucune consigne particulière ciblée active.")

    # ------------------------------------------------------------------
    # ONGLET 2 : ANOMALIES & CONSIGNES GÉNÉRALES DU SITE
    # ------------------------------------------------------------------
    with tab_generales:
        with st.container(height=350):
            if anomalies_actives:
                for ano in anomalies_actives:
                    criticite = ano.get("criticite", "NORMALE")
                    badge_crit = (
                        "🔴 CRITIQUE"
                        if criticite in ["CRITIQUE", "ELEVEE"]
                        else "🟠 VIGILANCE"
                    )

                    st.markdown(
                        f"**{badge_crit} [{ano.get('reference', 'ANO')}]"
                        f" {ano.get('titre', '')}**"
                    )
                    st.write(f"{ano.get('description', '')}")
                    st.caption(
                        f"📍 Emplacement : {ano.get('localisation', 'Site')} |"
                        f" 🚨 Statut : {ano.get('statut', 'EN_COURS')}"
                    )
                    st.markdown("---")
            else:
                st.success("✅ Aucune anomalie globale signalée sur le site.")

    st.markdown("---")

    # 🎯 TEST DU CONTEXTE : La vacation est-elle déjà active ?
    active_vac = get_active_vacation(site_id, agent_connecte)

    if not active_vac:
        # === CAS A : PRISE DE POSTE (ÉMARGEMENT BDD OBLIGATOIRE) ===
        if st.button(
            "✅ J'émarge & je démarre mon service",
            type="primary",
            use_container_width=True,
        ):
            vac_ref = generate_id("VAC")
            now_dt = get_now_nc()
            now_iso = now_dt.isoformat()

            # 1. Création de la vacation dans Supabase
            payload_vac = {
                "reference": vac_ref,
                "site_id": site_id,
                "agent_nom": agent_connecte,
                "debut_at": now_iso,
                "statut": "EN_COURS",
            }

            vac_id_creee = None
            try:
                res_v = supabase.table("vacations").insert(payload_vac).execute()
                if res_v.data:
                    vac_id_creee = res_v.data[0].get("id")
            except Exception as e:
                st.error(f"Erreur création vacation : {e}")

            # 2. Inscription unique de l'Émargement dans le Journal de la Main Courante
            payload_emargement = {
                "reference": generate_id("EMG"),
                "vacation_id": vac_id_creee,
                "site_id": site_id,
                "agent_nom": agent_connecte,
                "horodatage": now_iso,
                "type_evenement": "Prise de consignes",
                "description": (
                    f"📋 Émargement Prise de Poste : Prise de connaissance"
                    f" validée pour {len(consignes_actives)} consigne(s) et"
                    f" {len(anomalies_actives)} anomalie(s)."
                ),
                "actions_menees": (
                    "Lecture et validation explicite de prise de poste sur"
                    " l'application ORBIS."
                ),
                "notified_authority": False,
            }

            try:
                supabase.table("mc_evenements").insert(payload_emargement).execute()
                st.toast(
                    f"Service démarré (`{vac_ref}`) & émargement enregistré !",
                    icon="🚀",
                )
            except Exception as err:
                print(f"Erreur enregistrement émargement : {err}")

            st.rerun()

    else:
        # === CAS B : SIMPLE CONSULTATION EN COURS DE VACATION (SANS ÉMARGEMENT DUPLIQUÉ) ===
        if st.button("✖️ Fermer la consultation", use_container_width=True):
            st.rerun()


# --- FENÊTRE MODALE POP-UP DE FIN DE POSTE & CLÔTURE DE VACATION ---
@st.dialog("🛑 CLÔTURE DU POSTE DE GARDE")
def show_fin_de_poste_dialog(vac_id: str, site_id: str, agent_nom: str):
    st.warning("⚠️ **Confirmation de fin de service**")
    st.write(
        "Êtes-vous sûr de vouloir clôturer officiellement la vacation en cours" " ?"
    )
    st.caption(
        "Cette action enregistrera l'événement de fin de poste et fermera le"
        " registre de cette vacation dans Supabase."
    )

    col_confirm, col_cancel = st.columns([1, 1])

    with col_confirm:
        if st.button(
            "✅ Clôturer la vacation", type="primary", use_container_width=True
        ):
            now_dt = get_now_nc()

            try:
                # 1. Mise à jour de la vacation en statut CLOTUREE
                if vac_id and len(str(vac_id)) == 36:
                    supabase.table("vacations").update(
                        {
                            "statut": "CLOTUREE",
                            "fin_at": now_dt.isoformat(),
                        }
                    ).eq("id", vac_id).execute()
                else:
                    supabase.table("vacations").update(
                        {
                            "statut": "CLOTUREE",
                            "fin_at": now_dt.isoformat(),
                        }
                    ).eq("site_id", site_id).in_(
                        "statut", ["OUVERTE", "EN_COURS"]
                    ).execute()

                # 2. Inscription de l'événement de clôture
                payload_fin = {
                    "reference": (f"REF-FIN-VAC-{now_dt.strftime('%Y%m%d-%H%M%S')}"),
                    "vacation_id": (
                        vac_id if (vac_id and len(str(vac_id)) == 36) else None
                    ),
                    "site_id": site_id,
                    "agent_nom": agent_nom,
                    "horodatage": now_dt.isoformat(),
                    "type_evenement": "FIN_VACATION",
                    "description": (
                        f"🚪 Clôture explicite du poste par {agent_nom} — Fin de"
                        " service PC Garde."
                    ),
                    "actions_menees": (
                        "Passation / Fin de poste enregistrée et vacation"
                        " fermée (CLOTUREE)."
                    ),
                }
                supabase.table("mc_evenements").insert(payload_fin).execute()

                st.toast(
                    "✅ Vacation clôturée avec succès en Base de Données !",
                    icon="🚪",
                )

            except Exception as err:
                st.error(f"Erreur lors de la clôture BDD : {err}")

            # Effacement de la session et rafraîchissement
            st.session_state.clear()
            st.rerun()

    with col_cancel:
        if st.button("❌ Annuler", use_container_width=True):
            st.rerun()


def show():
    st.title("📝 Main Courante - Service Terrain")

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get(
        "user_profile",
        {"full_name": "Éric KUTER", "login": "eric.kuter", "role": "ADMIN"},
    )
    agent_connecte = user_info.get("full_name", "Éric KUTER")
    agent_login = user_info.get("login", "")
    user_role = user_info.get("role", "AGENT_SECU")

    # 1. Vérification de la vacation active dans Supabase
    active_vacation = get_active_vacation(site_actuel, agent_connecte)

    # ------------------------------------------------------------------
    # CAS 1 : AUCUNE VACATION EN COURS -> PRISE DE POSTE
    # ------------------------------------------------------------------
    if active_vacation is None:
        st.warning(f"⚠️ Aucune vacation ouverte pour le site **{site_actuel}**.")

        col_start, _ = st.columns([1, 2])
        with col_start:
            if st.button("🚀 Prise de poste", type="primary", use_container_width=True):
                consignes = fetch_consignes_cibles_agent(
                    site_actuel, agent_login, user_role
                )

                try:
                    res_ano = (
                        supabase.table("anomalies")
                        .select("*")
                        .eq("site_id", site_actuel)
                        .neq("statut", "RESOLUE")
                        .execute()
                    )
                    anomalies = res_ano.data if res_ano.data else []
                except Exception:
                    anomalies = []

                if consignes or anomalies:
                    show_consignes_dialog(
                        site_actuel, agent_connecte, consignes, anomalies
                    )
                else:
                    vac_ref = generate_id("VAC")
                    now_iso = get_now_nc().isoformat()

                    payload = {
                        "reference": vac_ref,
                        "site_id": site_actuel,
                        "agent_nom": agent_connecte,
                        "debut_at": now_iso,
                        "statut": "EN_COURS",
                    }

                    try:
                        supabase.table("vacations").insert(payload).execute()
                        st.success(
                            f"Prise de poste enregistrée (`{vac_ref}`). Service"
                            " démarré !"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error("Erreur lors de la création de la vacation :" f" {e}")

    # ------------------------------------------------------------------
    # CAS 2 : VACATION EN COURS -> SERVICE ACTIF
    # ------------------------------------------------------------------
    else:
        vac_id = active_vacation["id"]
        vac_ref = active_vacation["reference"]
        st.session_state["vacation_id"] = vac_id

        res_c = fetch_consignes_cibles_agent(site_actuel, agent_login, user_role)
        try:
            res_a = (
                supabase.table("anomalies")
                .select("*")
                .eq("site_id", site_actuel)
                .neq("statut", "RESOLUE")
                .execute()
                .data
                or []
            )
        except Exception:
            res_a = []

        tot_alerts = len(res_c) + len(res_a)

        # En-tête épuré avec bouton de Consignes & Fin de poste
        col_info, col_alert, col_fin = st.columns([3, 1.2, 1])
        with col_info:
            st.success(
                f"🟢 **Vacation active :** `{vac_ref}` | 📍 **Site :**"
                f" {site_actuel} | 👤 **Agent :** {agent_connecte}"
            )

        with col_alert:
            if tot_alerts > 0:
                if st.button(
                    f"📋 Consignes ({tot_alerts})",
                    use_container_width=True,
                ):
                    show_consignes_dialog(site_actuel, agent_connecte, res_c, res_a)
            else:
                st.caption("✅ Aucune consigne active")

        with col_fin:
            if st.button(
                "🛑 Fin de poste",
                type="primary",
                use_container_width=True,
                help="Clôture officiellement la vacation en cours sur ce site.",
            ):
                show_fin_de_poste_dialog(vac_id, site_actuel, agent_connecte)

        st.markdown("---")

        # ONGLETS POUR SÉPARER LA SAISIE DU JOURNAL DE BORD
        tab_saisie, tab_journal = st.tabs(
            ["✍️ Saisir un événement", "📜 Journal de la vacation"]
        )

        # --------------------------------------------------------------
        # ONGLET 1 : FORMULAIRE DE SAISIE
        # --------------------------------------------------------------
        with tab_saisie:
            with st.form("form_saisie_mc", clear_on_submit=True):
                col_type, col_heure = st.columns([2, 1])
                with col_type:
                    type_event = st.selectbox(
                        "Type d'événement *",
                        [
                            "Observation",
                            "Incident",
                            "Prise de consignes",
                            "Contrôle d'accès",
                            "Ronde de sécurité",
                        ],
                    )
                with col_heure:
                    heure_event = st.time_input(
                        "Heure du constat", value=get_now_nc().time()
                    )

                description = st.text_area(
                    "Description des faits *",
                    placeholder="Rédigez la main courante...",
                )
                actions = st.text_area(
                    "Actions menées / Mesures prises",
                    placeholder="Ex: Informé le PC Sûreté, remis en état...",
                )

                notify = st.toggle(
                    "🔔 Notifier le responsable de sûreté par email",
                    value=False,
                )

                submitted = st.form_submit_button(
                    "💾 Enregistrer l'événement",
                    use_container_width=True,
                    type="primary",
                )

                if submitted:
                    if not description.strip():
                        st.error("La description est obligatoire.")
                    else:
                        event_ref = generate_id("MC")
                        now_nc = get_now_nc()
                        dt_event = datetime.datetime.combine(
                            now_nc.date(), heure_event, tzinfo=TZ_NC
                        ).isoformat()

                        event_payload = {
                            "reference": event_ref,
                            "vacation_id": vac_id,
                            "site_id": site_actuel,
                            "agent_nom": agent_connecte,
                            "horodatage": dt_event,
                            "type_evenement": type_event,
                            "description": description,
                            "actions_menees": actions,
                            "notified_authority": notify,
                        }

                        try:
                            supabase.table("mc_evenements").insert(
                                event_payload
                            ).execute()
                            st.toast(
                                f"Événement {event_ref} enregistré dans" " Supabase !",
                                icon="✅",
                            )

                            if notify:
                                email_body = f"""
                                <h3>🚨 Alerte Main Courante — {site_actuel}</h3>
                                <p><b>Référence :</b> {event_ref}</p>
                                <p><b>Vacation :</b> {vac_ref}</p>
                                <p><b>Agent :</b> {agent_connecte}</p>
                                <p><b>Type :</b> {type_event}</p>
                                <p><b>Heure du constat :</b> {heure_event.strftime('%H:%M')}</p>
                                <hr>
                                <p><b>Description des faits :</b><br>{description}</p>
                                <p><b>Actions menées :</b><br>{actions if actions else 'Aucune action renseignée'}</p>
                                <hr>
                                <p><small>Message automatique généré par le système ORBIS Main Courante V3.</small></p>
                                """

                                with st.spinner(
                                    "Envoi de la notification par email..."
                                ):
                                    sent = send_alert_email(
                                        subject=(
                                            f"{type_event} sur le site"
                                            f" {site_actuel} ({event_ref})"
                                        ),
                                        body_html=email_body,
                                        recipient_email="eric.kuter@gouv.nc",
                                    )
                                    if sent:
                                        st.success(
                                            "📧 Notification envoyée avec"
                                            " succès à l'autorité de sûreté !"
                                        )

                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur d'enregistrement : {e}")

        # --------------------------------------------------------------
        # ONGLET 2 : HISTORIQUE DE LA VACATION
        # --------------------------------------------------------------
        with tab_journal:
            try:
                res_events = (
                    supabase.table("mc_evenements")
                    .select("*")
                    .eq("vacation_id", vac_id)
                    .order("horodatage", desc=True)
                    .execute()
                )

                if res_events.data:
                    df = pd.DataFrame(res_events.data)[
                        [
                            "horodatage",
                            "reference",
                            "type_evenement",
                            "description",
                            "actions_menees",
                        ]
                    ]
                    df.columns = [
                        "Heure",
                        "Référence",
                        "Type",
                        "Description",
                        "Actions",
                    ]

                    df["Heure_dt"] = pd.to_datetime(
                        df["Heure"],
                        format="ISO8601",
                        utc=True,
                        errors="coerce",
                    )
                    df["Heure"] = (
                        df["Heure_dt"]
                        .dt.tz_convert("Pacific/Noumea")
                        .dt.strftime("%H:%M:%S")
                    )

                    st.caption(
                        f"Total : {len(df)} événement(s) enregistré(s) pendant"
                        " cette vacation."
                    )
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info(
                        "Aucun événement saisi pour le moment dans cette" " vacation."
                    )
            except Exception as e:
                st.error(f"Erreur de chargement du journal : {e}")

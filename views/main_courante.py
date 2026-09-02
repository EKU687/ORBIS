# =========================================================================
# MODULE : MAIN COURANTE SERVICE TERRAIN (views/main_courante.py)
# Inclus : Vacation site, pop-up de prise de poste avec filtrage dynamique
#          des consignes (Globales & Ciblées par agent), saisie et journal.
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


def fetch_consignes_cibles_agent(site_id: str, agent_login: str) -> list[dict]:
    """
    🎯 Récupère les consignes actives du site et les filtre pour l'agent connecté
    (Consignes globales "TOUS" OU destinées spécifiquement à son login).
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
        consignes_valides = []

        agent_login_clean = str(agent_login).lower().strip()

        for csg in raw_consignes:
            destinataires = csg.get("destinataires") or ["TOUS"]
            
            # Normalisation en minuscules pour comparaison stricte
            dest_list = [str(d).lower().strip() for d in destinataires]

            # 🎯 RÈGLE DE FILTRAGE : Si 'tous' est présent OU si le login de l'agent est ciblé
            if "tous" in dest_list or agent_login_clean in dest_list:
                consignes_valides.append(csg)

        return consignes_valides
    except Exception as e:
        print(f"⚠️ Erreur lors du chargement des consignes ciblées : {e}")
        return []


# --- FENÊTRE MODALE POP-UP DE VIGILANCE & CONSIGNES PRISE DE POSTE ---
@st.dialog("📋 CONSIGNES SITE & VIGILANCE", width="large")
def show_consignes_dialog(site_id: str, agent_connecte: str, consignes_actives: list, anomalies_actives: list):
    st.warning(f"**Site {site_id}**")
    st.write("Veuillez prendre connaissance des consignes et points de vigilance actifs :")
    
    # Zone défilante avec hauteur fixe pour éviter que le bouton de validation ne déborde
    with st.container(height=380):
        
        # 1. SECTION CONSIGNES PARTICULIÈRES (ADMIN) - FILTRÉES POUR L'AGENT
        if consignes_actives:
            st.markdown("### 📌 **Consignes Particulières & Temporaires**")
            for csg in consignes_actives:
                badge = "🔴 URGENT" if csg.get("priorite") == "URGENTE" else "🔵 CONSIGNE"
                destinataires = csg.get("destinataires") or ["TOUS"]
                badge_cible = "🎯 (Ciblée)" if "TOUS" not in destinataires else ""

                st.markdown(f"**{badge} [{csg['reference']}] {csg['titre']} {badge_cible}**")
                st.write(f"{csg['description']}")
                st.caption(f"Valable jusqu'au {csg['fin_at'][:10]} | Publiée par {csg['cree_par']}")
                st.markdown("---")
        
        # 2. SECTION ANOMALIES & POINTS DE VIGILANCE
        if anomalies_actives:
            st.markdown("### ⚠️ **Anomalies & Points de Vigilance**")
            for ano in anomalies_actives:
                badge = "🔴" if ano.get("criticite") in ["CRITIQUE", "ELEVEE"] else "🟠"
                st.markdown(f"{badge} **[{ano['reference']}] {ano['titre']}**")
                st.caption(f"{ano['description']} *(Priorité : {ano['criticite']})*")
                st.markdown("---")

    st.markdown("---")

    # Bouton de validation ancré en bas du pop-up
    if st.button("✅ J'ai pris connaissance des consignes", type="primary", use_container_width=True):
        active_vac = get_active_vacation(site_id, agent_connecte)
        if not active_vac:
            vac_ref = generate_id("VAC")
            now = get_now_nc().isoformat()

            payload = {
                "reference": vac_ref,
                "site_id": site_id,
                "agent_nom": agent_connecte,
                "debut_at": now,
                "statut": "EN_COURS",
            }

            try:
                supabase.table("vacations").insert(payload).execute()
                st.toast(f"Prise de poste enregistrée (`{vac_ref}`). Service démarré !", icon="🚀")
            except Exception as e:
                st.error(f"Erreur lors de la création de la vacation : {e}")
        
        st.rerun()


def show():
    st.title("📝 Main Courante - Service Terrain")

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get("user_profile", {"full_name": "Éric KUTER", "login": "eric.kuter"})
    agent_connecte = user_info.get("full_name", "Éric KUTER")
    agent_login = user_info.get("login", "")

    # 1. Vérification de la vacation active dans Supabase
    active_vacation = get_active_vacation(site_actuel, agent_connecte)

    # ------------------------------------------------------------------
    # CAS 1 : AUCUNE VACATION EN COURS -> PRISE DE POSTE
    # ------------------------------------------------------------------
    if active_vacation is None:
        st.warning(
            f"⚠️ Aucune vacation ouverte pour le site **{site_actuel}**."
        )

        col_start, _ = st.columns([1, 2])
        with col_start:
            if st.button("🚀 Prise de poste", type="primary", use_container_width=True):
                # 🎯 Récupération des CONSIGNES actives FILTRÉES pour l'agent connecté
                consignes = fetch_consignes_cibles_agent(site_actuel, agent_login)

                # Récupération des ANOMALIES non résolues
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

                # Si au moins une consigne personnalisée ou une anomalie existe -> Pop-up
                if consignes or anomalies:
                    show_consignes_dialog(site_actuel, agent_connecte, consignes, anomalies)
                else:
                    # Prise de poste directe s'il n'y a rien à signaler pour cet agent
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
                            f"Prise de poste enregistrée (`{vac_ref}`). Service démarré !"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur lors de la création de la vacation : {e}")

    # ------------------------------------------------------------------
    # CAS 2 : VACATION EN COURS -> SERVICE ACTIF
    # ------------------------------------------------------------------
    else:
        vac_id = active_vacation["id"]
        vac_ref = active_vacation["reference"]
        st.session_state["vacation_id"] = vac_id

        # 🎯 Récupération des consignes et anomalies pour l'affichage du badge d'en-tête
        res_c = fetch_consignes_cibles_agent(site_actuel, agent_login)
        try:
            res_a = supabase.table("anomalies").select("*").eq("site_id", site_actuel).neq("statut", "RESOLUE").execute().data or []
        except Exception:
            res_a = []
            
        tot_alerts = len(res_c) + len(res_a)

        # En-tête épuré
        col_info, col_alert = st.columns([3, 1])
        with col_info:
            st.success(
                f"🟢 **Vacation active :** `{vac_ref}` | 📍 **Site :** {site_actuel} | 👤 **Agent :** {agent_connecte}"
            )

        with col_alert:
            if tot_alerts > 0:
                if st.button(f"📋 Consignes & Vigilance ({tot_alerts})", use_container_width=True):
                    show_consignes_dialog(site_actuel, agent_connecte, res_c, res_a)
            else:
                st.caption("✅ Aucune consigne active")

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
                    "💾 Enregistrer l'événement", use_container_width=True, type="primary"
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
                                f"Événement {event_ref} enregistré dans Supabase !",
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
                                        subject=f"{type_event} sur le site {site_actuel} ({event_ref})",
                                        body_html=email_body,
                                        recipient_email="eric.kuter@gouv.nc",
                                    )
                                    if sent:
                                        st.success(
                                            "📧 Notification envoyée avec succès à l'autorité de sûreté !"
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

                    # 1. Conversion souple des formats ISO 8601
                    df["Heure_dt"] = pd.to_datetime(df["Heure"], format="ISO8601", utc=True, errors="coerce")

                    # 2. Conversion vers le fuseau horaire de Nouméa (UTC+11) et formatage HH:MM:SS
                    df["Heure"] = df["Heure_dt"].dt.tz_convert("Pacific/Noumea").dt.strftime("%H:%M:%S")
                
                    st.caption(
                        f"Total : {len(df)} événement(s) enregistré(s) pendant cette vacation."
                    )
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info(
                        "Aucun événement saisi pour le moment dans cette vacation."
                    )
            except Exception as e:
                st.error(f"Erreur de chargement du journal : {e}")
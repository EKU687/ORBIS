import sys
from pathlib import Path
import datetime
import streamlit as st
import pandas as pd

# Fix pour assurer que Python trouve le dossier 'utils' depuis 'views'
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase
from utils.email_sender import send_alert_email


def generate_id(prefix: str) -> str:
    """Génère un identifiant horodaté unique (ex: VAC-20260820-163000)."""
    now = datetime.datetime.now()
    return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"


def get_active_vacation(site_id: str, agent_nom: str):
    """Récupère la vacation en cours depuis Supabase pour le site et l'agent."""
    try:
        response = (
            supabase.table("vacations")
            .select("*")
            .eq("site_id", site_id)
            .eq("agent_nom", agent_nom)
            .eq("statut", "EN_COURS")
            .execute()
        )

        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        st.error(f"Erreur lors de la récupération de la vacation : {e}")
        return None


# --- FENÊTRE MODALE POP-UP DE VIGILANCE & CONSIGNES PRISE DE POSTE ---
@st.dialog("📋 CONSIGNES SITE & VIGILANCE", width="large")
def show_consignes_dialog(site_id: str, agent_connecte: str, consignes_actives: list, anomalies_actives: list):
    st.warning(f"**Site {site_id}**")
    st.write("Veuillez prendre connaissance des consignes et points de vigilance actifs :")
    
    # Zone défilante avec hauteur fixe pour éviter que le bouton de validation ne déborde
    with st.container(height=380):
        
        # 1. SECTION CONSIGNES PARTICULIÈRES (ADMIN)
        if consignes_actives:
            st.markdown("### 📌 **Consignes Particulières & Temporaires**")
            for csg in consignes_actives:
                badge = "🔴 URGENT" if csg.get("priorite") == "URGENTE" else "🔵 CONSIGNE"
                st.markdown(f"**{badge} [{csg['reference']}] {csg['titre']}**")
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
        # Si une vacation n'est pas encore ouverte, on la crée
        active_vac = get_active_vacation(site_id, agent_connecte)
        if not active_vac:
            vac_ref = generate_id("VAC")
            now = datetime.datetime.now().isoformat()

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
    user_info = st.session_state.get("user_profile", {"full_name": "Éric KUTER"})
    agent_connecte = user_info["full_name"]

    # 1. Vérification de la vacation active dans Supabase
    active_vacation = get_active_vacation(site_actuel, agent_connecte)

    # ------------------------------------------------------------------
    # CAS 1 : AUCUNE VACATION EN COURS -> PRISE DE POSTE
    # ------------------------------------------------------------------
    if active_vacation is None:
        st.warning(
            f"⚠️ Aucune vacation ouverte pour **{agent_connecte}** sur le site **{site_actuel}**."
        )

        col_start, _ = st.columns([1, 2])
        with col_start:
            if st.button("🚀 Prise de poste", type="primary", use_container_width=True):
                now_iso = datetime.datetime.now().isoformat()
                
                # Récupération des CONSIGNES actives
                try:
                    res_csg = (
                        supabase.table("consignes")
                        .select("*")
                        .eq("site_id", site_actuel)
                        .eq("statut", "ACTIVE")
                        .gte("fin_at", now_iso)
                        .execute()
                    )
                    consignes = res_csg.data if res_csg.data else []
                except Exception:
                    consignes = []

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

                # Si au moins une consigne ou une anomalie existe -> Affichage du Pop-up
                if consignes or anomalies:
                    show_consignes_dialog(site_actuel, agent_connecte, consignes, anomalies)
                else:
                    # Prise de poste directe s'il n'y a rien à signaler
                    vac_ref = generate_id("VAC")

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

        # Récupération rapide du nombre d'instructions actives pour le badge
        now_iso = datetime.datetime.now().isoformat()
        try:
            res_c = supabase.table("consignes").select("*").eq("site_id", site_actuel).eq("statut", "ACTIVE").gte("fin_at", now_iso).execute().data or []
            res_a = supabase.table("anomalies").select("*").eq("site_id", site_actuel).neq("statut", "RESOLUE").execute().data or []
            tot_alerts = len(res_c) + len(res_a)
        except Exception:
            res_c, res_a, tot_alerts = [], [], 0

        # En-tête fixe et ergonomique
        col_info, col_alert, col_close = st.columns([3, 1.5, 1])
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

        with col_close:
            if st.button("🔴 Fin de poste", type="secondary", use_container_width=True):
                now = datetime.datetime.now().isoformat()
                try:
                    supabase.table("vacations").update(
                        {"fin_at": now, "statut": "CLOTUREE"}
                    ).eq("id", vac_id).execute()
                    st.info(f"Vacation `{vac_ref}` clôturée avec succès.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la clôture de la vacation : {e}")

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
                        "Heure du constat", value=datetime.datetime.now().time()
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
                    "💾 Enregistrer l'événement", use_container_width=True
                )

                if submitted:
                    if not description.strip():
                        st.error("La description est obligatoire.")
                    else:
                        event_ref = generate_id("MC")
                        dt_event = datetime.datetime.combine(
                            datetime.date.today(), heure_event
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

                    df["Heure"] = pd.to_datetime(df["Heure"]).dt.strftime(
                        "%H:%M:%S"
                    )

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
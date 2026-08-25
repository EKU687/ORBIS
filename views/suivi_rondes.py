import datetime
from pathlib import Path
import sys
import uuid
import zoneinfo
import streamlit as st

# Détection et chargement de la gestion des jours fériés NC
try:
    import holidays

    HAS_HOLIDAYS = True
except ImportError:
    HAS_HOLIDAYS = False

# --- FIX DES CHEMINS ---
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

# Détection de la disponibilité du module d'email
try:
    from utils.email_sender import envoyer_notification_passage_poste_securite

    HAS_EMAIL = True
except Exception:
    HAS_EMAIL = False

# Fuseau horaire Nouvelle-Calédonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


def est_jour_non_ouvre(date_cible: datetime.date) -> tuple[bool, str]:
    """Détermine si la date est un jour non travaillé (Week-End ou Férié Nouvelle-Calédonie).

    Retourne:
        - est_non_ouvre (bool): True si le site est fermé en journée
        - motif (str): Description du régime ('Week-End' ou nom du jour férié)
    """
    # 1. Contrôle du Week-End (5 = Samedi, 6 = Dimanche)
    if date_cible.weekday() in [5, 6]:
        return True, "Week-End"

    # 2. Contrôle des Jours Fériés en Nouvelle-Calédonie (Code Pays: NC)
    if HAS_HOLIDAYS:
        feries_nc = holidays.NC(years=date_cible.year)
        if date_cible in feries_nc:
            nom_ferie = feries_nc.get(date_cible)
            return True, f"Jour Férié ({nom_ferie})"

    return False, "Jour Ouvré"


def generer_grille_rondes_du_jour(date_cible: datetime.date) -> list[dict]:
    """Génère la grille des rondes ordonnée selon la VACATION DE SÛRETÉ (20:00 -> 05:00 puis Journée si non ouvré)."""
    est_non_ouvre, motif = est_jour_non_ouvre(date_cible)

    grille = []

    # =========================================================================
    # BLOC 1 : SOIRÉE & DÉBUT DE NUIT (20:00 -> 23:00)
    # =========================================================================

    # 1. Créneau 20:00 (Fermeture globale en semaine vs Ronde extérieure si non ouvré)
    if not est_non_ouvre:
        grille.append({
            "heure_cible": "20:00",
            "type": "Fermeture Globale (Int. & Ext.)",
            "frequence": "Ponctuelle (Semaine)",
        })
    else:
        grille.append({
            "heure_cible": "20:00",
            "type": "Ronde Extérieure (Périmètre)",
            "frequence": f"Nuit {motif}",
        })

    # 2. Rondes du soir (21:00 -> 23:00)
    for h in ["21:00", "22:00", "23:00"]:
        h_int = int(h.split(":")[0])
        est_ext = h_int % 2 == 0
        type_str = (
            "Ronde Intérieure & Extérieure" if est_ext else "Ronde Intérieure"
        )
        grille.append({
            "heure_cible": h,
            "type": type_str,
            "frequence": "Nuit (Int. 1h / Ext. 2h)",
        })

    # =========================================================================
    # BLOC 2 : MILIEU & FIN DE NUIT (00:00 -> 05:00)
    # =========================================================================

    # 3. Rondes du milieu de nuit (00:00 -> 04:00)
    for h in ["00:00", "01:00", "02:00", "03:00", "04:00"]:
        h_int = int(h.split(":")[0])
        est_ext = h_int % 2 == 0
        type_str = (
            "Ronde Intérieure & Extérieure" if est_ext else "Ronde Intérieure"
        )
        grille.append({
            "heure_cible": h,
            "type": type_str,
            "frequence": "Nuit (Int. 1h / Ext. 2h)",
        })

    # 4. Créneau 05:00 (Ouverture site en semaine vs Ronde extérieure si non ouvré)
    if not est_non_ouvre:
        grille.append({
            "heure_cible": "05:00",
            "type": "Ouverture du Site & Contrôle Périmètre",
            "frequence": "Ponctuelle (Semaine)",
        })
    else:
        grille.append({
            "heure_cible": "05:00",
            "type": "Ronde Extérieure (Périmètre)",
            "frequence": f"Nuit {motif}",
        })

    # =========================================================================
    # BLOC 3 : JOURNÉE COMPLÈTE (06:00 -> 19:00) - Uniquement Week-End / Férié
    # =========================================================================
    if est_non_ouvre:
        for h_num in range(6, 20):
            h_str = f"{h_num:02d}:00"
            est_ext = h_num % 2 == 0
            type_str = (
                "Ronde Journée (Int. & Ext.)"
                if est_ext
                else "Ronde Journée (Intérieure)"
            )
            grille.append({
                "heure_cible": h_str,
                "type": type_str,
                "frequence": f"Journée {motif}",
            })

    return grille


def get_or_create_vacation_id(site_id: str, agent_nom: str) -> str:
    """Récupère l'UUID réel de la dernière vacation ouverte sur le site, ou en crée une nouvelle."""
    if (
        st.session_state.get("vacation_id")
        and len(str(st.session_state["vacation_id"])) == 36
    ):
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


def envoyer_email_anomalie_ronde(
    site: str,
    h_cible: str,
    type_ronde: str,
    heure_constat: str,
    observation: str,
    agent_garde: str,
):
    """Envoie une notification par email spécifique au format 'Alerte Anomalie Ronde'."""
    if not HAS_EMAIL:
        return

    titre_alerte = f"ANOMALIE RONDE {h_cible} ({type_ronde})"

    envoyer_notification_passage_poste_securite(
        site=site,
        nom_personne=titre_alerte,
        organisme=f"Ronde de Nuit ({site})",
        heure=heure_constat,
        type_piece="Constat d'Anomalie",
        num_piece=observation,
        agent_garde=agent_garde,
    )


def show():
    st.title("🔦 Suivi & Émargement des Rondes de Sûreté")

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get(
        "user_profile", {"full_name": "Agent PC Security"}
    )
    agent_connecte = user_info["full_name"]

    vac_id = get_or_create_vacation_id(site_actuel, agent_connecte)

    # Récupération de l'horodatage précis en Nouvelle-Calédonie
    now_nc = get_now_nc()
    today_dt = now_nc.date()
    heure_courante = now_nc.hour

    nom_jour_fr = [
        "Lundi",
        "Mardi",
        "Mercredi",
        "Jeudi",
        "Vendredi",
        "Samedi",
        "Dimanche",
    ][today_dt.weekday()]

    st.caption(
        f"Programme officiel pour le **{nom_jour_fr}"
        f" {today_dt.strftime('%d/%m/%Y')}** sur le site **{site_actuel}**."
    )

    # Détection du régime du jour
    est_non_ouvre, motif = est_jour_non_ouvre(today_dt)
    grille_rondes = generer_grille_rondes_du_jour(today_dt)

    if est_non_ouvre:
        st.info(
            f"ℹ️ **Régime {motif} Actif :** Surveillance continue 24h/24."
            " Rondes extérieures maintenues à 05h00 et 20h00 (pas d'ouverture/fermeture)."
        )
    else:
        st.info(
            "ℹ️ **Régime Semaine Actif :** Rondes de Nuit + Ouverture Site"
            " (05h00) & Fermeture Globale (20h00)."
        )

        # Affichage d'un bandeau d'information durant la période d'ouverture en semaine
        if 8 <= heure_courante < 16:
            st.warning(
                "☀️ **Période Ouvrée (08h00 - 16h00) : Hors Couverture Rondes Systématiques.**\n\n"
                "Le site est actuellement ouvert sous la responsabilité des agents et services hôtes. "
                "Les rondes programmées reprendront à 20h00 (Fermeture globale)."
            )

    # 1. Chargement des rondes effectuées aujourd'hui
    rondes_validees = {}
    try:
        res = (
            supabase.table("mc_evenements")
            .select("*")
            .eq("site_id", site_actuel)
            .eq("type_evenement", "RONDE")
            .execute()
        )
        for ev in res.data or []:
            ref = ev.get("reference", "")
            rondes_validees[ref] = ev
    except Exception as e:
        st.error(f"❌ Erreur de lecture BDD Rondes : {e}")

    # 2. Affichage des cartes de rondes
    for ronde in grille_rondes:
        h_target = ronde["heure_cible"]
        type_ronde = ronde["type"]
        ref_cle = f"REF-RONDE-{today_dt.strftime('%Y%m%d')}-{h_target}"

        est_faite = ref_cle in rondes_validees

        with st.container(border=True):
            col_horaire, col_desc, col_action = st.columns([1.5, 3, 2.5])

            with col_horaire:
                st.markdown(f"🕒 **Créneau : {h_target}**")
                st.caption(f"Mode : {ronde['frequence']}")

            with col_desc:
                st.markdown(f"🏃 **{type_ronde}**")
                if est_faite:
                    ev_info = rondes_validees[ref_cle]
                    dt_valide = ev_info.get("horodatage", "")[11:16]
                    agent_nom = ev_info.get("agent_nom", "Agent")
                    st.success(f"✅ **Effectuée à {dt_valide}** par {agent_nom}")
                    st.caption(f"Obs : {ev_info.get('description', 'RAS')}")
                else:
                    st.warning("⏳ **Ronde non effectuée**")

            with col_action:
                if not est_faite:
                    with st.popover(
                        f"📝 Émarger ronde {h_target}", use_container_width=True
                    ):
                        st.markdown(f"**Émargement Ronde {h_target}**")

                        observation = st.text_input(
                            "Observations / Consignes :",
                            value="R.A.S. - Parcours effectué sans anomalie.",
                            key=f"obs_{h_target}",
                        )

                        has_anomalie = st.checkbox(
                            "⚠️ Signaler une anomalie constatée",
                            key=f"ano_{h_target}",
                        )

                        notif_surete = False
                        if has_anomalie:
                            st.error(
                                "🚨 Une entrée sera créée automatiquement dans"
                                " la Main Courante !"
                            )
                            notif_surete = st.checkbox(
                                "✉️ Prévenir immédiatement le Chargé de Sûreté"
                                " par Email",
                                value=True,
                                key=f"notif_{h_target}",
                            )

                        if st.button(
                            "✅ Valider l'émargement",
                            key=f"btn_{h_target}",
                            type="primary",
                            use_container_width=True,
                        ):
                            now_nc_local = get_now_nc()
                            ref_time = now_nc_local.strftime("%Y%m%d-%H%M%S")

                            payload_ronde = {
                                "reference": ref_cle,
                                "vacation_id": vac_id,
                                "site_id": site_actuel,
                                "agent_nom": agent_connecte,
                                "horodatage": now_nc_local.isoformat(),
                                "type_evenement": "RONDE",
                                "description": (
                                    f"Ronde {type_ronde} ({h_target}) :"
                                    f" {observation}"
                                ),
                                "actions_menees": (
                                    "Anomalie signalée et transmise"
                                    if has_anomalie
                                    else "Parcours conforme (RAS)"
                                ),
                            }

                            try:
                                supabase.table("mc_evenements").insert(
                                    payload_ronde
                                ).execute()

                                if has_anomalie:
                                    payload_anomalie = {
                                        "reference": (
                                            f"REF-ANO-RONDE-{ref_time}"
                                        ),
                                        "vacation_id": vac_id,
                                        "site_id": site_actuel,
                                        "agent_nom": agent_connecte,
                                        "horodatage": now_nc_local.isoformat(),
                                        "type_evenement": "ANOMALIE",
                                        "description": (
                                            f"⚠️ ANOMALIE DÉTECTÉE lors de la"
                                            f" Ronde {h_target} ({type_ronde}) :"
                                            f" {observation}"
                                        ),
                                        "actions_menees": (
                                            "Consigné depuis le module Rondes."
                                            " Sûreté informée."
                                            if notif_surete
                                            else "Consigné depuis le module"
                                                 " Rondes."
                                        ),
                                    }
                                    supabase.table("mc_evenements").insert(
                                        payload_anomalie
                                    ).execute()

                                    if notif_surete and HAS_EMAIL:
                                        try:
                                            envoyer_email_anomalie_ronde(
                                                site=site_actuel,
                                                h_cible=h_target,
                                                type_ronde=type_ronde,
                                                heure_constat=now_nc_local.strftime(
                                                    "%H:%M"
                                                ),
                                                observation=observation,
                                                agent_garde=agent_connecte,
                                            )
                                            st.toast(
                                                "Sûreté notifiée par email !",
                                                icon="✉️",
                                            )
                                        except Exception as mail_err:
                                            st.warning(
                                                "Note : Email non transmitted"
                                                f" ({mail_err})"
                                            )

                                st.toast(
                                    f"Ronde {h_target} consignée avec succès !",
                                    icon="✅",
                                )
                                st.rerun()

                            except Exception as err:
                                st.error(f"Erreur d'enregistrement : {err}")
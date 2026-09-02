# =========================================================================
# MODULE : SUIVI & ÉMARGEMENT DES RONDES DE SÛRETÉ (views/suivi_rondes.py)
# Inclus : Génération dynamique des rondes, décalage aléatoire (0-10 min),
#          fenêtre d'émargement active de 30 minutes et enregistrement BDD.
# =========================================================================
import datetime
import hashlib
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
    """Détermine si la date est un jour non travaillé (Week-End ou Férié Nouvelle-Calédonie)."""
    if date_cible.weekday() in [5, 6]:
        return True, "Week-End"

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

    # BLOC 1 : SOIRÉE & DÉBUT DE NUIT (20:00 -> 23:00)
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

    # BLOC 2 : MILIEU & FIN DE NUIT (00:00 -> 05:00)
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

    # BLOC 3 : JOURNÉE COMPLÈTE (06:00 -> 19:00) - Uniquement Week-End / Férié
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


def calculer_statut_creneau(
    heure_cible_str: str, now_datetime: datetime.datetime, est_faite: bool
) -> tuple[str, bool, str, int]:
    """
    🎯 CALCUL DYNAMIQUE AVEC DÉCALAGE ALÉATOIRE (0 à 10 MIN) ET FENÊTRE ACTIVE DE 30 MIN.
    Returns: (statut_code, bouton_actif, heure_debut_str, minutes_restantes)
    """
    if est_faite:
        return "EFFECTUEE", False, "", 0

    h_target, m_target = map(int, heure_cible_str.split(":"))
    date_jour = now_datetime.date()

    # 1. Génération d'un décalage aléatoire déterministe entre 0 et 10 minutes
    seed_str = f"{date_jour.isoformat()}_{heure_cible_str}"
    decalage_minutes = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest(), 16) % 11

    # Date cible théorique (ex: 20:00)
    dt_base = now_datetime.replace(
        hour=h_target, minute=m_target, second=0, microsecond=0
    )

    # 🎯 GESTION DU PASSAGE À MINUIT (00h00 -> 05h00)
    if h_target <= 5 and now_datetime.hour >= 5:
        dt_base += datetime.timedelta(days=1)

    # 2. Définition de l'heure de début effective (+ décalage) et de fin (+30 min)
    dt_debut_ronde = dt_base + datetime.timedelta(minutes=decalage_minutes)
    dt_fin_ronde = dt_debut_ronde + datetime.timedelta(minutes=30)

    heure_debut_str = dt_debut_ronde.strftime("%H:%M")

    # 3. Évaluation du statut temporel
    if now_datetime < dt_debut_ronde:
        return "FUTUR", False, heure_debut_str, 0
    elif dt_debut_ronde <= now_datetime <= dt_fin_ronde:
        min_restantes = int((dt_fin_ronde - now_datetime).total_seconds() // 60)
        return "ACTIF", True, heure_debut_str, min_restantes
    else:
        return "DEPASSE", False, heure_debut_str, 0


def get_or_create_vacation_id(site_id: str, agent_nom: str) -> str:
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

    now_nc = get_now_nc()
    today_dt = now_nc.date()
    heure_courante = now_nc.hour

    nom_jour_fr = [
        "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"
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

    # 2. Affichage des cartes de rondes avec décalage aléatoire et fenêtre de 30 min
    for ronde in grille_rondes:
        h_target = ronde["heure_cible"]
        type_ronde = ronde["type"]
        ref_cle = f"REF-RONDE-{today_dt.strftime('%Y%m%d')}-{h_target}"

        est_faite = ref_cle in rondes_validees
        statut_code, bouton_actif, h_debut_genere, min_restantes = calculer_statut_creneau(
            h_target, now_nc, est_faite
        )

        with st.container(border=True):
            col_horaire, col_desc, col_action = st.columns([1.5, 3, 2.5])

            with col_horaire:
                st.markdown(f"🕒 **Créneau : {h_target}**")
                if not est_faite and h_debut_genere:
                    st.caption(f"Début aléatoire : **{h_debut_genere}**\n\n*(Fenêtre : 30 min)*")
                else:
                    st.caption("Tolérance : 30 min active")

            with col_desc:
                st.markdown(f"🏃 **{type_ronde}**")
                
                if est_faite:
                    ev_info = rondes_validees[ref_cle]
                    dt_valide = ev_info.get("horodatage", "")[11:16]
                    agent_nom = ev_info.get("agent_nom", "Agent")
                    st.success(f"✅ **Effectuée à {dt_valide}** par {agent_nom}")
                    st.caption(f"Obs : {ev_info.get('description', 'RAS')}")
                elif statut_code == "ACTIF":
                    st.success(f"🟢 **Créneau ACTIF (Démarre à {h_debut_genere})** — **{min_restantes} min restantes**")
                elif statut_code == "FUTUR":
                    st.info(f"⚪ **Ronde à venir à {h_debut_genere}** (Bouton inactif)")
                elif statut_code == "DEPASSE":
                    st.error("🔴 **Créneau DÉPASSÉ — Ronde non effectuée (>30 min)**")

            with col_action:
                if not est_faite:
                    if bouton_actif:
                        with st.popover(
                            f"📝 Émarger ronde {h_target}", use_container_width=True
                        ):
                            st.markdown(f"**Émargement Ronde {h_target} (Début {h_debut_genere})**")

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
                                        f"Ronde {type_ronde} ({h_target} - Début {h_debut_genere}) :"
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
                                                    "Note : Email non transmis"
                                                    f" ({mail_err})"
                                                )

                                    st.toast(
                                        f"Ronde {h_target} consignée avec succès !",
                                        icon="✅",
                                    )
                                    st.rerun()

                                except Exception as err:
                                    st.error(f"Erreur d'enregistrement : {err}")
                    else:
                        btn_label = (
                            f"🔒 À venir ({h_debut_genere})"
                            if statut_code == "FUTUR"
                            else "🔒 Hors délai (>30 min)"
                        )
                        st.button(
                            btn_label,
                            key=f"btn_disabled_{h_target}",
                            disabled=True,
                            use_container_width=True,
                        )
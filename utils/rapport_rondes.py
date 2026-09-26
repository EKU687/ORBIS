"""
Rapport Automatique des Rondes — ORBIS / Main Courante V3
Contrôle basé directement sur le registre des événements (mc_evenements).
Supporte les vacations de nuit ainsi que les rondes de jour (Week-ends & Jours Fériés NC).
"""

from pathlib import Path
import sys

# Inclusion de la racine du projet
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import datetime
import zoneinfo
from tenacity import retry, stop_after_attempt, wait_fixed

from utils.db_client import supabase
from utils.email_sender import send_alert_email

# Fuseau horaire Nouméa (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")

# Créneaux théoriques des rondes
CRENEAUX_NUIT = [
    "20:00",
    "21:00",
    "22:00",
    "23:00",
    "00:00",
    "01:00",
    "02:00",
    "03:00",
    "04:00",
    "05:00",
]

CRENEAUX_JOURNEE = [
    "06:00",
    "07:00",
    "08:00",
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "14:00",
    "15:00",
    "16:00",
    "17:00",
    "18:00",
    "19:00",
]

# Calendrier des jours fériés légaux en Nouvelle-Calédonie
JOURS_FERIES_NC = {
    datetime.date(2026, 1, 1),  # Nouvel An
    datetime.date(2026, 4, 6),  # Lundi de Pâques
    datetime.date(2026, 5, 1),  # Fête du Travail
    datetime.date(2026, 5, 8),  # Victoire 1945
    datetime.date(2026, 5, 14),  # Ascension
    datetime.date(2026, 5, 25),  # Lundi de Pentecôte
    datetime.date(2026, 7, 14),  # Fête Nationale
    datetime.date(2026, 8, 15),  # Assomption
    datetime.date(2026, 9, 24),  # Fête de la Citoyenneté
    datetime.date(2026, 11, 1),  # Toussaint
    datetime.date(2026, 11, 11),  # Armistice 1918
    datetime.date(2026, 12, 25),  # Noël
}


def est_jour_non_travaille(d: datetime.date) -> bool:
    """Retourne True si la date est un Samedi, Dimanche ou Jour Férié NC."""
    return d.weekday() in (5, 6) or d in JOURS_FERIES_NC


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=False)
def fetch_sites_actifs() -> list[str]:
    """Récupère les sites actifs depuis Supabase."""
    res_sites = supabase.table("Sites").select("nom_site").eq("actif", True).execute()
    return [s["nom_site"] for s in (res_sites.data or []) if s.get("nom_site")]


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=False)
def fetch_registre_rondes(
    site_id: str, dt_debut_iso: str, dt_fin_iso: str
) -> list[dict]:
    """
    Interroge directement mc_evenements pour extraire toutes les rondes enregistrées.
    """
    res = (
        supabase.table("mc_evenements")
        .select("id, site_id, horodatage, reference, agent_nom, description")
        .eq("site_id", site_id)
        .eq("type_evenement", "RONDE")
        .gte("horodatage", dt_debut_iso)
        .lte("horodatage", dt_fin_iso)
        .order("horodatage", desc=False)
        .execute()
    )
    return res.data or []


def extraire_heure_cible(reference: str) -> str | None:
    """
    Extrait le tag horaire 'HH:MM' d'une référence (ex: 'REF-RONDE-20260926-05:00' -> '05:00').
    """
    if not reference:
        return None
    parties = reference.split("-")
    if len(parties) >= 4:
        return parties[-1]
    return None


def construire_table_html(
    creneaux: list[str], rondes_map: dict
) -> tuple[int, int, str]:
    """
    Construit les lignes du tableau HTML et calcule le bilan OK / KO.
    """
    nb_ok = 0
    nb_ko = 0
    lignes_html = ""

    for h_target in creneaux:
        if h_target in rondes_map:
            nb_ok += 1
            ev = rondes_map[h_target]
            raw_iso = ev.get("horodatage", "")

            try:
                dt_utc = datetime.datetime.fromisoformat(raw_iso.replace("Z", "+00:00"))
                dt_nc = dt_utc.astimezone(TZ_NC)
                heure_f = dt_nc.strftime("%H:%M:%S")
            except Exception:
                heure_f = raw_iso[11:19] if len(raw_iso) >= 19 else "N/A"

            agent_f = ev.get("agent_nom", "Agent")
            lignes_html += f"""
            <tr style="background-color: #e8f5e9;">
                <td><b>{h_target}</b></td>
                <td>Ronde Périphérique / Sécurité</td>
                <td style="color: green;"><b>✅ EFFECTUÉE</b> ({heure_f})</td>
                <td>{agent_f}</td>
            </tr>
            """
        else:
            nb_ko += 1
            lignes_html += f"""
            <tr style="background-color: #ffebee;">
                <td><b>{h_target}</b></td>
                <td>Ronde Périphérique / Sécurité</td>
                <td style="color: red;"><b>🔴 NON EXÉCUTÉE</b></td>
                <td>-</td>
            </tr>
            """

    return nb_ok, nb_ko, lignes_html


def generer_et_envoyer_rapport_nuit_tous_sites():
    """
    [Lancement du matin - Ex: 06:00]
    Génère le rapport des rondes de nuit (20:00 hier -> 05:00 ce matin).
    """
    now_nc = datetime.datetime.now(TZ_NC)
    today = now_nc.date()
    yesterday = today - datetime.timedelta(days=1)

    # Fenêtre ISO élargie : de 20:00 (hier) à 06:30 (ce matin)
    dt_debut_nuit = datetime.datetime.combine(
        yesterday, datetime.time(20, 0), tzinfo=TZ_NC
    )
    dt_fin_nuit = datetime.datetime.combine(today, datetime.time(6, 30), tzinfo=TZ_NC)

    sites = fetch_sites_actifs() or ["SITE OUEMO", "SITE DOUMER"]

    for site_id in sites:
        evenements = fetch_registre_rondes(
            site_id, dt_debut_nuit.isoformat(), dt_fin_nuit.isoformat()
        )

        # Indexation par heure cible (HH:MM)
        rondes_map = {}
        for ev in evenements:
            h_cible = extraire_heure_cible(ev.get("reference", ""))
            if h_cible:
                rondes_map[h_cible] = ev

        nb_ok, nb_ko, lignes_html = construire_table_html(CRENEAUX_NUIT, rondes_map)
        total = len(CRENEAUX_NUIT)
        taux = round((nb_ok / total) * 100, 1) if total else 0

        sujet = f"📊 Rapport Rondes de Nuit — {site_id} ({today.strftime('%d/%m/%Y')})"
        corps_html = f"""
        <h2>🔦 Bilan des Rondes de Nuit — {site_id}</h2>
        <p><b>Période d'analyse :</b> Du {yesterday.strftime('%d/%m/%Y')} 20:00 au {today.strftime('%d/%m/%Y')} 06:00</p>
        <ul>
            <li><b>Rondes effectuées :</b> {nb_ok} / {total}</li>
            <li><b>Rondes manquées :</b> <span style="color:red;"><b>{nb_ko}</b></span></li>
            <li><b>Taux de conformité :</b> <b>{taux}%</b></li>
        </ul>
        <br>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th>Créneau</th>
                    <th>Type de Ronde</th>
                    <th>Statut Registre</th>
                    <th>Agent</th>
                </tr>
            </thead>
            <tbody>
                {lignes_html}
            </tbody>
        </table>
        <br>
        <p><small>Rapport automatique basé sur le registre mc_evenements (ORBIS V3).</small></p>
        """

        try:
            send_alert_email(
                subject=sujet,
                body_html=corps_html,
                recipient_email="eric.kuter@gouv.nc",
            )
            print(f"✉️ Rapport de Nuit transmis avec succès pour {site_id}")
        except Exception as mail_err:
            print(f"❌ Erreur envoi mail Nuit pour {site_id} : {mail_err}")


def generer_et_envoyer_rapport_journee_si_besoin():
    """
    [Lancement du soir - Ex: 20:00]
    Génère le rapport de journée (06:00 -> 19:00) uniquement le Week-End et les Jours Fériés.
    """
    now_nc = datetime.datetime.now(TZ_NC)
    today = now_nc.date()

    if not est_jour_non_travaille(today):
        print(
            f"ℹ️ {today.strftime('%d/%m/%Y')} est un jour ouvré : pas de rapport de journée."
        )
        return

    # Fenêtre ISO de 06:00 à 20:30 (aujourd'hui)
    dt_debut_jour = datetime.datetime.combine(today, datetime.time(6, 0), tzinfo=TZ_NC)
    dt_fin_jour = datetime.datetime.combine(today, datetime.time(20, 30), tzinfo=TZ_NC)

    sites = fetch_sites_actifs() or ["SITE OUEMO", "SITE DOUMER"]

    for site_id in sites:
        evenements = fetch_registre_rondes(
            site_id, dt_debut_jour.isoformat(), dt_fin_jour.isoformat()
        )

        rondes_map = {}
        for ev in evenements:
            h_cible = extraire_heure_cible(ev.get("reference", ""))
            if h_cible:
                rondes_map[h_cible] = ev

        nb_ok, nb_ko, lignes_html = construire_table_html(CRENEAUX_JOURNEE, rondes_map)
        total = len(CRENEAUX_JOURNEE)
        taux = round((nb_ok / total) * 100, 1) if total else 0

        sujet = f"☀️ Rapport Rondes de Journée (WE/Férié) — {site_id} ({today.strftime('%d/%m/%Y')})"
        corps_html = f"""
        <h2>☀️ Bilan des Rondes de Journée — {site_id}</h2>
        <p><b>Période d'analyse :</b> Le {today.strftime('%d/%m/%Y')} de 06:00 à 20:00 (Jour Non Travillé)</p>
        <ul>
            <li><b>Rondes effectuées :</b> {nb_ok} / {total}</li>
            <li><b>Rondes manquées :</b> <span style="color:red;"><b>{nb_ko}</b></span></li>
            <li><b>Taux de conformité :</b> <b>{taux}%</b></li>
        </ul>
        <br>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th>Créneau</th>
                    <th>Type de Ronde</th>
                    <th>Statut Registre</th>
                    <th>Agent</th>
                </tr>
            </thead>
            <tbody>
                {lignes_html}
            </tbody>
        </table>
        <br>
        <p><small>Rapport automatique basé sur le registre mc_evenements (ORBIS V3).</small></p>
        """

        try:
            send_alert_email(
                subject=sujet,
                body_html=corps_html,
                recipient_email="eric.kuter@gouv.nc",
            )
            print(f"✉️ Rapport de Journée transmis avec succès pour {site_id}")
        except Exception as mail_err:
            print(f"❌ Erreur envoi mail Journée pour {site_id} : {mail_err}")


if __name__ == "__main__":
    # 1. Toujours lancer la vérification de nuit
    generer_et_envoyer_rapport_nuit_tous_sites()

    # 2. Lancer la vérification de jour si jour non travaillé
    generer_et_envoyer_rapport_journee_si_besoin()

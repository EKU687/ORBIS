import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Union
import requests

# Configuration du logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ORBIS_EMAIL")

# Pool d'exécution d'arrière-plan résilient pour Streamlit
_EMAIL_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="BrevoWorker")

# Chargement automatique du .env
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv())
except ImportError:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def get_secret(key: str, default: str = "") -> str:
    """Helper universel : Environnement système prioritaire, puis st.secrets sans crash en CLI."""
    val = os.environ.get(key)
    if val:
        return val

    try:
        import streamlit as st

        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass

    return default


def _execute_brevo_request(
    subject: str,
    body_html: str,
    recipient_email: Union[str, List[str]],
    sender_name: str,
    sender_email: str,
    api_key: str,
) -> bool:
    """Effectue l'appel HTTP bloquant vers l'API Brevo v3."""
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    if isinstance(recipient_email, str):
        to_list = [
            {"email": e.strip()} for e in recipient_email.split(",") if e.strip()
        ]
    else:
        to_list = [{"email": e.strip()} for e in recipient_email if e.strip()]

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": to_list,
        "subject": subject,
        "htmlContent": body_html,
    }

    try:
        logger.info(f"📧 Envoi Brevo vers : {[t['email'] for t in to_list]}")
        response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code in [200, 201, 202]:
            logger.info("✅ [BREVO SUCCESS] E-mail transmis avec succès.")
            return True
        else:
            logger.error(
                f"❌ [BREVO ERROR] Statut HTTP {response.status_code} : {response.text}"
            )
            return False

    except Exception as e:
        logger.error(f"❌ [BREVO ERROR] Exception réseau/HTTP : {e}")
        return False


def send_alert_email(
    subject: str,
    body_html: str,
    recipient_email: Union[str, List[str]] = "eric.kuter@gouv.nc",
    async_send: bool = False,
) -> bool:
    """Envoi d'e-mail HTML via Brevo v3.
    - async_send=True : utilise un pool de threads pérenne (recommandé pour Streamlit).
    - async_send=False : synchrone et bloquant (obligatoire pour GitHub Actions / CLI).
    """
    api_key = get_secret("BREVO_API_KEY", "")
    sender_email = get_secret("BREVO_SENDER_EMAIL", "")
    sender_name = get_secret("BREVO_SENDER_NAME", "ORBIS Sûreté")

    if not api_key or not sender_email:
        logger.error(
            "❌ [BREVO CONFIG] BREVO_API_KEY ou BREVO_SENDER_EMAIL manquant(s)."
        )
        return False

    if async_send:
        _EMAIL_EXECUTOR.submit(
            _execute_brevo_request,
            subject,
            body_html,
            recipient_email,
            sender_name,
            sender_email,
            api_key,
        )
        return True
    else:
        success = _execute_brevo_request(
            subject,
            body_html,
            recipient_email,
            sender_name,
            sender_email,
            api_key,
        )
        if not success:
            raise RuntimeError("Échec de l'envoi d'e-mail Brevo.")
        return True


def envoyer_notification_passage_poste_securite(
    site: str,
    nom_personne: str,
    organisme: str,
    heure: str,
    type_piece: str,
    num_piece: str,
    agent_garde: str,
):
    sujet = f"🛡️ [SÛRETÉ PC GARDE] Alerte Arrivée - {site} : {nom_personne}"
    corps_html = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h3 style="color: #0d6efd;">🛂 Pointage d'Entrée au PC Sécurité</h3>
        <p>Le poste de garde du site <b>{site}</b> vient d'enregistrer le passage suivant :</p>
        <ul>
            <li><b>Alerte :</b> {nom_personne} ({organisme})</li>
            <li><b>Heure de constatation :</b> {heure}</li>
            <li><b>Détails/Observations :</b> {type_piece} (N° {num_piece})</li>
            <li><b>Agent de garde :</b> {agent_garde}</li>
        </ul>
        <p style="font-size: 12px; color: #6c757d;"><i>Notification automatique générée par IDENTIS - Mouvements Sécurité.</i></p>
    </div>
    """
    send_alert_email(subject=sujet, body_html=corps_html, async_send=True)


def envoyer_notification_anomalie_ronde(
    site: str,
    titre_ronde: str,
    heure: str,
    details_anomalie: str,
    agent_garde: str,
):
    sujet = f"🛡️ [SÛRETÉ PC GARDE] Alerte Anomalie - Site {site} : {titre_ronde}"
    corps_html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h3 style="color: #d32f2f;">🚨 Notification d'Anomalie de Ronde</h3>
            <p>Le poste de garde du site <b>{site}</b> vient de consigner une anomalie :</p>
            <ul>
                <li><b>Type d'alerte :</b> {titre_ronde}</li>
                <li><b>Heure de constatation :</b> {heure}</li>
                <li><b>Détails / Observations :</b> {details_anomalie}</li>
                <li><b>Agent de garde :</b> {agent_garde}</li>
            </ul>
            <hr style="border: none; border-top: 1px solid #ccc;" />
            <p style="font-size: 11px; color: #777;">
                Notification automatique générée par ORBIS - Main Courante V3.
            </p>
        </body>
    </html>
    """
    send_alert_email(subject=sujet, body_html=corps_html, async_send=True)

import os
import threading
from pathlib import Path
import requests
import streamlit as st

# Chargement automatique du .env (méthode CENTAURE via find_dotenv)
try:
    from dotenv import load_dotenv, find_dotenv

    load_dotenv(find_dotenv())
except ImportError:
    # Fonction de secours native si python-dotenv n'est pas installé
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def get_secret(key: str, default: str = "") -> str:
    """Helper universel : Lit d'abord les variables d'environnement système (Render / GitHub Actions / .env),
    puis bascule sur st.secrets (Streamlit Cloud).
    """
    # 1. Priorité aux variables d'environnement système (Render / GitHub Actions / Local .env)
    if key in os.environ and os.environ[key]:
        return os.environ[key]

    # 2. Fallback sur st.secrets (Streamlit Cloud)
    try:
        if key in st.secrets and st.secrets[key]:
            return str(st.secrets[key])
    except Exception:
        pass

    return default


def send_alert_email(
    subject: str,
    body_html: str,
    recipient_email: str = "eric.kuter@gouv.nc",
    async_send: bool = False,
) -> bool:
    """Fonction principale d'envoi d'e-mail HTML via l'API REST HTTP v3 de Brevo.

    :param async_send: Si True, l'envoi se fait dans un Thread (idéal pour Streamlit).
                       Si False, l'envoi est synchrone (obligatoire pour GitHub Actions et tests).
    """

    def _envoyer():
        api_key = get_secret("BREVO_API_KEY", "")
        sender_email = get_secret("BREVO_SENDER_EMAIL", "")
        sender_name = get_secret("BREVO_SENDER_NAME", "ORBIS Sûreté")

        if not api_key or not sender_email:
            msg_err = "❌ [BREVO ERROR] Clé API ou Email expéditeur (BREVO_API_KEY / BREVO_SENDER_EMAIL) introuvables !"
            print(msg_err)
            return False

        # Configuration de la requête HTTP REST Brevo v3
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }

        # Découpage si plusieurs destinataires séparés par des virgules
        if isinstance(recipient_email, str):
            to_list = [
                {"email": e.strip()} for e in recipient_email.split(",") if e.strip()
            ]
        else:
            to_list = [{"email": e} for e in recipient_email]

        payload = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": to_list,
            "subject": subject,
            "htmlContent": body_html,
        }

        try:
            print(f"📧 Envoi de l'e-mail via API Brevo à {recipient_email}...")
            response = requests.post(url, json=payload, headers=headers, timeout=15)

            if response.status_code in [200, 201, 202]:
                print(
                    f"✅ [BREVO SUCCESS] E-mail transmis avec succès à {recipient_email}"
                )
                return True
            else:
                msg_err = (
                    f"❌ [BREVO ERROR] Code {response.status_code} : {response.text}"
                )
                print(msg_err)
                if not async_send:
                    raise RuntimeError(msg_err)
                return False

        except Exception as e:
            print(f"❌ [BREVO ERROR] Échec de l'envoi HTTP : {e}")
            if not async_send:
                raise e
            return False

    if async_send:
        # Mode Streamlit : Envoi en arrière-plan sans bloquer l'interface
        threading.Thread(target=_envoyer, daemon=True).start()
        return True
    else:
        # Mode Batch / GitHub Actions / Test Direct : Envoi bloquant
        return _envoyer()


def envoyer_notification_passage_poste_securite(
    site: str,
    nom_personne: str,
    organisme: str,
    heure: str,
    type_piece: str,
    num_piece: str,
    agent_garde: str,
):
    """Envoie un email de notification lors d'un passage au PC Sécurité (Mode Asynchrone pour Streamlit)."""
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
    """Envoie une alerte email dédiée en cas d'anomalie détectée pendant une ronde (Mode Asynchrone)."""
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

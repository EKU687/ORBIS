from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
import threading
import streamlit as st


def get_secret(key: str, default: str = "") -> str:
    """Helper universel : Lit d'abord les variables d'environnement système (GitHub Actions),

    puis bascule sur st.secrets (Streamlit Cloud).
    """
    # 1. Priorité aux variables d'environnement (GitHub Actions / Serveur)
    if key in os.environ and os.environ[key]:
        return os.environ[key]

    # 2. Fallback sur st.secrets (Streamlit Cloud / Local)
    try:
        if key in st.secrets:
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
    """Fonction principale d'envoi d'e-mail HTML via SMTP (Google Workspace / Gmail).

    :param async_send: Si True, l'envoi se fait dans un Thread (idéal pour
    Streamlit). Si False, l'envoi est synchrone (obligatoire pour GitHub
    Actions).
    """

    def _envoyer():
        smtp_server = get_secret("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(get_secret("SMTP_PORT", "465"))
        smtp_user = get_secret("SMTP_EMAIL", "")
        smtp_password = get_secret("SMTP_PASSWORD", "")

        if not smtp_user or not smtp_password:
            msg_err = "❌ [SMTP ERROR] Identifiants SMTP (SMTP_EMAIL / SMTP_PASSWORD) introuvables !"
            print(msg_err)
            return False

        # Construction du message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"ORBIS Sûreté <{smtp_user}>"
        msg["To"] = recipient_email
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            print(
                f"📧 Connexion SMTP à {smtp_server}:{smtp_port} pour {recipient_email}..."
            )

            if smtp_port == 465:
                with smtplib.SMTP_SSL(
                    smtp_server, smtp_port, timeout=15
                ) as server:
                    server.login(smtp_user, smtp_password)
                    server.sendmail(smtp_user, recipient_email, msg.as_string())
            else:
                with smtplib.SMTP(
                    smtp_server, smtp_port, timeout=15
                ) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                    server.sendmail(smtp_user, recipient_email, msg.as_string())

            print(
                f"✅ [SMTP SUCCESS] E-mail transmis avec succès à {recipient_email}"
            )
            return True

        except Exception as e:
            print(f"❌ [SMTP ERROR] Échec de l'envoi : {e}")
            if not async_send:
                # Si on est dans un script Batch (GitHub Actions), on lève l'erreur pour la voir dans les logs
                raise e
            return False

    if async_send:
        # Mode Streamlit : Envoi en arrière-plan sans bloquer l'agent
        threading.Thread(target=_envoyer, daemon=True).start()
        return True
    else:
        # Mode Batch / GitHub Actions : Envoi direct et bloquant
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
    sujet = f"🛡️ [SÛRETÉ PC GARDE] Alerte Anomalie Ronde - {site} : {nom_personne}"
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
    send_alert_email(
        subject=sujet, body_html=corps_html, async_send=True
    )


def envoyer_notification_anomalie_ronde(
    site: str,
    titre_ronde: str,
    heure: str,
    details_anomalie: str,
    agent_garde: str,
):
    """Envoie une alerte email dédiée en cas d'anomalie détectée pendant une ronde (Mode Asynchrone)."""
    sujet = (
        f"🛡️ [SÛRETÉ PC GARDE] Alerte Anomalie - Site {site} : {titre_ronde}"
    )
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
    send_alert_email(
        subject=sujet, body_html=corps_html, async_send=True
    )
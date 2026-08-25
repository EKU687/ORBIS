import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import streamlit as st

def send_alert_email(subject: str, body_html: str, recipient_email: str = "eric.kuter@gouv.nc") -> bool:
    """Envoie un e-mail d'alerte HTML via le serveur SMTP configuré dans secrets.toml."""
    try:
        # Récupération des identifiants SMTP
        smtp_server = st.secrets["SMTP_SERVER"]
        smtp_port = st.secrets["SMTP_PORT"]
        smtp_email = st.secrets["SMTP_EMAIL"]
        smtp_password = st.secrets["SMTP_PASSWORD"]

        # Construction du message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚨 [ORBIS ALERT] {subject}"
        msg["From"] = f"ORBIS Sûreté <{smtp_email}>"
        msg["To"] = recipient_email

        # Version HTML du mail
        html_part = MIMEText(body_html, "html", "utf-8")
        msg.attach(html_part)

        # Connexion sécurisée SSL (Port 465)
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, recipient_email, msg.as_string())

        return True
    except Exception as e:
        st.error(f"❌ Échec de l'envoi de l'e-mail : {e}")
        return False
    
def envoyer_notification_passage_poste_securite(
    site: str,
    nom_personne: str,
    organisme: str,
    heure: str,
    type_piece: str,
    num_piece: str,
    agent_garde: str,
):
    """Envoie un email de notification via Google Workspace (Port 465 SSL) en tâche de fond (asynchrone)."""

    def _job_envoi():
        try:
            # 1. Lecture directe des clés d'accès depuis .streamlit/secrets.toml
            smtp_server = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
            smtp_port = int(st.secrets.get("SMTP_PORT", 465))
            smtp_user = st.secrets.get("SMTP_EMAIL", "")
            smtp_password = st.secrets.get("SMTP_PASSWORD", "")

            # Adresse destinataire du Chargé de Sûreté / Administrateur
            destinataire = "eric.kuter@gouv.nc"

            if not smtp_user or not smtp_password:
                print(
                    "❌ [SMTP ERROR] Identifiants SMTP introuvables dans"
                    " secrets.toml !"
                )
                return

            # 2. Construction du mail au format HTML
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

            msg = MIMEMultipart("alternative")
            msg["Subject"] = sujet
            msg["From"] = smtp_user
            msg["To"] = destinataire
            msg.attach(MIMEText(corps_html, "html"))

            # 3. Connexion SSL sécurisée pour Google Workspace (Port 465)
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
                server.starttls()

            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [destinataire], msg.as_string())
            server.quit()

            print(
                "✅ [SMTP SUCCESS] Email envoyé avec succès à"
                f" {destinataire} via {smtp_user} !"
            )

        except Exception as e:
            print(f"❌ [SMTP ERROR] Échec lors de l'envoi de l'email : {e}")

    # Lancement de l'envoi dans un thread asynchrone pour ne pas ralentir Streamlit
    threading.Thread(target=_job_envoi, daemon=True).start()

def envoyer_notification_anomalie_ronde(
    site: str,
    titre_ronde: str,
    heure: str,
    details_anomalie: str,
    agent_garde: str,
):
    """Envoie une alerte email dédiée en cas d'anomalie détectée pendant une ronde."""
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

    # Utilise ta logique d'envoi SMTP existante dans email_sender.py
    # (Exemple : envoyer_email(sujet, corps_html, ...))
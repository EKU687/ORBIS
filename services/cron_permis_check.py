# =========================================================================
# CRON AUTOMATISÉ : VÉRIFICATION MATINALE DES PERMIS DE CONDUIRE
# Emplacement : services/cron_permis_check.py
# Inclus : Contrôle 90 jours, Suspension BDD Supabase, Notifications Email + CC Admin,
#          Inscriptions automatiques dans la Main Courante.
# =========================================================================
import datetime
import os
import smtplib
import sys
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# --- FIX DU CHEMIN DE L'APPLICATION ---
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import du client Supabase
from utils.db_client import supabase

TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")
DELAI_VALIDE_JOURS = 90

# Configuration SMTP (extraite des variables d'environnement)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_ADMIN_CC = os.getenv("EMAIL_ADMIN_CC", "eric.kuter@gouv.nc")  # 👈 Ta boîte e-mail en CC


def get_now_nc() -> datetime.datetime:
    return datetime.datetime.now(TZ_NC)


def envoyer_email_notification(email_agent: str, nom_complet: str, type_alerte: str, details: str):
    """Envoie un e-mail d'avertissement ou de suspension à l'agent avec l'admin en CC."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"⚠️ [SMTP] Identifiants absents. Mail non envoyé à {email_agent}.")
        return

    if not email_agent:
        print(f"⚠️ [SMTP] Aucun e-mail renseigné pour {nom_complet}.")
        return

    msg = MIMEMultipart("alternative")
    
    if type_alerte == "SUSPENSION":
        msg["Subject"] = "🚨 SUSPENSION : Autorisation de conduite des véhicules de service"
        couleur_titre = "#d9534f"
        titre_header = "🚨 Suspension de votre Autorisation de Conduite"
        texte_body = f"""
        <p>La période de validité de 90 jours de votre dernier contrôle de permis de conduire est arrivée à échéance ({details}).</p>
        <p>Conformément aux consignes de sécurité du site, <b>votre autorisation d'utilisation des véhicules de service est automatiquement suspendue</b> à compter de ce jour.</p>
        <hr style="border: none; border-top: 1px solid #ccc;">
        <p><b>Action requise :</b> Veuillez présenter votre permis de conduire original au PC Garde / Service Sûreté afin de renouveler votre contrôle réglementaire et rétablir vos droits.</p>
        """
    else:  # AVERTISSEMENT
        msg["Subject"] = "⚠️ RAPPEL : Renouvellement de votre contrôle de Permis de Conduire"
        couleur_titre = "#f0ad4e"
        titre_header = "⚠️ Expiration prochaine de votre Autorisation de Conduite"
        texte_body = f"""
        <p>Votre dernier contrôle de permis de conduire arrivera à échéance dans <b>{details} jour(s)</b>.</p>
        <p>Afin d'éviter toute interruption de vos droits de réservation de véhicule de service, merci de bien vouloir présenter votre permis au PC Garde rapidement.</p>
        """

    msg["From"] = SMTP_USER
    msg["To"] = email_agent
    msg["Cc"] = EMAIL_ADMIN_CC

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <h2 style="color: {couleur_titre};">{titre_header}</h2>
        <p>Bonjour <b>{nom_complet}</b>,</p>
        {texte_body}
        <br>
        <p><i>Message automatique généré par le système ORBIS V3 / Main Courante DINUM.</i></p>
      </body>
    </html>
    """
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            destinataires = [email_agent, EMAIL_ADMIN_CC]
            server.sendmail(SMTP_USER, destinataires, msg.as_string())
        print(f"📧 [EMAIL] Notification ({type_alerte}) envoyée à {email_agent} (CC: {EMAIL_ADMIN_CC})")
    except Exception as e:
        print(f"❌ [EMAIL] Erreur lors de l'envoi à {email_agent} : {e}")


def verifier_et_suspendre_permis():
    """Scan quotidien des permis de conduire :
    - Identifie les contrôles de plus de 90 jours.
    - Bascule `autorise_vehicule` à FALSE en BDD.
    - Envoie les notifications e-mails (Agent + CC Admin).
    - Inscrit l'événement dans la Main Courante.
    """
    aujourdhui = get_now_nc().date()
    print("=" * 60)
    print(f"🚀 [CRON PERMIS] Lancement du contrôle du {aujourdhui.strftime('%d/%m/%Y')}")
    print("=" * 60)

    try:
        # 1. Récupération des agents publics actifs déclarés autorisés
        res = (
            supabase.table("Agents_Publics")
            .select("id, id_ident, nom, prenom, email, date_dernier_controle_permis, autorise_vehicule")
            .eq("statut", "ACTIF")
            .eq("autorise_vehicule", True)
            .execute()
        )

        agents = res.data or []
        print(f"🔍 [ANALYSE] {len(agents)} agent(s) actuellement autorisé(s) à contrôler.")

        nb_suspendus = 0
        nb_avertissements = 0

        for ag in agents:
            nom_complet = f"{ag.get('prenom', '').title()} {ag.get('nom', '').upper()}".strip()
            email_agent = ag.get("email")
            date_ctrl_str = ag.get("date_dernier_controle_permis")

            # Cas 1 : Aucune date enregistrée alors qu'il est marqué autorisé -> Suspension
            if not date_ctrl_str:
                print(f"🚨 [SUSPENSION] {nom_complet} : Aucune date de contrôle -> Révocation.")
                supabase.table("Agents_Publics").update({"autorise_vehicule": False}).eq("id", ag["id"]).execute()
                
                envoyer_email_notification(email_agent, nom_complet, "SUSPENSION", "Aucun contrôle enregistré")
                
                # Inscription Main Courante
                supabase.table("main_courante").insert({
                    "site_id": "DINUM",
                    "agent_auteur": "SYSTEME_CRON",
                    "categorie": "SECURITE",
                    "titre": f"🔒 SUSPENSION AUTOMATIQUE PERMIS : {nom_complet}",
                    "description": "Révocation de l'autorisation véhicule : Aucune date de contrôle enregistrée.",
                    "horodatage": get_now_nc().isoformat(),
                    "statut": "CLOTURE",
                }).execute()
                
                nb_suspendus += 1
                continue

            dt_ctrl = datetime.date.fromisoformat(str(date_ctrl_str))
            dt_expiration = dt_ctrl + datetime.timedelta(days=DELAI_VALIDE_JOURS)
            jours_restants = (dt_expiration - aujourdhui).days

            # Cas 2 : Contrôle périmé (> 90 jours) -> Suspension BDD + Mail + Main Courante
            if jours_restants < 0:
                print(
                    f"🚨 [SUSPENSION] {nom_complet} : Périmé depuis {abs(jours_restants)} jour(s) "
                    f"(Dernier contrôle le {dt_ctrl.strftime('%d/%m/%Y')}) -> Révocation."
                )
                supabase.table("Agents_Publics").update({"autorise_vehicule": False}).eq("id", ag["id"]).execute()
                
                envoyer_email_notification(
                    email_agent, 
                    nom_complet, 
                    "SUSPENSION", 
                    f"Dernier contrôle le {dt_ctrl.strftime('%d/%m/%Y')}"
                )

                supabase.table("main_courante").insert({
                    "site_id": "DINUM",
                    "agent_auteur": "SYSTEME_CRON",
                    "categorie": "SECURITE",
                    "titre": f"🔒 SUSPENSION AUTOMATIQUE PERMIS : {nom_complet}",
                    "description": f"Dépassement du délai de 90 jours (Dernier contrôle le {dt_ctrl.strftime('%d/%m/%Y')}). Droit véhicule suspendu.",
                    "horodatage": get_now_nc().isoformat(),
                    "statut": "CLOTURE",
                }).execute()

                nb_suspendus += 1

            # Cas 3 : Avertissement (Expiration dans 7 jours ou moins) -> Mail de rappel
            elif jours_restants <= 7:
                print(
                    f"⚠️ [AVERTISSEMENT] {nom_complet} : Expire dans {jours_restants} jour(s) "
                    f"({dt_expiration.strftime('%d/%m/%Y')})."
                )
                envoyer_email_notification(email_agent, nom_complet, "AVERTISSEMENT", str(jours_restants))
                nb_avertissements += 1

        print("-" * 60)
        print(f"✅ [CRON FINI] Bilan : {nb_suspendus} suspension(s) effectuée(s), {nb_avertissements} alerte(s).")
        print("=" * 60)

    except Exception as err:
        print(f"❌ [ERREUR CRON] Dysfonctionnement lors de l'exécution : {err}")
        sys.exit(1)


if __name__ == "__main__":
    verifier_et_suspendre_permis()
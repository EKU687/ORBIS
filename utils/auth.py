import bcrypt
import streamlit as st
from utils.db_client import supabase


def verifier_mot_de_passe(mot_de_passe_saisi: str, mdp_stocke: str) -> bool:
    """Vérifie le mot de passe (soit en hash bcrypt, soit en texte brut si BDD héritée)."""
    if not mdp_stocke:
        return False

    # 1. Tentative de vérification bcrypt
    try:
        if mdp_stocke.startswith("$2b$") or mdp_stocke.startswith("$2a$"):
            return bcrypt.checkpw(
                mot_de_passe_saisi.encode("utf-8"), mdp_stocke.encode("utf-8")
            )
    except Exception:
        pass

    # 2. Fallback de comparaison directe
    return mot_de_passe_saisi == mdp_stocke


def authentifier_utilisateur(
    login_ou_email: str, mot_de_passe: str
) -> dict | None:
    """Authentifie l'utilisateur via son login PORTAIL-GNC ou son email."""
    identifiant = login_ou_email.strip().lower()

    try:
        # Recherche par login OU par email
        res = (
            supabase.table("Utilisateur")
            .select(
                "id, login, nom, service, role, mdp, email,"
                " changement_mdp_requis, site_defaut"
            )
            .or_(f"login.eq.{identifiant},email.eq.{identifiant}")
            .execute()
        )

        users = res.data or []
        if not users:
            return None

        user = users[0]
        mdp_bd = user.get("mdp", "")

        # Vérification du mot de passe
        if verifier_mot_de_passe(mot_de_passe, mdp_bd):
            nom_affiche = user.get("nom") or user.get("login") or "Agent"

            return {
                "id": user.get("id"),
                "login": user.get("login"),
                "email": user.get("email"),
                "full_name": nom_affiche.upper(),
                "service": user.get("service", "Sécurité"),
                "role": str(user.get("role", "agent")).lower().strip(),
                "site_defaut": user.get("site_defaut") or "DINUM",
                "changement_mdp_requis": user.get(
                    "changement_mdp_requis", False
                ),
            }

        return None

    except Exception as e:
        st.error(f"❌ Erreur BDD Authentification : {e}")
        return None
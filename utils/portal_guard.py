# =====================================================================
# MODULE : PORTEUR ET GARDE-FOU PORTAIL (utils/portal_guard.py)
# Verrouillage de l'accès direct par URL (Point d'Entrée Unique SSO)
# =====================================================================
import cadre_entreprise.auth as auth
from cadre_entreprise.database import supabase
import streamlit as st


def verifier_acces_depuis_portail() -> dict:
    """Vérifie que l'accès provient obligatoirement du Portail GNC.

    Si l'URL est saisie en direct sans jeton valide, l'application est bloquée.
    Retourne les informations de l'utilisateur authentifié.
    """
    # 1. Si la session locale Streamlit est déjà validée dans cet onglet
    if st.session_state.get("authenticated_from_portal") and st.session_state.get("user_info"):
        return st.session_state["user_info"]

    # 2. Récupération du jeton depuis l'URL (ex: ?session_token=GNC-APP-XXXX)
    query_params = st.query_params
    token_url = query_params.get("session_token")

    # Si aucun jeton n'est présent dans l'URL ➔ BLOCAGE IMMÉDIAT
    if not token_url:
        afficher_ecran_blocage(
            "Aucun jeton de session détecté. Vous devez obligatoirement"
            " lancer cette application depuis le Portail Central GNC."
        )

    # 3. Validation du jeton auprès de Supabase (Table Sessions_Portail)
    try:
        res_session = (
            supabase.table("Sessions_Portail")
            .select("*, Utilisateur(id, login, nom, role, service, site_defaut)")
            .eq("token", token_url)
            .eq("actif", True)
            .execute()
        )
        sessions_list = res_session.data or []

        if not sessions_list:
            afficher_ecran_blocage(
                "Le jeton de session est invalide ou a expiré. Veuillez relancer"
                " l'application depuis le Portail Central GNC."
            )

        session_data = sessions_list[0]
        user_info = session_data.get("Utilisateur", {})

        if not user_info:
            afficher_ecran_blocage(
                "Utilisateur introuvable ou compte désactivé dans REFERO."
            )

        # 4. Invalidation/Mise en cache local de la session Streamlit
        st.session_state["authenticated_from_portal"] = True
        st.session_state["user_info"] = user_info
        st.session_state["session_token_actuel"] = token_url

        return user_info

    except Exception as err:
        afficher_ecran_blocage(
            f"Erreur lors du contrôle de sécurité du Portail : {err}"
        )


def afficher_ecran_blocage(message_erreur: str):
    """Affiche une page d'accès refusé stylisée et stoppe le script Streamlit."""
    st.error("⛔ **ACCÈS NON AUTORISÉ — PORTAIL CENTRAL GNC REQUIS**")

    st.markdown(
        f"""
        <div style="
            background-color: #fff3cd;
            border-left: 5px solid #ffc107;
            padding: 15px;
            border-radius: 6px;
            margin-top: 10px;
            margin-bottom: 20px;
            color: #856404;
            font-family: Arial, sans-serif;
        ">
            <b>🔒 Règle de Sécurité Institutionnelle :</b><br>
            {message_erreur}
        </div>
        """,
        unsafe_allow_html=True,
    )

    url_portail = "https://portail-gnc.streamlit.app"

    st.markdown(
        f"""
        <a href="{url_portail}" target="_self">
            <button style="
                background-color: #0d6efd;
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 6px;
                cursor: pointer;
                width: 100%;
            ">
                👉 Se connecter sur le Portail Central GNC
            </button>
        </a>
        """,
        unsafe_allow_html=True,
    )

    # 🛑 ARRÊT STRICT STREAMLIT
    st.stop()


def deconnecter_et_retourner_portail():
    """Invalide le jeton Supabase et ferme l'onglet courant (ou redirige vers le Portail)."""
    token_actuel = st.session_state.get("session_token_actuel")

    # 1. Invalidation du jeton dans Supabase (Sécurité BDD)
    if token_actuel:
        try:
            supabase.table("Sessions_Portail").update({"actif": False}).eq(
                "token", token_actuel
            ).execute()
        except Exception as e:
            print(f"⚠️ Erreur lors de l'invalidation du jeton : {e}")

    # 2. Nettoyage de la session locale Streamlit
    st.session_state.clear()

    # URL de secours
    url_portail = "https://portail-gnc.streamlit.app"

    # 3. Injection JS propre pour fermeture d'onglet + Redirection de secours
    st.markdown(
        f"""
        <script type="text/javascript">
            // Tentative 1 : Fermeture de l'onglet courant
            window.close();
            
            // Tentative 2 : Si le navigateur bloque window.close(), redirection vers le Portail
            setTimeout(function() {{
                window.location.href = "{url_portail}";
            }}, 300);
        </script>
        <div style="padding: 20px; text-align: center;">
            <h3>🔒 Session fermée avec succès.</h3>
            <p>Vous pouvez fermer cet onglet ou <a href="{url_portail}">cliquer ici pour revenir au Portail GNC</a>.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 🛑 Arrêt strict pour empêcher la ré-exécution du script Streamlit
    st.stop()
import streamlit as st
from utils.auth import authentifier_utilisateur


def show_login_page():
    """Affiche la mire de connexion sécurisée."""
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col_box, _ = st.columns([1, 2, 1])

    with col_box:
        with st.container(border=True):
            st.title("🛡️ MAIN COURANTE V3")
            st.subheader("Portail d'Accès Sécurité & PC Garde")
            st.caption("Identifiants uniques du Portail GNC.")

            login_input = st.text_input(
                "Identifiant (Login ou Email) :",
                placeholder="ex: ekuter ou eric.kuter@gouv.nc",
            )
            pass_input = st.text_input("Mot de passe :", type="password")

            if st.button(
                "🚀 Connexion", type="primary", use_container_width=True
            ):
                if not login_input or not pass_input:
                    st.warning("⚠️ Veuillez remplir tous les champs.")
                    return

                profil = authentifier_utilisateur(login_input, pass_input)

                if profil:
                    # Enregistrement dans la session Streamlit
                    st.session_state["authenticated"] = True
                    st.session_state["user_profile"] = profil
                    st.session_state["site_actif"] = profil["site_defaut"]

                    st.toast(
                        f"Bienvenue {profil['full_name']} !", icon="✅"
                    )
                    st.rerun()
                else:
                    st.error("❌ Identifiants incorrects ou compte introuvable.")
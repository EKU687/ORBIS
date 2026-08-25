import streamlit as st


def show():
    st.title("🌐 Hypervision COS (Centre Opérationnel de Sûreté)")
    st.caption("Synthèse multi-sites et supervision en temps réel du GNC.")

    st.markdown("---")

    # Carte d'information temporaire
    st.info(
        "🚧 **Module en cours de préparation (Phase DSUP)**\n\n"
        "Ce composant centralisera la synthèse des mains courantes ouvertes sur l'ensemble des sites de la Nouvelle-Calédonie.\n\n"
        "**Fonctionnalités à venir :**\n"
        "* 📊 Vue consolidée des événements inter-sites.\n"
        "* 🚨 Alertes globales et suivi des incidents majeurs.\n"
        "* 📈 Statistiques d'activité du COS en temps réel."
    )

    # Indicateur visuel de statut
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Statut du Module", value="En Développement", delta="DSUP Target")
    with col2:
        st.metric(label="Mains Courantes Connectées", value="0 / --", delta="Attente API")
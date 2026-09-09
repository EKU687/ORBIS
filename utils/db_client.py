# =========================================================================
# CLIENT BD UNIVERSAL SUPABASE (utils/db_client.py)
# Compatible : Streamlit App, App Mobile, Scripts CLI & Cron GitHub Actions
# =========================================================================
import os
from supabase import create_client, Client


def get_secret(key: str, default: str = "") -> str:
    """Récupère une clé depuis os.environ (GitHub Actions) ou st.secrets (Streamlit)."""
    # 1. Priorité aux variables d'environnement système (GitHub Actions / Server)
    val = os.getenv(key)
    if val:
        return val

    # 2. Fallback sur st.secrets si nous sommes dans Streamlit
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    return default


def init_supabase() -> Client:
    """Initialise le client Supabase de manière universelle."""
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")

    if not url or not key:
        raise ValueError(
            "❌ Impossible d'initialiser Supabase : SUPABASE_URL ou SUPABASE_KEY manquants."
        )

    return create_client(url, key)


# Initialisation universelle du singleton Supabase
try:
    import streamlit as st

    # Si Streamlit est disponible et dans un contexte de runtime, on utilise le cache
    @st.cache_resource
    def get_cached_supabase() -> Client:
        return init_supabase()

    supabase = get_cached_supabase()
except Exception:
    # Mode ligne de commande / GitHub Actions (sans le runtime Streamlit)
    supabase = init_supabase()
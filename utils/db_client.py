import os
import streamlit as st
from supabase import create_client, Client

def get_secret(key: str, default: str = "") -> str:
    """Récupère une clé depuis os.environ (GitHub Actions) ou st.secrets (Streamlit)."""
    # 1. Priorité aux variables d'environnement système (GitHub Actions / Server)
    if key in os.environ and os.environ[key]:
        return os.environ[key]
    # 2. Fallback sur st.secrets (Streamlit Cloud)
    try:
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

# Initialisation sécurisée hors décorateur Streamlit si exécuté hors session
try:
    # Si nous sommes dans une session Streamlit active, on peut cacher la ressource
    @st.cache_resource
    def get_cached_supabase():
        return init_supabase()
    
    supabase = get_cached_supabase()
except Exception:
    # Mode ligne de commande / GitHub Actions (hors session Streamlit)
    supabase = init_supabase()
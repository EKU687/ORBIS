# debug_bridge.py
import toml
from supabase import create_client

# Chargement des secrets Streamlit local
secrets = toml.load(".streamlit/secrets.toml")
supabase = create_client(secrets["SUPABASE_URL"], secrets["SUPABASE_KEY"])

print("\n=== 🕵️ AUDIT BDD PASSERELLE OPERA <-> ORBIS ===")

# 1. Liste des sites
sites = supabase.table("opera_sites").select("*").execute().data
print("\n📍 1. Sites enregistrés (opera_sites) :")
for s in sites:
    print(f"   - ID: {s.get('id')} | Nom: '{s.get('nom_site')}'")

# 2. Liste des notifications
notifs = supabase.table("opera_orbis_notifications").select("*").execute().data
print("\n🔔 2. Notifications actives (opera_orbis_notifications) :")
for n in notifs:
    print(
        f"   - ID Notif: {n.get('id')} | Site UUID: {n.get('site_id')} | Active: {n.get('est_active')} | Vers: v{n.get('version_cible')}"
    )

# 3. Liste des émargements
emargements = supabase.table("opera_emargements").select("*").execute().data
print("\n✍️ 3. Émargements enregistrés (opera_emargements) :")
for e in emargements:
    print(
        f"   - Agent: {e.get('agent_login')} | Proc_ID: {e.get('procedure_id')} | Version: {e.get('version_emargee')}"
    )
print("\n===============================================\n")

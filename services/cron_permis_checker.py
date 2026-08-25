import datetime
import os
import sys
from pathlib import Path

# --- FIX DU CHEMIN DE L'APPLICATION ---
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import du client Supabase
from utils.db_client import supabase

DELAI_VALIDE_JOURS = 90


def verifier_et_suspendre_permis():
    """Scan quotidien des permis de conduire :

    - Identifie les contrôles de plus de 90 jours.
    - Bascule `autorise_vehicule` à FALSE en BDD.
    - Génère un rapport d'exécution.
    """
    aujourdhui = datetime.date.today()
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
            nom_complet = f"{ag.get('nom', '').upper()} {ag.get('prenom', '').title()}"
            date_ctrl_str = ag.get("date_dernier_controle_permis")

            # Cas 1 : Aucune date enregistrée alors qu'il est marqué autorisé -> Suspension
            if not date_ctrl_str:
                print(f"🚨 [SUSPENSION] {nom_complet} : Aucune date de contrôle -> Révocation.")
                supabase.table("Agents_Publics").update({"autorise_vehicule": False}).eq("id", ag["id"]).execute()
                nb_suspendus += 1
                continue

            dt_ctrl = datetime.date.fromisoformat(str(date_ctrl_str))
            dt_expiration = dt_ctrl + datetime.timedelta(days=DELAI_VALIDE_JOURS)
            jours_restants = (dt_expiration - aujourdhui).days

            # Cas 2 : Contrôle périmé (> 90 jours) -> Suspension BDD
            if jours_restants < 0:
                print(
                    f"🚨 [SUSPENSION] {nom_complet} : Périmé depuis {abs(jours_restants)} jour(s) "
                    f"(Dernier contrôle le {dt_ctrl.strftime('%d/%m/%Y')}) -> Révocation."
                )
                supabase.table("Agents_Publics").update({"autorise_vehicule": False}).eq("id", ag["id"]).execute()
                nb_suspendus += 1

            # Cas 3 : Avertissement (Expiration dans 7 jours ou moins)
            elif jours_restants <= 7:
                print(
                    f"⚠️ [AVERTISSEMENT] {nom_complet} : Expire dans {jours_restants} jour(s) "
                    f"({dt_expiration.strftime('%d/%m/%Y')})."
                )
                nb_avertissements += 1

        print("-" * 60)
        print(f"✅ [CRON FINI] Bilan : {nb_suspendus} suspension(s) effectuée(s), {nb_avertissements} alerte(s).")
        print("=" * 60)

    except Exception as err:
        print(f"❌ [ERREUR CRON] Dysfonctionnement lors de l'exécution : {err}")
        sys.exit(1)


if __name__ == "__main__":
    verifier_et_suspendre_permis()
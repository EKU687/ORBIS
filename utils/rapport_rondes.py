import datetime
import zoneinfo
from utils.db_client import supabase
from utils.email_sender import send_alert_email
from views.suivi_rondes import generer_grille_rondes_du_jour

TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def generer_et_envoyer_rapport_nuit_tous_sites():
    """Génère et envoie par e-mail le rapport des rondes de la nuit pour chaque site actif."""
    now_nc = datetime.datetime.now(TZ_NC)
    today = now_nc.date()
    yesterday = today - datetime.timedelta(days=1)

    # Bornes temporelles ISO
    dt_debut_nuit = datetime.datetime.combine(
        yesterday, datetime.time(20, 0), tzinfo=TZ_NC
    )
    dt_fin_nuit = datetime.datetime.combine(
        today, datetime.time(5, 0), tzinfo=TZ_NC
    )

    # Récupération des sites actifs
    try:
        res_sites = (
            supabase.table("Sites")
            .select("nom_site")
            .eq("actif", True)
            .execute()
        )
        sites = [
            s["nom_site"] for s in (res_sites.data or []) if s.get("nom_site")
        ]
    except Exception as e:
        print(f"⚠️ Erreur chargement sites : {e}")
        sites = ["SITE OUEMO", "SITE DOUMER"]

    for site_id in sites:
        # 1. Grille théorique de la nuit (20:00 -> 05:00)
        grille_hier = generer_grille_rondes_du_jour(yesterday)
        creneaux_nuit = [
            r
            for r in grille_hier
            if r["heure_cible"]
            in [
                "20:00",
                "21:00",
                "22:00",
                "23:00",
                "00:00",
                "01:00",
                "02:00",
                "03:00",
                "04:00",
                "05:00",
            ]
        ]

        # 2. Récupération des émargements en BDD
        rondes_realisees = {}
        try:
            res_r = (
                supabase.table("mc_evenements")
                .select("*")
                .eq("site_id", site_id)
                .eq("type_evenement", "RONDE")
                .gte("horodatage", dt_debut_nuit.isoformat())
                .lte("horodatage", dt_fin_nuit.isoformat())
                .execute()
            )
            for ev in res_r.data or []:
                rondes_realisees[ev.get("reference", "")] = ev
        except Exception as err:
            print(f"Erreur lecture BDD : {err}")

        # 3. Bilan et détection des omissions
        nb_ok = 0
        nb_ko = 0
        lignes_html = ""

        for r_theo in creneaux_nuit:
            h_target = r_theo["heure_cible"]
            date_ref = (
                yesterday if int(h_target.split(":")[0]) >= 20 else today
            )
            ref_cle = f"REF-RONDE-{date_ref.strftime('%Y%m%d')}-{h_target}"

            if ref_cle in rondes_realisees:
                nb_ok += 1
                ev = rondes_realisees[ref_cle]
                heure_f = ev.get("horodatage", "")[11:16]
                agent_f = ev.get("agent_nom", "Agent")
                lignes_html += f"""
                <tr style="background-color: #e8f5e9;">
                    <td><b>{h_target}</b></td>
                    <td>{r_theo['type']}</td>
                    <td style="color: green;"><b>✅ EFFECTUÉE</b> ({heure_f})</td>
                    <td>{agent_f}</td>
                </tr>
                """
            else:
                nb_ko += 1
                lignes_html += f"""
                <tr style="background-color: #ffebee;">
                    <td><b>{h_target}</b></td>
                    <td>{r_theo['type']}</td>
                    <td style="color: red;"><b>🔴 NON EXÉCUTÉE</b></td>
                    <td>-</td>
                </tr>
                """

        taux = (
            round((nb_ok / len(creneaux_nuit)) * 100, 1) if creneaux_nuit else 0
        )

        # 4. Construction de l'e-mail HTML
        sujet = f"📊 Rapport Rondes de Nuit — {site_id} ({today.strftime('%d/%m/%Y')})"
        corps_html = f"""
        <h2>🔦 Bilan des Rondes de Nuit — {site_id}</h2>
        <p><b>Période analysée :</b> Du {yesterday.strftime('%d/%m/%Y')} 20:00 au {today.strftime('%d/%m/%Y')} 05:00</p>
        <ul>
            <li><b>Rondes effectuées :</b> {nb_ok} / {len(creneaux_nuit)}</li>
            <li><b>Rondes manquées :</b> <span style="color:red;"><b>{nb_ko}</b></span></li>
            <li><b>Taux de conformité :</b> <b>{taux}%</b></li>
        </ul>
        <br>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th>Créneau</th>
                    <th>Type de Ronde</th>
                    <th>Statut</th>
                    <th>Agent</th>
                </tr>
            </thead>
            <tbody>
                {lignes_html}
            </tbody>
        </table>
        <br>
        <p><small>Rapport automatique généré par ORBIS Main Courante V3.</small></p>
        """

        # Envoi de l'e-mail au Chargé de Sûreté
        send_alert_email(
            subject=sujet,
            body_html=corps_html,
            recipient_email="eric.kuter@gouv.nc",
        )
        print(f"✉️ Rapport de nuit transmis pour {site_id}")


if __name__ == "__main__":
    generer_et_envoyer_rapport_nuit_tous_sites()
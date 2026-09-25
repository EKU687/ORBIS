# 🛡️ ORBIS — Main Courante Service Terrain (V3)

[![Version](https://img.shields.io/badge/Version-v3.1.0-blue.svg)](https://github.com/)
[![Environnement](https://img.shields.io/badge/Environnement-PRODUCTION-brightgreen.svg)](https://portail-gnc.streamlit.app)
[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.x-red.svg)](https://streamlit.io/)
[![Database](https://img.shields.io/badge/Supabase-PostgreSQL-green.svg)](https://supabase.com/)

> **ORBIS Main Courante** est l'application métier dédiée à la traçabilité des événements de sécurité, à la gestion des vacations, au suivi des anomalies matérielles et à l'émargement obligatoire des consignes pour le PC Garde & Service Terrain.

---

## 📌 Fonctionnalités Principales

* 📝 **Main Courante & Journal de Bord :** Saisie d'événements horodatés en temps réel avec fuseau horaire dédié (`Pacific/Noumea` UTC+11).
* 📋 **Prise de Poste & Émargement Numérique :** Modale obligatoire de prise de connaissance des consignes et anomalies avec traçabilité juridique en base de données.
* 🚨 **Gestion des Anomalies & Directives Site :** Traçabilité des pannes matérielles et des consignes générales sans péremption automatique.
* 🎯 **Consignes Ciblées (Admin) :** Interface de création de consignes particulières temporaires attribuées spécifiquement à un agent ou un groupe d'agents.
* 🚪 **Moniteur des Mouvements & Présences :** Console dédiée aux flux d'entrées/sorties et gestion des visiteurs attendus/imprévus.
* 🔑 **Authentification Hybride (SSO & SDK) :** Prise en charge du SSO Portail HUB et secours par clé matérielle **YubiKey** / Mot de passe.

---

## 🛠️ Stack Technique & Outils

* **Langage & Framework :** Python 3.14 / Streamlit
* **Backend :** Supabase (PostgreSQL 15+, RLS, Realtime)
* **Fuseau Horaire Applicatif :** `Pacific/Noumea` (UTC+11)
* **Qualité de code :** PEP 8 strict (Black Formatter & Linter Ruff)
* **CI/CD & Déploiement :** Streamlit Cloud (Déploiement automatique sur merge `main`)

---

## 🚀 Installation & Lancement en Local

### 1. Prérequis
* Python 3.14+
* Git

### 2. Cloner le dépôt
```bash
git clone [https://github.com/votre-orga/main-courante.git](https://github.com/votre-orga/main-courante.git)
cd main-courante
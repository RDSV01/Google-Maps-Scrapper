# Google-Maps-Scrapper

Script Python qui scrape Google Maps pour extraire des informations sur des établissements, puis visite automatiquement leurs sites web pour y collecter des adresses email.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Key Features](#key-features)
- [Installation](#installation)
- [Usage](#usage)
- [Examples](#examples)
- [Notes](#notes)

## Prerequisites

- Python 3.8+
- Chromium (installé automatiquement via Playwright)

## Key Features

- **Google Maps scraping** : nom, adresse, site web, téléphone, note, nombre d'avis, type d'établissement, horaires, description.
- **Email harvesting** : pour chaque fiche, le script visite le site web et scrape les emails disponibles (page principale + page contact en fallback).
- **Limite d'emails par site** : configurable pour éviter de récupérer des dizaines d'adresses génériques depuis un même site.
- **Gestion du consentement** : acceptation automatique de la page de cookies Google.
- **Délai aléatoire** : pause variable entre 0.5s et 2s entre chaque site pour limiter la détection.
- **Export CSV** : toutes les données dans un fichier CSV, avec support de l'append.
- **Mode interactif** : lancement sans arguments pour une configuration guidée en terminal.

## Installation

1. Cloner le dépôt :

   ```bash
   git clone https://github.com/RDSV01/Google-Maps-Scrapper.git
   cd Google-Maps-Scrapper
   ```

2. Installer les dépendances Python :

   ```bash
   pip install -r requirements.txt
   ```

3. Installer Chromium pour Playwright :
   ```bash
   playwright install chromium
   ```

## Usage

### Mode interactif (recommandé)

```bash
python main.py
```

Le script pose les questions suivantes :

- Requête Google Maps
- Nombre de fiches à scraper
- Fichier de sortie
- Nombre d'emails maximum par site
- Exclure l'export des fiches sans site web ou sans email

### Mode ligne de commande

```bash
python main.py -s "avocat paris" -t 20
```

## Examples

Scraper 20 avocats à Paris avec 1 email max par site :

```bash
python main.py -s "avocat paris" -t 20 --max-per-site 1
```

Ajouter des résultats à un fichier existant :

```bash
python main.py -s "restaurants paris 15e" -t 50 -o paris.csv --append
```

Scraper uniquement les données Maps sans les emails :

```bash
python main.py -s "plombiers lyon" -t 30 --no-emails
```

## Notes

- Le navigateur s'ouvre en mode visible (non headless) pour contourner les protections de Google Maps.
- Les XPaths Google Maps peuvent changer à tout moment. En cas de données manquantes, vérifier et mettre à jour les sélecteurs dans `main.py`.
- Ne pas lancer des volumes trop importants en peu de temps pour éviter d'être bloqué par Google.
- Chrome est détecté automatiquement s'il est installé. Sinon, le Chromium bundlé de Playwright est utilisé.

## License

MIT

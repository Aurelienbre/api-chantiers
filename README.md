# API de Pilotage RIP

API FastAPI pour la gestion des chantiers, préparateurs et planifications.

## 🚀 Déploiement sur Render

Cette application est prête pour le déploiement sur Render avec migration automatique des données.

### Configuration requise

- **Runtime** : Python 3.9+
- **Build Command** : `pip install -r requirements.txt`
- **Start Command** : `python main.py`

## 📊 Fonctionnalités

- **Migration automatique** : Conversion des données JSON vers SQLite au premier démarrage
- **Gestion des chantiers** : CRUD complet (création, lecture, mise à jour, suppression)
- **Gestion des préparateurs** : Liste et gestion des préparateurs
- **Planification** : Système de planification par semaines
- **Disponibilités** : Gestion des disponibilités des préparateurs

## 🛠 API Endpoints

### Chantiers
- `GET /chantiers` - Liste tous les chantiers
- `POST /ajouter` - Ajoute un nouveau chantier
- `PUT /chantiers/{id}` - Met à jour un chantier
- `PUT /chantiers/bulk` - Mise à jour en masse
- `DELETE /chantiers/{id}` - Supprime un chantier
- `POST /cloturer` - Clôture un chantier

### Préparateurs & Disponibilités
- `GET /preparateurs` - Liste tous les préparateurs
- `GET /disponibilites` - Récupère toutes les disponibilités
- `PUT /disponibilites` - Met à jour une disponibilité

## 📝 Structure des données

- **SQLite** : Base de données principale (créée automatiquement)
- **JSON** : Données initiales pour la migration (utilisées une seule fois)

## 🔧 Installation locale

```bash
pip install -r requirements.txt
python main.py
```

L'API sera accessible sur `http://localhost:8000`

## 📋 Variables d'environnement

- `PORT` : Port d'écoute (par défaut: 8000)

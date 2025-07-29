from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import sqlite3

DB_SQLITE = "db.sqlite3"
DB_JSON = "db.json"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Migration automatique JSON -> SQLite ---
def migrate_json_to_sqlite():
    """Migration initiale des données JSON vers SQLite - à exécuter une seule fois"""
    if not os.path.exists(DB_JSON):
        print("db.json introuvable, migration annulée.")
        return
    
    print("Début de la migration JSON -> SQLite...")
    with open(DB_JSON, encoding="utf-8") as f:
        db = json.load(f)

    conn = sqlite3.connect(DB_SQLITE)
    cur = conn.cursor()

    cur.executescript("""
    DROP TABLE IF EXISTS disponibilites;
    DROP TABLE IF EXISTS planifications;
    DROP TABLE IF EXISTS chantiers;
    DROP TABLE IF EXISTS preparateurs;

    CREATE TABLE preparateurs (
        nom TEXT PRIMARY KEY,
        nni TEXT
    );

    CREATE TABLE disponibilites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        preparateur_nom TEXT,
        semaine TEXT,
        minutes INTEGER,
        updatedAt TEXT,
        FOREIGN KEY (preparateur_nom) REFERENCES preparateurs(nom)
    );

    CREATE TABLE chantiers (
        id TEXT PRIMARY KEY,
        label TEXT,
        status TEXT,
        prepTime INTEGER,
        endDate TEXT,
        preparateur_nom TEXT,
        ChargeRestante INTEGER,
        FOREIGN KEY (preparateur_nom) REFERENCES preparateurs(nom)
    );

    CREATE TABLE planifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chantier_id TEXT,
        semaine TEXT,
        minutes INTEGER,
        FOREIGN KEY (chantier_id) REFERENCES chantiers(id)
    );
    """)

    # Remplir preparateurs
    for nom, nni in db.get("preparateurs", {}).items():
        cur.execute("INSERT INTO preparateurs (nom, nni) VALUES (?, ?)", (nom, nni))

    # Remplir disponibilites
    for nom, semaines in db.get("data", {}).items():
        for semaine, val in semaines.items():
            if isinstance(val, dict):  # S'assurer que val est un dictionnaire
                cur.execute(
                    "INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt) VALUES (?, ?, ?, ?)",
                    (nom, semaine, val.get("minutes", 0), val.get("updatedAt"))
                )

    # Remplir chantiers et planifications
    for ch_id, ch in db.get("chantiers", {}).items():
        cur.execute(
            "INSERT INTO chantiers (id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ch.get("id", ch_id),
                ch.get("label"),
                ch.get("status"),
                ch.get("prepTime"),
                ch.get("endDate"),
                ch.get("preparateur"),
                ch.get("ChargeRestante")
            )
        )
        # Planification
        for semaine, minutes in (ch.get("planification") or {}).items():
            cur.execute(
                "INSERT INTO planifications (chantier_id, semaine, minutes) VALUES (?, ?, ?)",
                (ch.get("id", ch_id), semaine, minutes)
            )

    conn.commit()
    conn.close()
    print("Migration JSON -> SQLite terminée.")

# Migration conditionnelle : ne migre que si SQLite n'existe pas
if not os.path.exists(DB_SQLITE):
    migrate_json_to_sqlite()

# --- Fonctions utilitaires SQL ---
def get_db():
    return sqlite3.connect(DB_SQLITE)

def chantier_to_dict(row, planif=None):
    return {
        "id": row[0],
        "label": row[1],
        "status": row[2],
        "prepTime": row[3],
        "endDate": row[4],
        "preparateur": row[5],
        "ChargeRestante": row[6],
        "planification": planif or {}
    }

def get_planification_for_chantier(conn, chantier_id):
    cur = conn.cursor()
    cur.execute("SELECT semaine, minutes FROM planifications WHERE chantier_id = ?", (chantier_id,))
    return {semaine: minutes for semaine, minutes in cur.fetchall()}

# --- Endpoints FastAPI (lecture seule) ---

@app.get("/chantiers")
def get_chantiers():
    """Récupère tous les chantiers avec leurs planifications"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante FROM chantiers")
    chantiers = {}
    for row in cur.fetchall():
        planif = get_planification_for_chantier(conn, row[0])
        chantiers[row[0]] = chantier_to_dict(row, planif)
    conn.close()
    return chantiers

@app.get("/preparateurs")
def get_preparateurs():
    """Récupère tous les préparateurs"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT nom, nni FROM preparateurs")
    preparateurs = {nom: nni for nom, nni in cur.fetchall()}
    conn.close()
    return preparateurs

@app.get("/disponibilites")
def get_disponibilites():
    """Récupère toutes les disponibilités"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT preparateur_nom, semaine, minutes, updatedAt FROM disponibilites")
    disponibilites = {}
    for nom, semaine, minutes, updated_at in cur.fetchall():
        if nom not in disponibilites:
            disponibilites[nom] = {}
        disponibilites[nom][semaine] = {
            "minutes": minutes,
            "updatedAt": updated_at
        }
    conn.close()
    return disponibilites

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

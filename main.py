from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from database_config import get_database_connection
from migration import migrate_json_to_db, check_tables_exist

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Migration automatique au démarrage
if not check_tables_exist():
    migrate_json_to_db()
else:
    print("Tables déjà existantes, migration ignorée")

# --- Fonctions utilitaires SQL ---
def get_db():
    return get_database_connection()

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
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:  # PostgreSQL
        cur.execute("SELECT semaine, minutes FROM planifications WHERE chantier_id = %s", (chantier_id,))
    else:  # SQLite
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

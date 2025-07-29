from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, List
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

# --- Modèles Pydantic ---
class Disponibilite(BaseModel):
    preparateur_nom: str
    semaine: str
    minutes: int = 0
    updatedAt: Optional[str] = None
class Chantier(BaseModel):
    id: str = Field(..., example="TEST")
    label: str = Field(..., example="TEST")
    status: str = Field(..., example="Nouveau")
    prepTime: int = Field(..., example=900)
    endDate: str = Field(..., example="05/08/2025")
    preparateur: Optional[str] = Field(None, example="Sylvain MATHAIS")
    planification: Dict[str, Any] = Field(default_factory=dict)
    ChargeRestante: int = Field(...)

class ChantierUpdate(BaseModel):
    label: Optional[str]
    status: Optional[str]
    prepTime: Optional[int]
    endDate: Optional[str]
    preparateur: Optional[str]
    planification: Optional[Dict[str, Any]]
    ChargeRestante: Optional[int]

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

# --- Endpoints FastAPI ---
@app.get("/chantiers")
def get_chantiers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante FROM chantiers")
    chantiers = {}
    for row in cur.fetchall():
        planif = get_planification_for_chantier(conn, row[0])
        chantiers[row[0]] = chantier_to_dict(row, planif)
    conn.close()
    return chantiers

@app.post("/ajouter", status_code=201)
def ajouter_chantier(chantier: Chantier):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM chantiers WHERE id = ?", (chantier.id,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Chantier déjà existant")
    cur.execute(
        "INSERT INTO chantiers (id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chantier.id, chantier.label, chantier.status, chantier.prepTime, chantier.endDate, chantier.preparateur, chantier.ChargeRestante)
    )
    # Planification
    for semaine, minutes in (chantier.planification or {}).items():
        cur.execute(
            "INSERT INTO planifications (chantier_id, semaine, minutes) VALUES (?, ?, ?)",
            (chantier.id, semaine, minutes)
        )
    conn.commit()
    conn.close()
    return {"message": f"Chantier {chantier.id} ajouté.", "chantier": chantier.dict()}

@app.put("/chantiers/{ch_id}")
def update_chantier(ch_id: str, update: ChantierUpdate):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chantiers WHERE id = ?", (ch_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    chantier = chantier_to_dict(row, get_planification_for_chantier(conn, ch_id))
    updates = update.dict(exclude_unset=True)
    # Met à jour les champs simples
    for key in ["label", "status", "prepTime", "endDate", "preparateur", "ChargeRestante"]:
        if key in updates:
            chantier[key] = updates[key]
    # Met à jour la planification
    if "planification" in updates and isinstance(updates["planification"], dict):
        for semaine, minutes in updates["planification"].items():
            cur.execute(
                "INSERT OR REPLACE INTO planifications (chantier_id, semaine, minutes) VALUES (?, ?, ?)",
                (ch_id, semaine, minutes)
            )
    # Update chantier
    cur.execute(
        "UPDATE chantiers SET label=?, status=?, prepTime=?, endDate=?, preparateur_nom=?, ChargeRestante=? WHERE id=?",
        (chantier["label"], chantier["status"], chantier["prepTime"], chantier["endDate"], chantier["preparateur"], chantier["ChargeRestante"], ch_id)
    )
    conn.commit()
    conn.close()
    return {"message": f"Chantier {ch_id} mis à jour.", "chantier": chantier}

@app.put("/chantiers/bulk", status_code=200)
def bulk_update_chantiers(chantiers_list: List[Chantier]):
    conn = get_db()
    cur = conn.cursor()
    # Supprime tout
    cur.execute("DELETE FROM planifications")
    cur.execute("DELETE FROM chantiers")
    # Réinsère tout
    for chantier in chantiers_list:
        cur.execute(
            "INSERT INTO chantiers (id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chantier.id, chantier.label, chantier.status, chantier.prepTime, chantier.endDate, chantier.preparateur, chantier.ChargeRestante)
        )
        for semaine, minutes in (chantier.planification or {}).items():
            cur.execute(
                "INSERT INTO planifications (chantier_id, semaine, minutes) VALUES (?, ?, ?)",
                (chantier.id, semaine, minutes)
            )
    conn.commit()
    conn.close()
    return {"message": "Tous les chantiers ont été mis à jour."}

@app.post("/cloturer")
def cloturer_chantier(payload: Dict[str, str]):
    ch_id = payload.get("id")
    if not ch_id:
        raise HTTPException(status_code=400, detail="ID manquant")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chantiers WHERE id = ?", (ch_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    cur.execute("UPDATE chantiers SET status=? WHERE id=?", ("Clôturé", ch_id))
    conn.commit()
    conn.close()
    return {"message": f"Chantier {ch_id} clôturé."}

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

@app.put("/disponibilites")
def update_disponibilite(dispo: Disponibilite):
    """Met à jour une disponibilité"""
    conn = get_db()
    cur = conn.cursor()
    
    # Vérifier que le préparateur existe
    cur.execute("SELECT 1 FROM preparateurs WHERE nom = ?", (dispo.preparateur_nom,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Préparateur introuvable")
    
    # Insérer ou mettre à jour la disponibilité
    cur.execute("""
        INSERT OR REPLACE INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt) 
        VALUES (?, ?, ?, datetime('now'))
    """, (dispo.preparateur_nom, dispo.semaine, dispo.minutes))
    
    conn.commit()
    conn.close()
    return {"message": f"Disponibilité mise à jour pour {dispo.preparateur_nom} semaine {dispo.semaine}"}

@app.delete("/chantiers/{ch_id}")
def delete_chantier(ch_id: str):
    """Supprime un chantier et ses planifications"""
    conn = get_db()
    cur = conn.cursor()
    
    # Vérifier que le chantier existe
    cur.execute("SELECT 1 FROM chantiers WHERE id = ?", (ch_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    
    # Supprimer les planifications puis le chantier
    cur.execute("DELETE FROM planifications WHERE chantier_id = ?", (ch_id,))
    cur.execute("DELETE FROM chantiers WHERE id = ?", (ch_id,))
    
    conn.commit()
    conn.close()
    return {"message": f"Chantier {ch_id} supprimé"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

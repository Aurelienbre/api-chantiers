from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
import json
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "db.json"

class Chantier(BaseModel):
    id: str
    label: str
    statut: str
    prepTime: int
    endDate: str
    preparateur: Optional[str] = None
    planification: Dict[str, Any] = {}
    ChargeRestante: int

class ChantierUpdate(BaseModel):
    label: Optional[str]
    statut: Optional[str]
    prepTime: Optional[int]
    endDate: Optional[str]
    preparateur: Optional[str]
    planification: Optional[Dict[str, Any]]
    ChargeRestante: Optional[int]

def charger_donnees() -> Dict[str, Any]:
    if not os.path.isfile(DB_PATH):
        raise HTTPException(status_code=500, detail="Fichier de base de données introuvable")
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_donnees(data: Dict[str, Any]) -> None:
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.get("/chantiers")
def get_chantiers():
    return charger_donnees()

@app.post("/ajouter", status_code=201)
def ajouter_chantier(chantier: Chantier):
    data = charger_donnees()
    if chantier.id in data:
        raise HTTPException(status_code=400, detail="Chantier déjà existant")
    data[chantier.id] = chantier.dict()
    sauvegarder_donnees(data)
    return {"message": f"Chantier {chantier.id} ajouté.", "chantier": data[chantier.id]}

@app.put("/chantiers/{ch_id}")
def update_chantier(ch_id: str, update: ChantierUpdate):
    data = charger_donnees()
    if ch_id not in data:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    existing = data[ch_id]
    for k, v in update.dict(exclude_unset=True).items():
        existing[k] = v
    sauvegarder_donnees(data)
    return {"message": f"Chantier {ch_id} mis à jour.", "chantier": existing}

@app.post("/cloturer")
def cloturer_chantier(payload: Dict[str, str]):
    data = charger_donnees()
    ch_id = payload.get("id")
    if not ch_id or ch_id not in data:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    data[ch_id]["statut"] = "Clôturé"
    sauvegarder_donnees(data)
    return {"message": f"Chantier {ch_id} clôturé.", "chantier": data[ch_id]}

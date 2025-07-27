from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
from typing import Dict
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Chantier(BaseModel):
    id: str
    label: str
    statut: str

def charger_donnees():
    with open("db.json", "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_donnees(data):
    with open("db.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.get("/chantiers")
def get_chantiers():
    return charger_donnees()

@app.post("/cloturer")
def cloturer_chantier(payload: Dict[str, str]):
    data = charger_donnees()
    ch_id = payload.get("id")
    if ch_id not in data:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    data[ch_id]["statut"] = "Clôturé"
    sauvegarder_donnees(data)
    return {"message": f"Chantier {ch_id} clôturé."}

@app.post("/ajouter")
def ajouter_chantier(payload: Dict[str, str]):
    data = charger_donnees()
    ch_id = payload.get("id")
    if ch_id in data:
        raise HTTPException(status_code=400, detail="Chantier déjà existant")
    data[ch_id] = {
        "id": ch_id,
        "label": payload.get("label", ""),
        "statut": payload.get("statut", "Nouveau")
    }
    sauvegarder_donnees(data)
    return {"message": f"Chantier {ch_id} ajouté."}

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "db.json"

class Chantier(BaseModel):
    id: str = Field(..., example="CH-000123")
    label: str = Field(..., example="Pose de carrelage")
    statut: str = Field(..., example="Nouveau")
    prepTime: int = Field(..., description="Durée de préparation en minutes", ge=0)
    endDate: str = Field(..., description="Date de fin au format DD/MM/YYYY", example="31/07/2025")
    preparateur: Optional[str] = Field(None, description="Nom du préparateur affecté")
    planification: Dict[str, Any] = Field(default_factory=dict, description="Planification détaillée")
    ChargeRestante: int = Field(..., description="Charge restante en minutes", ge=0)


def charger_donnees() -> Dict[str, Any]:
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def sauvegarder_donnees(data: Dict[str, Any]) -> None:
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.get("/chantiers")
def get_chantiers():
    """Retourne tous les chantiers stockés."""
    return charger_donnees()


@app.post("/ajouter", status_code=201)
def ajouter_chantier(chantier: Chantier):
    """Ajoute un nouveau chantier et le stocke dans db.json."""
    data = charger_donnees()
    if chantier.id in data:
        raise HTTPException(status_code=400, detail="Chantier déjà existant")
    # Construire l'objet JSON à stocker
    obj = chantier.dict()
    data[chantier.id] = obj
    sauvegarder_donnees(data)
    return {"message": f"Chantier {chantier.id} ajouté.", "chantier": obj}


@app.post("/cloturer")
def cloturer_chantier(payload: Dict[str, str]):
    """Met à jour le statut d'un chantier en 'Clôturé'."""
    data = charger_donnees()
    ch_id = payload.get("id")
    if not ch_id or ch_id not in data:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    data[ch_id]["statut"] = "Clôturé"
    sauvegarder_donnees(data)
    return {"message": f"Chantier {ch_id} clôturé.", "chantier": data[ch_id]}


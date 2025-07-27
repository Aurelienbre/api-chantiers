from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, List
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
    id: str = Field(..., example="TEST")
    label: str = Field(..., example="TEST")
    status: Optional[str] = None
    prepTime: int = Field(..., description="Durée de préparation en minutes", ge=0, example=900)
    endDate: str = Field(..., description="Date de fin au format DD/MM/YYYY", example="05/08/2025")
    preparateur: Optional[str] = Field(None, description="Nom du préparateur affecté", example="Sylvain MATHAIS")
    planification: Dict[str, Any] = Field(default_factory=dict, description="Planification détaillée")
    ChargeRestante: int = Field(..., description="Charge restante en minutes")

    class Config:
        allow_population_by_field_name = True
        extra = "allow"

class ChantierUpdate(BaseModel):
    label: Optional[str]
    status: Optional[str]
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
    """Retourne tous les chantiers stockés."""
    return charger_donnees()

@app.post("/ajouter", status_code=201)
def ajouter_chantier(chantier: Chantier):
    """Ajoute un nouveau chantier et le stocke dans db.json."""
    data = charger_donnees()
    if chantier.id in data:
        raise HTTPException(status_code=400, detail="Chantier déjà existant")
    data[chantier.id] = chantier.dict()
    sauvegarder_donnees(data)
    return {"message": f"Chantier {chantier.id} ajouté.", "chantier": data[chantier.id]}

@app.put("/chantiers/{ch_id}")
def update_chantier(ch_id: str, update: ChantierUpdate):
    """Met à jour un chantier existant partiellement."""
    data = charger_donnees()
    if ch_id not in data:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    existing = data[ch_id]
    updates = update.dict(exclude_unset=True)
    # Merge planification if provided
    if 'planification' in updates and isinstance(updates['planification'], dict):
        existing['planification'].update(updates.pop('planification'))
    existing.update(updates)
    data[ch_id] = existing
    sauvegarder_donnees(data)
    return {"message": f"Chantier {ch_id} mis à jour.", "chantier": existing}

@app.put("/chantiers/bulk", status_code=200)
def bulk_update_chantiers(chantiers_list: List[Chantier]):
    """Remplace l'ensemble des chantiers et leurs planifications."""
    data = {c.id: c.dict() for c in chantiers_list}
    sauvegarder_donnees(data)
    return {"message": "Tous les chantiers ont été mis à jour.", "chantiers": data}

@app.post("/cloturer")
def cloturer_chantier(payload: Dict[str, str]):
    """Met à jour le statut d'un chantier en 'Clôturé'."""
    data = charger_donnees()
    ch_id = payload.get("id")
    if not ch_id or ch_id not in data:
        raise HTTPException(status_code=404, detail="Chantier introuvable")
    data[ch_id]["status"] = "Clôturé"
    sauvegarder_donnees(data)
    return {"message": f"Chantier {ch_id} clôturé.", "chantier": data[ch_id]}

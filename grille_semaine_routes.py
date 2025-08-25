"""
Routes pour la gestion des étiquettes de planification (Grille semaine.html)

Ce module contient toutes les routes relatives à :
- La gestion des horaires des préparateurs
- La gestion des étiquettes de grille
- Les planifications d'étiquettes
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Optional, Any
import os
import json
from main import get_db_connection, close_db_connection


# Créer le router pour les routes Grille Semaine
router = APIRouter(
    prefix="",
    tags=["Grille Semaine Étiquettes"],
    responses={404: {"description": "Not found"}},
)


def ensure_etiquettes_grille_tables(conn):
    """S'assurer que les tables pour les étiquettes de grille existent"""
    cur = conn.cursor()
    
    # Table principale des étiquettes de grille
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etiquettes_grille (
            id SERIAL PRIMARY KEY,
            type_activite VARCHAR(255) NOT NULL,
            description TEXT,
            group_id VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table des planifications d'étiquettes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS planifications_etiquettes (
            id SERIAL PRIMARY KEY,
            etiquette_id INTEGER NOT NULL REFERENCES etiquettes_grille(id) ON DELETE CASCADE,
            date_jour DATE NOT NULL,
            heure_debut TIME NOT NULL,
            heure_fin TIME NOT NULL,
            preparateurs TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT check_heures CHECK (heure_debut < heure_fin)
        )
    """)
    
    # Index pour améliorer les performances
    cur.execute("CREATE INDEX IF NOT EXISTS idx_etiquettes_type ON etiquettes_grille (type_activite)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_etiquettes_group ON etiquettes_grille (group_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planifications_etiquette ON planifications_etiquettes (etiquette_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planifications_date ON planifications_etiquettes (date_jour)")
    
    conn.commit()


# ========================================================================
#  GESTION DES ETIQUETTES DE PLANIFICATION (Grille semaine.html)
# ========================================================================

# Horaires des préparateurs 

@router.get("/horaires")
def get_all_horaires():
    """Récupérer tous les horaires de tous les préparateurs"""
    conn = None
    try:
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier si la table horaires existe
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'horaires_preparateurs'
        """)
        table_exists = cur.fetchone()
        
        if not table_exists:
            # Créer la table si elle n'existe pas
            cur.execute("""
                CREATE TABLE horaires_preparateurs (
                    id SERIAL PRIMARY KEY,
                    preparateur_nom VARCHAR(255) NOT NULL,
                    jour_semaine VARCHAR(20) NOT NULL,
                    heure_debut TIME NOT NULL,
                    heure_fin TIME NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Index pour améliorer les performances
                    CONSTRAINT check_jour_semaine CHECK (jour_semaine IN ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'))
                )
            """)
            
            # Créer des index
            cur.execute("CREATE INDEX idx_horaires_preparateur ON horaires_preparateurs (preparateur_nom)")
            cur.execute("CREATE INDEX idx_horaires_jour ON horaires_preparateurs (jour_semaine)")
            
            # Trigger pour mettre à jour updated_at
            cur.execute("""
                CREATE TRIGGER update_horaires_updated_at 
                BEFORE UPDATE ON horaires_preparateurs 
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
            """)
            
            conn.commit()
            return {"message": "Table horaires_preparateurs créée", "horaires": {}}
        
        # Récupérer tous les horaires
        cur.execute("""
            SELECT preparateur_nom, jour_semaine, heure_debut, heure_fin
            FROM horaires_preparateurs
            ORDER BY preparateur_nom, 
                     CASE jour_semaine 
                         WHEN 'lundi' THEN 1 
                         WHEN 'mardi' THEN 2 
                         WHEN 'mercredi' THEN 3 
                         WHEN 'jeudi' THEN 4 
                         WHEN 'vendredi' THEN 5 
                         WHEN 'samedi' THEN 6 
                         WHEN 'dimanche' THEN 7 
                     END,
                     heure_debut
        """)
        
        results = cur.fetchall()
        
        # Organiser les données par préparateur
        horaires = {}
        for row in results:
            preparateur_nom, jour_semaine, heure_debut, heure_fin = row
            
            if preparateur_nom not in horaires:
                horaires[preparateur_nom] = {
                    'lundi': [], 'mardi': [], 'mercredi': [], 'jeudi': [], 
                    'vendredi': [], 'samedi': [], 'dimanche': []
                }
            
            horaires[preparateur_nom][jour_semaine].append({
                'debut': str(heure_debut),
                'fin': str(heure_fin)
            })
        
        return horaires
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des horaires: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.get("/horaires/{preparateur_nom}")
def get_horaires_preparateur(preparateur_nom: str):
    """Récupérer les horaires d'un préparateur spécifique"""
    conn = None
    try:
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT jour_semaine, heure_debut, heure_fin
            FROM horaires_preparateurs
            WHERE preparateur_nom = %s
            ORDER BY CASE jour_semaine 
                         WHEN 'lundi' THEN 1 
                         WHEN 'mardi' THEN 2 
                         WHEN 'mercredi' THEN 3 
                         WHEN 'jeudi' THEN 4 
                         WHEN 'vendredi' THEN 5 
                         WHEN 'samedi' THEN 6 
                         WHEN 'dimanche' THEN 7 
                     END,
                     heure_debut
        """, (preparateur_nom,))
        
        results = cur.fetchall()
        
        # Organiser les données par jour
        horaires = {
            'lundi': [], 'mardi': [], 'mercredi': [], 'jeudi': [], 
            'vendredi': [], 'samedi': [], 'dimanche': []
        }
        
        for row in results:
            jour_semaine, heure_debut, heure_fin = row
            horaires[jour_semaine].append({
                'debut': str(heure_debut),
                'fin': str(heure_fin)
            })
        
        return horaires
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des horaires: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.put("/horaires/{preparateur_nom}")
def update_horaires_preparateur(preparateur_nom: str, horaires_data: Dict[str, Any]):
    """Mettre à jour les horaires d'un préparateur"""
    conn = None
    try:
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Supprimer tous les horaires existants pour ce préparateur
        cur.execute("DELETE FROM horaires_preparateurs WHERE preparateur_nom = %s", (preparateur_nom,))
        
        # Insérer les nouveaux horaires
        for jour, creneaux in horaires_data.items():
            if jour in ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'] and creneaux:
                for creneau in creneaux:
                    if isinstance(creneau, dict) and 'debut' in creneau and 'fin' in creneau:
                        cur.execute("""
                            INSERT INTO horaires_preparateurs (preparateur_nom, jour_semaine, heure_debut, heure_fin)
                            VALUES (%s, %s, %s, %s)
                        """, (preparateur_nom, jour, creneau['debut'], creneau['fin']))
        
        conn.commit()
        
        return {
            "status": "✅ Horaires mis à jour",
            "preparateur": preparateur_nom,
            "message": f"Horaires de {preparateur_nom} synchronisés avec succès"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour des horaires: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.post("/horaires")
def sync_all_horaires(horaires_data: Dict[str, Any]):
    """Synchroniser tous les horaires des préparateurs"""
    conn = None
    try:
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier/créer la table si nécessaire
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'horaires_preparateurs'
        """)
        table_exists = cur.fetchone()
        
        if not table_exists:
            # Créer la table
            cur.execute("""
                CREATE TABLE horaires_preparateurs (
                    id SERIAL PRIMARY KEY,
                    preparateur_nom VARCHAR(255) NOT NULL,
                    jour_semaine VARCHAR(20) NOT NULL,
                    heure_debut TIME NOT NULL,
                    heure_fin TIME NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT check_jour_semaine CHECK (jour_semaine IN ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'))
                )
            """)
            
            cur.execute("CREATE INDEX idx_horaires_preparateur ON horaires_preparateurs (preparateur_nom)")
            cur.execute("CREATE INDEX idx_horaires_jour ON horaires_preparateurs (jour_semaine)")
            
            cur.execute("""
                CREATE TRIGGER update_horaires_updated_at 
                BEFORE UPDATE ON horaires_preparateurs 
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
            """)
        
        # Supprimer tous les horaires existants
        cur.execute("DELETE FROM horaires_preparateurs")
        
        # Insérer tous les nouveaux horaires
        total_creneaux = 0
        for preparateur_nom, horaires in horaires_data.items():
            if isinstance(horaires, dict):
                for jour, creneaux in horaires.items():
                    if jour in ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'] and creneaux:
                        for creneau in creneaux:
                            if isinstance(creneau, dict) and 'debut' in creneau and 'fin' in creneau:
                                cur.execute("""
                                    INSERT INTO horaires_preparateurs (preparateur_nom, jour_semaine, heure_debut, heure_fin)
                                    VALUES (%s, %s, %s, %s)
                                """, (preparateur_nom, jour, creneau['debut'], creneau['fin']))
                                total_creneaux += 1
        
        conn.commit()
        
        return {
            "status": "✅ Synchronisation complète",
            "message": f"Horaires de {len(horaires_data)} préparateur(s) synchronisés",
            "total_creneaux": total_creneaux
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la synchronisation: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.delete("/horaires/{preparateur_nom}")
def delete_horaires_preparateur(preparateur_nom: str):
    """Supprimer tous les horaires d'un préparateur"""
    conn = None
    try:
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Compter les horaires avant suppression
        cur.execute("SELECT COUNT(*) FROM horaires_preparateurs WHERE preparateur_nom = %s", (preparateur_nom,))
        count_before = cur.fetchone()[0]
        
        # Supprimer les horaires
        cur.execute("DELETE FROM horaires_preparateurs WHERE preparateur_nom = %s", (preparateur_nom,))
        
        conn.commit()
        
        return {
            "status": "✅ Horaires supprimés",
            "preparateur": preparateur_nom,
            "creneaux_supprimes": count_before
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)



# Gestion des étiquettes de planification

@router.get("/etiquettes-grille")
def get_all_etiquettes_grille():
    """Récupérer toutes les étiquettes de la grille semaine avec leurs planifications"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Récupérer toutes les étiquettes avec leurs planifications
        cur.execute("""
            SELECT 
                e.id, e.type_activite, e.description, e.group_id, 
                e.created_at, e.updated_at,
                p.id as planif_id, p.date_jour, p.heure_debut, p.heure_fin, p.preparateurs
            FROM etiquettes_grille e
            LEFT JOIN planifications_etiquettes p ON e.id = p.etiquette_id
            ORDER BY e.created_at DESC, p.date_jour ASC, p.heure_debut ASC
        """)
        
        results = cur.fetchall()
        
        # Grouper les résultats par étiquette
        etiquettes = {}
        for row in results:
            etiquette_id = row[0]
            
            if etiquette_id not in etiquettes:
                etiquettes[etiquette_id] = {
                    "id": row[0],
                    "type_activite": row[1],
                    "description": row[2],
                    "group_id": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "updated_at": row[5].isoformat() if row[5] else None,
                    "planifications": []
                }
            
            # Ajouter la planification si elle existe
            if row[6]:  # planif_id
                etiquettes[etiquette_id]["planifications"].append({
                    "id": row[6],
                    "date_jour": row[7].strftime('%Y-%m-%d'),
                    "heure_debut": row[8],
                    "heure_fin": row[9],
                    "preparateurs": row[10]
                })
        
        etiquettes_list = list(etiquettes.values())
        
        return {
            "status": "✅ Étiquettes récupérées",
            "count": len(etiquettes_list),
            "etiquettes": etiquettes_list
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.post("/etiquettes-grille")
def create_etiquette_grille(etiquette_data: Dict[str, Any]):
    """Créer une nouvelle étiquette de la grille semaine avec ses planifications"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Valider les données requises
        required_fields = ['type_activite', 'planifications']
        for field in required_fields:
            if field not in etiquette_data:
                raise HTTPException(status_code=400, detail=f"Champ requis manquant: {field}")
        
        if not etiquette_data['planifications']:
            raise HTTPException(status_code=400, detail="Au moins une planification est requise")
        
        # Créer l'étiquette principale
        cur.execute("""
            INSERT INTO etiquettes_grille (type_activite, description, group_id)
            VALUES (%s, %s, %s)
            RETURNING id, created_at, updated_at
        """, (
            etiquette_data['type_activite'],
            etiquette_data.get('description'),
            etiquette_data.get('group_id')
        ))
        
        etiquette_result = cur.fetchone()
        etiquette_id = etiquette_result[0]
        
        # Créer les planifications
        planifications_creees = []
        for planif in etiquette_data['planifications']:
            # Valider les champs de planification
            required_planif_fields = ['date_jour', 'heure_debut', 'heure_fin', 'preparateurs']
            for field in required_planif_fields:
                if field not in planif:
                    raise HTTPException(status_code=400, detail=f"Champ planification requis manquant: {field}")
            
            # Valider les heures
            if planif['heure_debut'] >= planif['heure_fin']:
                raise HTTPException(status_code=400, detail=f"Heure de début ({planif['heure_debut']}) doit être < heure de fin ({planif['heure_fin']})")
            
            # Insérer la planification
            cur.execute("""
                INSERT INTO planifications_etiquettes (etiquette_id, date_jour, heure_debut, heure_fin, preparateurs)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, created_at
            """, (
                etiquette_id,
                planif['date_jour'],
                planif['heure_debut'],
                planif['heure_fin'],
                planif['preparateurs']
            ))
            
            planif_result = cur.fetchone()
            planifications_creees.append({
                "id": planif_result[0],
                "date_jour": planif['date_jour'],
                "heure_debut": planif['heure_debut'],
                "heure_fin": planif['heure_fin'],
                "preparateurs": planif['preparateurs'],
                "created_at": planif_result[1].isoformat()
            })
        
        conn.commit()
        
        return {
            "status": "✅ Étiquette créée",
            "etiquette": {
                "id": etiquette_id,
                "type_activite": etiquette_data['type_activite'],
                "description": etiquette_data.get('description'),
                "group_id": etiquette_data.get('group_id'),
                "created_at": etiquette_result[1].isoformat(),
                "updated_at": etiquette_result[2].isoformat(),
                "planifications": planifications_creees
            }
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.put("/etiquettes-grille/{etiquette_id}")
def update_etiquette_grille(etiquette_id: int, etiquette_data: Dict[str, Any]):
    """Mettre à jour une étiquette de la grille semaine"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Vérifier que l'étiquette existe
        cur.execute("SELECT id FROM etiquettes_grille WHERE id = %s", (etiquette_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Étiquette non trouvée")
        
        # Mettre à jour les informations de l'étiquette
        update_fields = []
        update_values = []
        
        for field in ['type_activite', 'description', 'group_id']:
            if field in etiquette_data:
                update_fields.append(f"{field} = %s")
                update_values.append(etiquette_data[field])
        
        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            update_values.append(etiquette_id)
            
            query = f"""
                UPDATE etiquettes_grille 
                SET {', '.join(update_fields)}
                WHERE id = %s
            """
            cur.execute(query, update_values)
        
        # Mettre à jour les planifications si fournies
        if 'planifications' in etiquette_data:
            # Supprimer les anciennes planifications
            cur.execute("DELETE FROM planifications_etiquettes WHERE etiquette_id = %s", (etiquette_id,))
            
            # Créer les nouvelles planifications
            for planif in etiquette_data['planifications']:
                cur.execute("""
                    INSERT INTO planifications_etiquettes (etiquette_id, date_jour, heure_debut, heure_fin, preparateurs)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    etiquette_id,
                    planif['date_jour'],
                    planif['heure_debut'],
                    planif['heure_fin'],
                    planif['preparateurs']
                ))
        
        conn.commit()
        
        return {
            "status": "✅ Étiquette mise à jour",
            "etiquette_id": etiquette_id
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.put("/etiquettes-grille/{etiquette_id}/horaires")
def update_etiquette_horaires(etiquette_id: int, horaires_data: Dict[str, Any]):
    """Mettre à jour seulement les heures d'une planification d'étiquette (sans toucher aux préparateurs)"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Vérifier que l'étiquette existe
        cur.execute("SELECT id FROM etiquettes_grille WHERE id = %s", (etiquette_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Étiquette non trouvée")
        
        # Vérifier les champs requis
        required_fields = ['planification_id', 'heure_debut', 'heure_fin']
        for field in required_fields:
            if field not in horaires_data:
                raise HTTPException(status_code=400, detail=f"Champ requis manquant: {field}")
        
        # Valider les heures
        if horaires_data['heure_debut'] >= horaires_data['heure_fin']:
            raise HTTPException(status_code=400, detail=f"Heure de début ({horaires_data['heure_debut']}) doit être < heure de fin ({horaires_data['heure_fin']})")
        
        # Mettre à jour seulement les heures de la planification spécifique
        cur.execute("""
            UPDATE planifications_etiquettes 
            SET heure_debut = %s, heure_fin = %s
            WHERE id = %s AND etiquette_id = %s
        """, (
            horaires_data['heure_debut'],
            horaires_data['heure_fin'],
            horaires_data['planification_id'],
            etiquette_id
        ))
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Planification non trouvée pour cette étiquette")
        
        # Mettre à jour le timestamp de l'étiquette
        cur.execute("""
            UPDATE etiquettes_grille 
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (etiquette_id,))
        
        conn.commit()
        
        return {
            "status": "✅ Horaires mis à jour",
            "etiquette_id": etiquette_id,
            "planification_id": horaires_data['planification_id']
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour des horaires: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.post("/etiquettes-grille/{etiquette_id}/planifications")
def add_planification_to_etiquette(etiquette_id: int, planification_data: dict):
    """Ajouter une nouvelle planification à une étiquette existante"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Vérifier que l'étiquette existe
        cur.execute("SELECT id FROM etiquettes_grille WHERE id = %s", (etiquette_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Étiquette non trouvée")
        
        # Vérifier les données requises
        required_fields = ['date_jour', 'heure_debut', 'heure_fin', 'preparateurs']
        for field in required_fields:
            if field not in planification_data:
                raise HTTPException(status_code=422, detail=f"Champ manquant: {field}")
        
        # Insérer la nouvelle planification
        cur.execute("""
            INSERT INTO planifications_etiquettes 
            (etiquette_id, date_jour, heure_debut, heure_fin, preparateurs)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (
            etiquette_id,
            planification_data['date_jour'],
            planification_data['heure_debut'],
            planification_data['heure_fin'],
            planification_data['preparateurs']
        ))
        
        planification_id = cur.fetchone()[0]
        
        # Mettre à jour le timestamp de l'étiquette
        cur.execute("""
            UPDATE etiquettes_grille 
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (etiquette_id,))
        
        conn.commit()
        
        return {
            "status": "✅ Planification ajoutée",
            "etiquette_id": etiquette_id,
            "planification_id": planification_id,
            "date_jour": planification_data['date_jour'],
            "heure_debut": planification_data['heure_debut'],
            "heure_fin": planification_data['heure_fin'],
            "preparateurs": planification_data['preparateurs']
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'ajout de la planification: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.put("/etiquettes-grille/{etiquette_id}/planifications/{planification_id}")
def update_planification_specifique(etiquette_id: int, planification_id: int, update_data: Dict[str, Any]):
    """Mettre à jour une planification spécifique (date, heures, et un seul préparateur)"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Vérifier que l'étiquette et la planification existent
        cur.execute("""
            SELECT id, preparateurs FROM planifications_etiquettes 
            WHERE id = %s AND etiquette_id = %s
        """, (planification_id, etiquette_id))
        
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Planification non trouvée pour cette étiquette")
        
        current_preparateurs = result[1]
        
        # Vérifier les champs requis
        required_fields = ['nouveau_preparateur', 'date_jour', 'heure_debut', 'heure_fin']
        for field in required_fields:
            if field not in update_data:
                raise HTTPException(status_code=400, detail=f"Champ requis manquant: {field}")
        
        # Valider les heures
        if update_data['heure_debut'] >= update_data['heure_fin']:
            raise HTTPException(status_code=400, detail=f"Heure de début ({update_data['heure_debut']}) doit être < heure de fin ({update_data['heure_fin']})")
        
        # Logique pour modifier le préparateur dans la liste
        preparateurs_list = [p.strip() for p in current_preparateurs.split(',')] if current_preparateurs else []
        nouveau_preparateur = update_data['nouveau_preparateur'].strip()
        ancien_preparateur = update_data.get('ancien_preparateur', '').strip()  # Optionnel
        
        print(f"🔧 Mise à jour planification {planification_id}:")
        print(f"   📋 Données reçues: {update_data}")
        print(f"   👥 Préparateurs actuels: {preparateurs_list}")
        print(f"   👤 Ancien préparateur: '{ancien_preparateur}' (type: {type(ancien_preparateur)})")
        print(f"   👤 Nouveau préparateur: '{nouveau_preparateur}' (type: {type(nouveau_preparateur)})")
        print(f"   🔍 Ancien préparateur in list: {ancien_preparateur in preparateurs_list if ancien_preparateur else 'N/A'}")
        
        # Si on a spécifié l'ancien préparateur, on le remplace spécifiquement
        if ancien_preparateur and ancien_preparateur in preparateurs_list:
            # Remplacer spécifiquement l'ancien préparateur
            index = preparateurs_list.index(ancien_preparateur)
            preparateurs_list[index] = nouveau_preparateur
            print(f"🔄 Remplacement spécifique: '{ancien_preparateur}' → '{nouveau_preparateur}' (position {index})")
        
        elif nouveau_preparateur not in preparateurs_list:
            if preparateurs_list:
                # Pas d'ancien préparateur spécifié, remplacer le premier par défaut
                ancien_prep_defaut = preparateurs_list[0]
                preparateurs_list[0] = nouveau_preparateur
                print(f"🔄 Remplacement par défaut: '{ancien_prep_defaut}' → '{nouveau_preparateur}' (premier préparateur)")
                print(f"   ⚠️ Raison: ancien_preparateur='{ancien_preparateur}' non trouvé dans {preparateurs_list}")
            else:
                # Ajouter si la liste est vide
                preparateurs_list = [nouveau_preparateur]
                print(f"➕ Ajout nouveau préparateur: '{nouveau_preparateur}'")
        else:
            print(f"ℹ️ Préparateur '{nouveau_preparateur}' déjà présent, pas de changement")
        
        # 🚨 NOUVELLE LOGIQUE : Détecter et supprimer les doublons
        preparateurs_avant_dedoublonnage = preparateurs_list.copy()
        
        # Créer une liste sans doublons en préservant l'ordre
        preparateurs_dedoublonnes = []
        for prep in preparateurs_list:
            if prep and prep not in preparateurs_dedoublonnes:  # Ignorer les chaînes vides aussi
                preparateurs_dedoublonnes.append(prep)
        
        # Vérifier s'il y avait des doublons
        doublons_detectes = len(preparateurs_avant_dedoublonnage) != len(preparateurs_dedoublonnes)
        doublons_supprimes = len(preparateurs_avant_dedoublonnage) - len(preparateurs_dedoublonnes)
        
        if doublons_detectes:
            print(f"🔍 DOUBLONS DETECTÉS:")
            print(f"   📋 Avant dédoublonnage: {preparateurs_avant_dedoublonnage} ({len(preparateurs_avant_dedoublonnage)} éléments)")
            print(f"   ✅ Après dédoublonnage: {preparateurs_dedoublonnes} ({len(preparateurs_dedoublonnes)} éléments)")
            print(f"   🗑️ {doublons_supprimes} doublon(s) supprimé(s)")
        
        preparateurs_list = preparateurs_dedoublonnes
        nouveaux_preparateurs = ','.join(preparateurs_list)
        print(f"   👥 Nouveaux préparateurs finaux: {nouveaux_preparateurs}")
        
        # Mettre à jour la planification
        cur.execute("""
            UPDATE planifications_etiquettes 
            SET date_jour = %s, 
                heure_debut = %s, 
                heure_fin = %s, 
                preparateurs = %s
            WHERE id = %s AND etiquette_id = %s
        """, (
            update_data['date_jour'],
            update_data['heure_debut'],
            update_data['heure_fin'],
            nouveaux_preparateurs,
            planification_id,
            etiquette_id
        ))
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Aucune planification mise à jour")
        
        # Mettre à jour le timestamp de l'étiquette
        cur.execute("""
            UPDATE etiquettes_grille 
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (etiquette_id,))
        
        conn.commit()
        
        return {
            "status": "✅ Planification spécifique mise à jour",
            "etiquette_id": etiquette_id,
            "planification_id": planification_id,
            "date_jour": update_data['date_jour'],
            "heure_debut": update_data['heure_debut'],
            "heure_fin": update_data['heure_fin'],
            "ancien_preparateurs": current_preparateurs,
            "nouveaux_preparateurs": nouveaux_preparateurs,
            "doublons_detectes": doublons_detectes,
            "doublons_supprimes": doublons_supprimes if doublons_detectes else 0,
            "preparateurs_avant_dedoublonnage": preparateurs_avant_dedoublonnage if doublons_detectes else None
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour de la planification: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.post("/etiquettes-grille/{etiquette_id}/planifications/{planification_id}/preparateurs")
def add_preparateur_to_planification(etiquette_id: int, planification_id: int, preparateur_data: Dict[str, Any]):
    """Ajouter un préparateur à une planification existante"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Vérifier que l'étiquette et la planification existent
        cur.execute("""
            SELECT p.id, p.preparateurs, e.type_activite, e.description
            FROM planifications_etiquettes p
            INNER JOIN etiquettes_grille e ON p.etiquette_id = e.id
            WHERE p.id = %s AND p.etiquette_id = %s
        """, (planification_id, etiquette_id))
        
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Planification non trouvée pour cette étiquette")
        
        planif_id, preparateurs_actuels, type_activite, description = result
        
        # Vérifier les champs requis
        if 'preparateur_nom' not in preparateur_data:
            raise HTTPException(status_code=400, detail="Champ requis manquant: preparateur_nom")
        
        nouveau_preparateur = preparateur_data['preparateur_nom'].strip()
        if not nouveau_preparateur:
            raise HTTPException(status_code=400, detail="Le nom du préparateur ne peut pas être vide")
        
        # Analyser la liste des préparateurs actuels
        preparateurs_list = [p.strip() for p in preparateurs_actuels.split(',') if p.strip()] if preparateurs_actuels else []
        
        print(f"🔧 Ajout préparateur à la planification {planification_id}:")
        print(f"   👤 Nouveau préparateur: '{nouveau_preparateur}'")
        print(f"   👥 Préparateurs actuels: {preparateurs_list}")
        
        # Vérifier si le préparateur est déjà dans la liste
        if nouveau_preparateur in preparateurs_list:
            raise HTTPException(
                status_code=409, 
                detail=f"Le préparateur '{nouveau_preparateur}' est déjà assigné à cette planification"
            )
        
        # Ajouter le nouveau préparateur à la liste
        preparateurs_list.append(nouveau_preparateur)
        nouveaux_preparateurs = ','.join(preparateurs_list)
        
        print(f"   👥 Nouveaux préparateurs: {nouveaux_preparateurs}")
        
        # Mettre à jour la planification avec le nouveau préparateur
        cur.execute("""
            UPDATE planifications_etiquettes 
            SET preparateurs = %s
            WHERE id = %s AND etiquette_id = %s
        """, (nouveaux_preparateurs, planification_id, etiquette_id))
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Aucune planification mise à jour")
        
        # Mettre à jour le timestamp de l'étiquette
        cur.execute("""
            UPDATE etiquettes_grille 
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (etiquette_id,))
        
        conn.commit()
        
        return {
            "status": "✅ Préparateur ajouté à la planification",
            "etiquette_id": etiquette_id,
            "planification_id": planification_id,
            "type_activite": type_activite,
            "description": description,
            "preparateur_ajoute": nouveau_preparateur,
            "anciens_preparateurs": preparateurs_actuels if preparateurs_actuels else "(aucun)",
            "nouveaux_preparateurs": nouveaux_preparateurs,
            "total_preparateurs": len(preparateurs_list)
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'ajout du préparateur: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.delete("/etiquettes-grille/{etiquette_id}")
def delete_etiquette_grille(etiquette_id: int):
    """Supprimer une étiquette de la grille semaine et toutes ses planifications"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Récupérer les informations avant suppression
        cur.execute("""
            SELECT e.type_activite, e.description, e.group_id, 
                   COUNT(p.id) as nb_planifications
            FROM etiquettes_grille e
            LEFT JOIN planifications_etiquettes p ON e.id = p.etiquette_id
            WHERE e.id = %s
            GROUP BY e.id, e.type_activite, e.description, e.group_id
        """, (etiquette_id,))
        
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Étiquette non trouvée")
        
        type_activite, description, group_id, nb_planifications = result
        
        # Supprimer l'étiquette (les planifications sont supprimées automatiquement via CASCADE)
        cur.execute("DELETE FROM etiquettes_grille WHERE id = %s", (etiquette_id,))
        conn.commit()
        
        return {
            "status": "✅ Étiquette supprimée",
            "etiquette_id": etiquette_id,
            "type_activite": type_activite,
            "description": description,
            "group_id": group_id,
            "planifications_supprimees": nb_planifications
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.delete("/etiquettes-grille/{etiquette_id}/planifications/{planification_id}")
def delete_planification_etiquette(etiquette_id: int, planification_id: int):
    """Supprimer une planification spécifique d'une étiquette sans supprimer l'étiquette entière"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Vérifier que l'étiquette et la planification existent
        cur.execute("""
            SELECT e.type_activite, e.description, e.group_id,
                   p.date_jour, p.heure_debut, p.heure_fin, p.preparateurs
            FROM etiquettes_grille e
            INNER JOIN planifications_etiquettes p ON e.id = p.etiquette_id
            WHERE e.id = %s AND p.id = %s
        """, (etiquette_id, planification_id))
        
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Étiquette ou planification non trouvée")
        
        type_activite, description, group_id, date_jour, heure_debut, heure_fin, preparateurs = result
        
        # Vérifier combien de planifications restent pour cette étiquette
        cur.execute("""
            SELECT COUNT(*) FROM planifications_etiquettes 
            WHERE etiquette_id = %s
        """, (etiquette_id,))
        
        nb_planifications_total = cur.fetchone()[0]
        
        # Si c'est la dernière planification, on peut soit interdire la suppression
        # soit supprimer toute l'étiquette (à décider selon vos besoins)
        if nb_planifications_total == 1:
            raise HTTPException(
                status_code=400, 
                detail="Impossible de supprimer la dernière planification d'une étiquette. Supprimez l'étiquette entière si nécessaire."
            )
        
        # Supprimer la planification spécifique
        cur.execute("""
            DELETE FROM planifications_etiquettes 
            WHERE id = %s AND etiquette_id = %s
        """, (planification_id, etiquette_id))
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Planification non trouvée")
        
        # Mettre à jour le timestamp de l'étiquette
        cur.execute("""
            UPDATE etiquettes_grille 
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (etiquette_id,))
        
        conn.commit()
        
        return {
            "status": "✅ Planification supprimée",
            "etiquette_id": etiquette_id,
            "planification_id": planification_id,
            "type_activite": type_activite,
            "description": description,
            "group_id": group_id,
            "planification_supprimee": {
                "date_jour": str(date_jour),
                "heure_debut": str(heure_debut),
                "heure_fin": str(heure_fin),
                "preparateurs": preparateurs
            },
            "planifications_restantes": nb_planifications_total - 1
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression de la planification: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.delete("/etiquettes-grille/{etiquette_id}/planifications/{planification_id}/preparateurs/{preparateur_nom}")
def remove_preparateur_from_planification(etiquette_id: int, planification_id: int, preparateur_nom: str):
    """Retirer un préparateur spécifique d'une planification sans affecter les autres préparateurs"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_grille_tables(conn)
        cur = conn.cursor()
        
        # Vérifier que l'étiquette et la planification existent
        cur.execute("""
            SELECT e.type_activite, e.description, e.group_id,
                   p.date_jour, p.heure_debut, p.heure_fin, p.preparateurs
            FROM etiquettes_grille e
            INNER JOIN planifications_etiquettes p ON e.id = p.etiquette_id
            WHERE e.id = %s AND p.id = %s
        """, (etiquette_id, planification_id))
        
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Étiquette ou planification non trouvée")
        
        type_activite, description, group_id, date_jour, heure_debut, heure_fin, preparateurs_actuels = result
        
        # Analyser la liste des préparateurs actuels
        preparateurs_list = [p.strip() for p in preparateurs_actuels.split(',') if p.strip()]
        preparateur_nom_clean = preparateur_nom.strip()
        
        # Vérifier que le préparateur est dans la liste
        if preparateur_nom_clean not in preparateurs_list:
            raise HTTPException(
                status_code=404, 
                detail=f"Le préparateur '{preparateur_nom_clean}' n'est pas assigné à cette planification"
            )
        
        # Si c'est le seul préparateur, ne rien faire
        if len(preparateurs_list) == 1:
            return {
                "status": "ℹ️ Aucune action effectuée",
                "message": f"Le préparateur '{preparateur_nom_clean}' est le seul assigné à cette planification",
                "etiquette_id": etiquette_id,
                "planification_id": planification_id,
                "preparateurs_avant": preparateurs_actuels,
                "preparateurs_apres": preparateurs_actuels,
                "preparateurs_restants": 1
            }
        
        # Retirer le préparateur de la liste
        preparateurs_list.remove(preparateur_nom_clean)
        nouveaux_preparateurs = ','.join(preparateurs_list)
        
        # Mettre à jour la planification
        cur.execute("""
            UPDATE planifications_etiquettes 
            SET preparateurs = %s
            WHERE id = %s AND etiquette_id = %s
        """, (nouveaux_preparateurs, planification_id, etiquette_id))
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Impossible de mettre à jour la planification")
        
        # Mettre à jour le timestamp de l'étiquette
        cur.execute("""
            UPDATE etiquettes_grille 
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (etiquette_id,))
        
        conn.commit()
        
        return {
            "status": "✅ Préparateur retiré de la planification",
            "etiquette_id": etiquette_id,
            "planification_id": planification_id,
            "type_activite": type_activite,
            "description": description,
            "group_id": group_id,
            "preparateur_retire": preparateur_nom_clean,
            "planification_info": {
                "date_jour": str(date_jour),
                "heure_debut": str(heure_debut),
                "heure_fin": str(heure_fin)
            },
            "preparateurs_avant": preparateurs_actuels,
            "preparateurs_apres": nouveaux_preparateurs,
            "preparateurs_restants": len(preparateurs_list)
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors du retrait du préparateur: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

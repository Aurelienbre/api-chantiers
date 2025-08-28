"""
Routes pour la gestion des templates de texte et du contenu textuel des étiquettes

Ce module contient toutes les routes relatives à :
- La gestion des templates de texte prédéfinis
- La gestion du contenu textuel des étiquettes
- L'intégration avec le système d'étiquettes existant
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Optional, Any, List
from datetime import datetime
from main import get_db_connection, close_db_connection
import psycopg2
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Créer le router pour les routes de texte d'étiquettes
router = APIRouter(
    prefix="",
    tags=["Templates et Texte Étiquettes"],
    responses={404: {"description": "Not found"}},
)

# REMPLACER la fonction ensure_texte_etiquettes_tables() par ces 2 fonctions séparées :

def ensure_text_templates_table(conn):
    """Créer UNIQUEMENT la table des templates (indépendante)"""
    try:
        cursor = conn.cursor()
        
        # UNIQUEMENT la table des templates
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS text_templates (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                content TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Template d'exemple UNIQUEMENT si la table vient d'être créée
        cursor.execute("SELECT COUNT(*) FROM text_templates WHERE name = %s", ('Réunion',))
        if cursor.fetchone()[0] == 0:
            template_content = """📝 Réunion – [Titre]
📅 Date : ____
👥 Participants : ____
________________________________________
✅ Ordre du jour
•	Point 1 : ____________________________
•	Point 2 : ____________________________
•	Point 3 : ____________________________
•	Divers
________________________________________
📌 Suivi des actions précédentes
•	Action A – Responsable : ____ – Échéance : ____
•	Action B – Responsable : ____ – Échéance : ____
•	Action C – Responsable : ____ – Échéance : ____
________________________________________
📖 Notes & Décisions
•	Décision 1 : ____________________________________
•	Décision 2 : ____________________________________
________________________________________
🛠️ Actions à venir
•	Tâche 1 – Responsable : ____ – Échéance : ____
•	Tâche 2 – Responsable : ____ – Échéance : ____
•	Tâche 3 – Responsable : ____ – Échéance : ____
________________________________________
📅 Prochaine réunion
•	Date : ____
•	Objectif : ____"""
            
            cursor.execute("""
                INSERT INTO text_templates (name, content, description) 
                VALUES (%s, %s, %s)
            """, ('Réunion', template_content, 'Template pour les réunions avec ordre du jour et suivi'))
        
        conn.commit()
        logger.info("Table text_templates créée/vérifiée")
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de la création de la table text_templates: {e}")
        conn.rollback()
        raise

def ensure_etiquettes_texte_column(conn):
    """Ajouter UNIQUEMENT la colonne texte aux étiquettes (indépendante)"""
    try:
        cursor = conn.cursor()
        
        # UNIQUEMENT vérifier/ajouter la colonne texte
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'etiquettes_grille' AND column_name = 'texte'
        """)
        
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE etiquettes_grille ADD COLUMN texte TEXT DEFAULT ''")
            conn.commit()
            logger.info("Colonne 'texte' ajoutée à la table etiquettes_grille")
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de l'ajout de la colonne texte: {e}")
        conn.rollback()
        raise

# ========================================================================
#  GESTION DES TEMPLATES DE TEXTE
# ========================================================================

@router.get("/text-templates")
def get_all_templates():
    """Récupérer tous les templates de texte disponibles"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, content, description, created_at, updated_at 
            FROM text_templates 
            ORDER BY name
        """)
        
        templates = []
        for row in cursor.fetchall():
            templates.append({
                'id': row[0],
                'name': row[1],
                'content': row[2],
                'description': row[3],
                'created_at': row[4].isoformat() if row[4] else None,
                'updated_at': row[5].isoformat() if row[5] else None
            })
        
        logger.info(f"Récupération de {len(templates)} templates")
        return {"success": True, "data": templates}
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de la récupération des templates: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

@router.get("/text-templates/{template_id}")
def get_template_by_id(template_id: int):
    """Récupérer un template spécifique par son ID"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, content, description, created_at, updated_at 
            FROM text_templates 
            WHERE id = %s
        """, (template_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Template non trouvé")
        
        template = {
            'id': row[0],
            'name': row[1],
            'content': row[2],
            'description': row[3],
            'created_at': row[4].isoformat() if row[4] else None,
            'updated_at': row[5].isoformat() if row[5] else None
        }
        
        logger.info(f"Template {template_id} récupéré")
        return {"success": True, "data": template}
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de la récupération du template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

@router.post("/text-templates")
def create_template(template_data: Dict[str, Any]):
    """Créer un nouveau template de texte"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    # Validation des données
    if not template_data.get('name') or not template_data.get('content'):
        raise HTTPException(status_code=400, detail="Le nom et le contenu sont obligatoires")
    
    try:
        
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO text_templates (name, content, description, updated_at) 
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id
        """, (
            template_data['name'],
            template_data['content'],
            template_data.get('description', '')
        ))
        
        template_id = cursor.fetchone()[0]
        conn.commit()
        
        logger.info(f"Template '{template_data['name']}' créé avec l'ID {template_id}")
        return {
            "success": True, 
            "message": "Template créé avec succès", 
            "id": template_id
        }
        
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Erreur lors de la création du template: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

@router.put("/text-templates/{template_id}")
def update_template(template_id: int, template_data: Dict[str, Any]):
    """Mettre à jour un template existant"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    # Validation des données
    if not template_data.get('name') or not template_data.get('content'):
        raise HTTPException(status_code=400, detail="Le nom et le contenu sont obligatoires")
    
    try:
       
        cursor = conn.cursor()
        
        # Vérifier que le template existe
        cursor.execute("SELECT id FROM text_templates WHERE id = %s", (template_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Template non trouvé")
        
        cursor.execute("""
            UPDATE text_templates 
            SET name = %s, content = %s, description = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            template_data['name'],
            template_data['content'],
            template_data.get('description', ''),
            template_id
        ))
        
        conn.commit()
        
        logger.info(f"Template {template_id} mis à jour")
        return {"success": True, "message": "Template mis à jour avec succès"}
        
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Erreur lors de la mise à jour du template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

@router.delete("/text-templates/{template_id}")
def delete_template(template_id: int):
    """Supprimer un template"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        
        cursor = conn.cursor()
        
        # Vérifier que le template existe
        cursor.execute("SELECT id FROM text_templates WHERE id = %s", (template_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Template non trouvé")
        
        cursor.execute("DELETE FROM text_templates WHERE id = %s", (template_id,))
        conn.commit()
        
        logger.info(f"Template {template_id} supprimé")
        return {"success": True, "message": "Template supprimé avec succès"}
        
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Erreur lors de la suppression du template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

# ========================================================================
#  GESTION DU TEXTE DES ÉTIQUETTES
# ========================================================================

@router.get("/etiquettes-grille/{etiquette_id}/texte")
def get_etiquette_texte(etiquette_id: int):
    """Récupérer le contenu textuel d'une étiquette de grille"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        
        cursor = conn.cursor()
        cursor.execute("SELECT texte FROM etiquettes_grille WHERE id = %s", (etiquette_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Étiquette non trouvée")
        
        logger.info(f"Texte de l'étiquette {etiquette_id} récupéré")
        return {"success": True, "data": {"texte": row[0] or ""}}
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de la récupération du texte de l'étiquette {etiquette_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

@router.put("/etiquettes-grille/{etiquette_id}/texte")
def update_etiquette_texte(etiquette_id: int, texte_data: Dict[str, Any]):
    """Mettre à jour le contenu textuel d'une étiquette de grille"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        
        cursor = conn.cursor()
        
        # Vérifier que l'étiquette existe
        cursor.execute("SELECT id FROM etiquettes_grille WHERE id = %s", (etiquette_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Étiquette non trouvée")
        
        cursor.execute("""
            UPDATE etiquettes_grille 
            SET texte = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (texte_data.get('texte', ''), etiquette_id))
        
        conn.commit()
        
        logger.info(f"Texte de l'étiquette {etiquette_id} mis à jour")
        return {"success": True, "message": "Texte de l'étiquette mis à jour avec succès"}
        
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Erreur lors de la mise à jour du texte de l'étiquette {etiquette_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

@router.post("/etiquettes-grille/{etiquette_id}/apply-template/{template_id}")
def apply_template_to_etiquette(etiquette_id: int, template_id: int):
    """Appliquer un template à une étiquette de grille (remplace le texte existant)"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        
        cursor = conn.cursor()
        
        # Vérifier que l'étiquette existe
        cursor.execute("SELECT id FROM etiquettes_grille WHERE id = %s", (etiquette_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Étiquette non trouvée")
        
        # Récupérer le contenu du template
        cursor.execute("SELECT content FROM text_templates WHERE id = %s", (template_id,))
        template_row = cursor.fetchone()
        if not template_row:
            raise HTTPException(status_code=404, detail="Template non trouvé")
        
        # Appliquer le template à l'étiquette
        cursor.execute("""
            UPDATE etiquettes_grille 
            SET texte = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (template_row[0], etiquette_id))
        
        conn.commit()
        
        logger.info(f"Template {template_id} appliqué à l'étiquette {etiquette_id}")
        return {
            "success": True, 
            "message": "Template appliqué avec succès à l'étiquette",
            "texte": template_row[0]
        }
        
    except psycopg2.Error as e:
        conn.rollback()
        logger.error(f"Erreur lors de l'application du template {template_id} à l'étiquette {etiquette_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

# ========================================================================
#  ENDPOINTS UTILITAIRES
# ========================================================================

@router.get("/etiquettes-grille-with-text")
def get_etiquettes_with_text():
    """Récupérer toutes les étiquettes de grille avec leur contenu textuel et planifications (OPTIMISÉ)"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        
        cursor = conn.cursor()
        # ✅ OPTIMISATION : Requête unique avec agrégation JSON (comme grille_semaine_routes.py)
        cursor.execute("""
            SELECT 
                e.id,
                e.type_activite,
                e.description,
                e.group_id,
                e.texte,
                e.created_at,
                e.updated_at,
                -- Agrégation optimisée des planifications
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', p.id,
                            'date_jour', p.date_jour::text,
                            'heure_debut', p.heure_debut::text,
                            'heure_fin', p.heure_fin::text,
                            'preparateurs', p.preparateurs
                        ) ORDER BY p.date_jour ASC, p.heure_debut ASC
                    ) FILTER (WHERE p.id IS NOT NULL),
                    '[]'::json
                ) as planifications_json
            FROM etiquettes_grille e
            LEFT JOIN planifications_etiquettes p ON e.id = p.etiquette_id
            GROUP BY e.id, e.type_activite, e.description, e.group_id, e.texte, e.created_at, e.updated_at
            ORDER BY e.created_at DESC
        """)
        
        etiquettes = []
        for row in cursor.fetchall():
            etiquettes.append({
                'id': row[0],
                'type_activite': row[1],
                'description': row[2],
                'group_id': row[3],
                'texte': row[4] or "",
                'created_at': row[5].isoformat() if row[5] else None,
                'updated_at': row[6].isoformat() if row[6] else None,
                'planifications': row[7]  # ← Déjà au format JSON !
            })
        
        logger.info(f"✅ Récupération optimisée de {len(etiquettes)} étiquettes avec texte")
        return {
            "success": True, 
            "count": len(etiquettes),
            "data": etiquettes
        }
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de la récupération des étiquettes avec texte: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

# ========================================================================
#  GESTION INDÉPENDANTE DES TEMPLATES (ADMIN)
# ========================================================================

@router.post("/admin/init-templates-table")
def init_templates_table():
    """ADMIN: Créer/initialiser UNIQUEMENT la table des templates"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        ensure_text_templates_table(conn)
        
        # Statistiques
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM text_templates")
        templates_count = cursor.fetchone()[0]
        
        return {
            "success": True,
            "message": "Table des templates initialisée avec succès",
            "scope": "🎯 Templates uniquement",
            "details": {
                "text_templates_table": "✅ Créée/Vérifiée",
                "templates_count": templates_count,
                "example_template": "Réunion" if templates_count > 0 else None
            }
        }
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de l'initialisation de la table templates: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

@router.get("/admin/templates-status")
def get_templates_status():
    """ADMIN: Vérifier UNIQUEMENT le statut des templates"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        cursor = conn.cursor()
        
        # Vérifier la table text_templates
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'text_templates'
        """)
        table_exists = bool(cursor.fetchone())
        
        templates_count = 0
        if table_exists:
            cursor.execute("SELECT COUNT(*) FROM text_templates")
            templates_count = cursor.fetchone()[0]
        
        return {
            "success": True,
            "scope": "🎯 Templates uniquement",
            "status": "✅ Templates prêts" if table_exists else "⚠️ Table templates manquante",
            "data": {
                "text_templates_table_exists": table_exists,
                "templates_count": templates_count
            },
            "next_steps": [
                "Utilisez POST /admin/init-templates-table pour créer la table"
            ] if not table_exists else [
                "✅ Templates opérationnels !",
                "Créez des templates via POST /text-templates"
            ]
        }
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de la vérification du statut templates: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

# ========================================================================
#  GESTION INDÉPENDANTE DU TEXTE D'ÉTIQUETTES (ADMIN)
# ========================================================================

@router.post("/admin/init-etiquettes-texte-column")
def init_etiquettes_texte_column():
    """ADMIN: Ajouter UNIQUEMENT la colonne texte aux étiquettes"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        ensure_etiquettes_texte_column(conn)
        
        # Statistiques
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM etiquettes_grille")
        etiquettes_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM etiquettes_grille WHERE texte IS NOT NULL AND texte != ''")
        etiquettes_with_text = cursor.fetchone()[0]
        
        return {
            "success": True,
            "message": "Colonne texte des étiquettes initialisée avec succès",
            "scope": "🎯 Texte d'étiquettes uniquement",
            "details": {
                "etiquettes_texte_column": "✅ Ajoutée/Vérifiée",
                "total_etiquettes": etiquettes_count,
                "etiquettes_with_text": etiquettes_with_text
            }
        }
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de l'initialisation de la colonne texte: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

@router.get("/admin/etiquettes-texte-status")
def get_etiquettes_texte_status():
    """ADMIN: Vérifier UNIQUEMENT le statut du texte des étiquettes"""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
    
    try:
        cursor = conn.cursor()
        
        # Vérifier la colonne texte dans etiquettes_grille
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'etiquettes_grille' AND column_name = 'texte'
        """)
        column_exists = bool(cursor.fetchone())
        
        etiquettes_count = 0
        etiquettes_with_text = 0
        
        if column_exists:
            cursor.execute("SELECT COUNT(*) FROM etiquettes_grille")
            etiquettes_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM etiquettes_grille WHERE texte IS NOT NULL AND texte != ''")
            etiquettes_with_text = cursor.fetchone()[0]
        
        return {
            "success": True,
            "scope": "🎯 Texte d'étiquettes uniquement",
            "status": "✅ Texte étiquettes prêt" if column_exists else "⚠️ Colonne texte manquante",
            "data": {
                "etiquettes_texte_column_exists": column_exists,
                "total_etiquettes": etiquettes_count,
                "etiquettes_with_text": etiquettes_with_text
            },
            "next_steps": [
                "Utilisez POST /admin/init-etiquettes-texte-column pour ajouter la colonne"
            ] if not column_exists else [
                "✅ Texte d'étiquettes opérationnel !",
                "Gérez le texte via PUT /etiquettes-grille/{id}/texte"
            ]
        }
        
    except psycopg2.Error as e:
        logger.error(f"Erreur lors de la vérification du statut texte étiquettes: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        close_db_connection(conn)

# Migration pour ajouter le support des verrous de planification forcée
import os
import json
from database_config import execute_query

def migrate_add_forced_planning_lock():
    """Ajoute le support des verrous de planification forcée"""
    
    try:
        print("🔒 Migration: Ajout du support des verrous de planification...")
        
        # 1. Ajouter la colonne forced_planning_lock à la table chantiers
        execute_query("""
            ALTER TABLE chantiers 
            ADD COLUMN IF NOT EXISTS forced_planning_lock JSONB DEFAULT NULL
        """)
        print("✅ Colonne forced_planning_lock ajoutée")
        
        # 2. Créer l'index pour améliorer les performances sur les requêtes JSON
        execute_query("""
            CREATE INDEX IF NOT EXISTS idx_chantiers_forced_planning_lock 
            ON chantiers USING GIN (forced_planning_lock)
        """)
        print("✅ Index GIN créé pour forced_planning_lock")
        
        print("✅ Migration réussie: Support des verrous de planification ajouté")
        
    except Exception as e:
        print(f"❌ Erreur lors de la migration: {e}")
        raise

if __name__ == "__main__":
    migrate_add_forced_planning_lock()

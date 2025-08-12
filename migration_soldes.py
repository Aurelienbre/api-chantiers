#!/usr/bin/env python3
"""
Migration pour créer la table des soldes de planification
Cette table stocke les soldes de temps de préparation par chantier et par semaine
"""

import os
import sys

def create_soldes_table():
    """Crée la table soldes avec les contraintes appropriées"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Création de la table soldes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS soldes (
                id SERIAL PRIMARY KEY,
                chantier_id VARCHAR(255) NOT NULL,
                semaine VARCHAR(20) NOT NULL,
                minutes INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                
                -- Contrainte d'unicité sur la combinaison chantier_id + semaine
                CONSTRAINT unique_solde_chantier_semaine UNIQUE (chantier_id, semaine),
                
                -- Contraintes de validation
                CONSTRAINT check_minutes_positive CHECK (minutes >= 0),
                CONSTRAINT check_semaine_format CHECK (semaine ~ '^[0-9]{4}-W[0-9]{2}-1$')
            )
        """)
        
        # Index pour améliorer les performances
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_soldes_chantier_id 
            ON soldes (chantier_id)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_soldes_semaine 
            ON soldes (semaine)
        """)
        
        # Trigger pour mettre à jour updated_at automatiquement
        cur.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql'
        """)
        
        cur.execute("""
            DROP TRIGGER IF EXISTS update_soldes_updated_at ON soldes
        """)
        
        cur.execute("""
            CREATE TRIGGER update_soldes_updated_at 
            BEFORE UPDATE ON soldes 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)
        
        conn.commit()
        
        print("✅ Table 'soldes' créée avec succès!")
        print("📊 Structure:")
        print("   - id: Clé primaire auto-incrémentée")
        print("   - chantier_id: ID du chantier (VARCHAR)")
        print("   - semaine: Semaine au format YYYY-WXX-1 (VARCHAR)")
        print("   - minutes: Nombre de minutes du solde (INTEGER)")
        print("   - created_at/updated_at: Timestamps automatiques")
        print("🔒 Contraintes:")
        print("   - Unicité sur (chantier_id, semaine)")
        print("   - Minutes >= 0")
        print("   - Format de semaine validé")
        print("🚀 Index créés pour optimiser les requêtes")
        
        # Vérifier la création
        cur.execute("""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'soldes'
            ORDER BY ordinal_position
        """)
        
        print("\n📋 Colonnes créées:")
        for row in cur.fetchall():
            table_name, column_name, data_type, is_nullable = row
            print(f"   - {column_name}: {data_type} ({'NULL' if is_nullable == 'YES' else 'NOT NULL'})")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la création de la table soldes: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if 'conn' in locals() and conn:
            try:
                conn.close()
            except:
                pass

def main():
    """Point d'entrée principal"""
    print("🏗️ Migration : Création de la table des soldes")
    print("=" * 50)
    
    if create_soldes_table():
        print("\n✅ Migration terminée avec succès!")
        print("💡 La table 'soldes' est maintenant prête à recevoir les données")
    else:
        print("\n❌ Échec de la migration")
        sys.exit(1)

if __name__ == "__main__":
    main()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional, Any
import os
import json


try:
    from beta_api_routes import router as beta_api_router
    BETA_API_AVAILABLE = True
except ImportError:
    beta_api_router = None
    BETA_API_AVAILABLE = False

try:
    from grille_semaine_routes import router as grille_semaine_router
    GRILLE_SEMAINE_AVAILABLE = True
except ImportError:
    grille_semaine_router = None
    GRILLE_SEMAINE_AVAILABLE = False


# Configuration de la base de données
def get_db_connection():
    """Établit une connexion à la base PostgreSQL"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL non définie")
    
    try:
        # Essayer psycopg3 d'abord
        import psycopg
        return psycopg.connect(database_url)
    except ImportError:
        try:
            # Fallback sur psycopg2
            import psycopg2
            return psycopg2.connect(database_url)
        except ImportError:
            raise Exception("Aucun module psycopg disponible")

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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_etiquettes_type_activite ON etiquettes_grille (type_activite)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_etiquettes_group_id ON etiquettes_grille (group_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planif_etiquettes_date ON planifications_etiquettes (date_jour)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planif_etiquettes_etiquette ON planifications_etiquettes (etiquette_id)")
    
    conn.commit()

def ensure_chantiers_tables(conn):
    """S'assurer que les tables pour les chantiers et préparateurs existent"""
    cur = conn.cursor()
    
    # Table des préparateurs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS preparateurs (
            nom VARCHAR(255) PRIMARY KEY,
            nni VARCHAR(50) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table des chantiers
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chantiers (
            id VARCHAR(255) PRIMARY KEY,
            label VARCHAR(500) NOT NULL,
            status VARCHAR(100) DEFAULT 'Nouveau',
            prepTime INTEGER DEFAULT 0,
            endDate VARCHAR(50),
            preparateur_nom VARCHAR(255) REFERENCES preparateurs(nom) ON UPDATE CASCADE ON DELETE SET NULL,
            ChargeRestante INTEGER DEFAULT 0,
            forced_planning_lock JSONB DEFAULT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table des planifications
    cur.execute("""
        CREATE TABLE IF NOT EXISTS planifications (
            id SERIAL PRIMARY KEY,
            chantier_id VARCHAR(255) NOT NULL REFERENCES chantiers(id) ON DELETE CASCADE,
            semaine VARCHAR(50) NOT NULL,
            minutes INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT unique_chantier_semaine UNIQUE (chantier_id, semaine)
        )
    """)
    
    # Table des soldes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS soldes (
            id SERIAL PRIMARY KEY,
            chantier_id VARCHAR(255) NOT NULL REFERENCES chantiers(id) ON DELETE CASCADE,
            semaine VARCHAR(50) NOT NULL,
            minutes INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT unique_solde_chantier_semaine UNIQUE (chantier_id, semaine)
        )
    """)
    
    # Table des disponibilités
    cur.execute("""
        CREATE TABLE IF NOT EXISTS disponibilites (
            id SERIAL PRIMARY KEY,
            preparateur_nom VARCHAR(255) NOT NULL REFERENCES preparateurs(nom) ON UPDATE CASCADE ON DELETE CASCADE,
            semaine VARCHAR(50) NOT NULL,
            minutes INTEGER NOT NULL DEFAULT 0,
            updatedAt VARCHAR(100) DEFAULT '',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT unique_dispo_preparateur_semaine UNIQUE (preparateur_nom, semaine)
        )
    """)
    
    # Table des horaires préparateurs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS horaires_preparateurs (
            id SERIAL PRIMARY KEY,
            preparateur_nom VARCHAR(255) NOT NULL REFERENCES preparateurs(nom) ON UPDATE CASCADE ON DELETE CASCADE,
            jour_semaine VARCHAR(20) NOT NULL,
            heure_debut TIME NOT NULL,
            heure_fin TIME NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT check_jour_semaine CHECK (jour_semaine IN ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')),
            CONSTRAINT check_heures_horaires CHECK (heure_debut < heure_fin)
        )
    """)
    
    # Index pour améliorer les performances
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chantiers_status ON chantiers (status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chantiers_preparateur ON chantiers (preparateur_nom)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chantiers_forced_planning_lock ON chantiers USING GIN (forced_planning_lock)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planifications_chantier ON planifications (chantier_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planifications_semaine ON planifications (semaine)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_soldes_chantier ON soldes (chantier_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_soldes_semaine ON soldes (semaine)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_disponibilites_preparateur ON disponibilites (preparateur_nom)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_disponibilites_semaine ON disponibilites (semaine)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_horaires_preparateur ON horaires_preparateurs (preparateur_nom)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_horaires_jour ON horaires_preparateurs (jour_semaine)")
    
    # Fonction pour mettre à jour updated_at automatiquement
    cur.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    # Triggers pour mettre à jour updated_at
    cur.execute("""
        DROP TRIGGER IF EXISTS update_preparateurs_updated_at ON preparateurs;
        CREATE TRIGGER update_preparateurs_updated_at 
            BEFORE UPDATE ON preparateurs 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    cur.execute("""
        DROP TRIGGER IF EXISTS update_chantiers_updated_at ON chantiers;
        CREATE TRIGGER update_chantiers_updated_at 
            BEFORE UPDATE ON chantiers 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    cur.execute("""
        DROP TRIGGER IF EXISTS update_horaires_updated_at ON horaires_preparateurs;
        CREATE TRIGGER update_horaires_updated_at 
            BEFORE UPDATE ON horaires_preparateurs 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)
    
    conn.commit()


app = FastAPI(
    title="API de Planification",
    description="API pour la gestion des chantiers et des étiquettes de planification",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclure les routers
if BETA_API_AVAILABLE and beta_api_router:
    app.include_router(beta_api_router, prefix="", tags=["Beta-API"])

if GRILLE_SEMAINE_AVAILABLE and grille_semaine_router:
    app.include_router(grille_semaine_router, prefix="", tags=["Grille Semaine"])

@app.get("/")
def read_root():
    """Point d'entrée de l'API"""
    return {
        "message": "API de Planification",
        "version": "2.0.0",
        "endpoints": {
            "beta_api": "Gestion des chantiers et préparateurs",
            "grille_semaine": "Gestion des étiquettes et horaires (à venir)"
        }
    }

@app.get("/health")
def health_check():
    """Vérification de santé de l'API"""
    return {"status": "healthy", "service": "planning-api"}



# ========================================================================
# ENDPOINTS DE NETTOYAGE COMPLET DE LA BASE DE DONNÉES
# ========================================================================

@app.delete("/admin/reset-database")
def reset_complete_database():
    """DANGER: Vider complètement toute la base de données - À utiliser avec précaution!"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Compter les enregistrements avant suppression
        tables_info = []
        
        # Liste des tables principales de l'application
        tables_to_check = [
            'chantiers', 'planifications', 'soldes', 'preparateurs', 
            'disponibilites', 'etiquettes_grille', 'planifications_etiquettes',
            'horaires_preparateurs', 'etiquettes_planification'
        ]
        
        # Compter les enregistrements dans chaque table
        for table_name in tables_to_check:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cur.fetchone()[0]
                if count > 0:
                    tables_info.append({"table": table_name, "records": count})
            except Exception:
                # Table n'existe pas, on continue
                pass
        
        total_records_before = sum(t["records"] for t in tables_info)
        
        if total_records_before == 0:
            return {
                "status": "ℹ️ Base de données déjà vide",
                "message": "Aucune donnée à supprimer",
                "tables_info": []
            }
        
        # Supprimer toutes les données dans l'ordre (contraintes de clés étrangères)
        deletion_summary = []
        
        # 1. Supprimer les tables de planifications en premier (dépendent des autres)
        for table in ['planifications', 'planifications_etiquettes', 'soldes', 'disponibilites']:
            try:
                cur.execute(f"DELETE FROM {table}")
                deleted = cur.rowcount
                if deleted > 0:
                    deletion_summary.append({"table": table, "deleted": deleted})
            except Exception as e:
                # Table n'existe peut-être pas
                pass
        
        # 2. Supprimer les tables principales
        for table in ['chantiers', 'etiquettes_grille', 'preparateurs', 'horaires_preparateurs']:
            try:
                cur.execute(f"DELETE FROM {table}")
                deleted = cur.rowcount
                if deleted > 0:
                    deletion_summary.append({"table": table, "deleted": deleted})
            except Exception as e:
                # Table n'existe peut-être pas
                pass
        
        # 3. Supprimer les anciennes tables si elles existent
        for table in ['etiquettes_planification']:
            try:
                cur.execute(f"DELETE FROM {table}")
                deleted = cur.rowcount
                if deleted > 0:
                    deletion_summary.append({"table": table, "deleted": deleted})
            except Exception as e:
                # Table n'existe peut-être pas
                pass
        
        # 4. Reset des séquences (pour repartir les IDs à 1)
        sequences_reset = []
        for table in ['chantiers', 'etiquettes_grille', 'preparateurs', 'planifications', 'planifications_etiquettes', 'soldes', 'disponibilites', 'horaires_preparateurs']:
            try:
                cur.execute(f"ALTER SEQUENCE {table}_id_seq RESTART WITH 1")
                sequences_reset.append(table)
            except Exception:
                # Séquence n'existe peut-être pas
                pass
        
        conn.commit()
        
        total_deleted = sum(d["deleted"] for d in deletion_summary)
        
        return {
            "status": "🗑️ Base de données vidée complètement",
            "summary": {
                "total_records_before": total_records_before,
                "total_deleted": total_deleted,
                "tables_processed": len(deletion_summary),
                "sequences_reset": len(sequences_reset)
            },
            "deletion_details": deletion_summary,
            "sequences_reset": sequences_reset,
            "message": "⚠️ TOUTES les données ont été supprimées définitivement !",
            "next_steps": [
                "Vous pouvez maintenant recréer vos données proprement",
                "Les IDs recommenceront à 1 pour toutes les tables",
                "Les structures de tables sont conservées"
            ]
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors du reset de la base: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.delete("/admin/drop-all-tables")
def drop_all_tables():
    """DANGER EXTRÊME: Supprimer complètement toutes les tables - Structure ET données!"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Lister toutes les tables de l'application
        cur.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename IN ('chantiers', 'planifications', 'soldes', 'preparateurs', 
                             'disponibilites', 'etiquettes_grille', 'planifications_etiquettes',
                             'horaires_preparateurs', 'etiquettes_planification')
        """)
        
        tables_found = [row[0] for row in cur.fetchall()]
        
        if not tables_found:
            return {
                "status": "ℹ️ Aucune table à supprimer",
                "message": "Les tables de l'application n'existent pas",
                "tables_found": []
            }
        
        # Supprimer toutes les tables (CASCADE pour gérer les contraintes)
        tables_dropped = []
        for table_name in tables_found:
            try:
                cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                tables_dropped.append(table_name)
            except Exception as e:
                print(f"Erreur suppression table {table_name}: {e}")
        
        conn.commit()
        
        return {
            "status": "💥 Tables supprimées complètement",
            "summary": {
                "tables_found": len(tables_found),
                "tables_dropped": len(tables_dropped)
            },
            "tables_dropped": tables_dropped,
            "message": "⚠️ STRUCTURE ET DONNÉES supprimées définitivement !",
            "warning": "Les tables devront être recréées lors de la prochaine utilisation de l'API",
            "next_steps": [
                "Redémarrez l'API pour recréer les tables automatiquement",
                "Ou utilisez les endpoints POST pour déclencher la création des tables"
            ]
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression des tables: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.post("/admin/create-all-tables")
def create_all_tables():
    """Créer toutes les tables de l'application"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        
        # Créer les tables des chantiers et préparateurs
        ensure_chantiers_tables(conn)
        
        # Créer les tables des étiquettes
        ensure_etiquettes_grille_tables(conn)
        
        # Vérifier que les tables ont bien été créées
        cur = conn.cursor()
        cur.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename IN ('preparateurs', 'chantiers', 'planifications', 'soldes', 
                             'disponibilites', 'horaires_preparateurs',
                             'etiquettes_grille', 'planifications_etiquettes')
            ORDER BY tablename
        """)
        
        tables_created = [row[0] for row in cur.fetchall()]
        
        return {
            "status": "✅ Toutes les tables créées avec succès",
            "tables_created": tables_created,
            "summary": {
                "chantiers_system": [
                    "preparateurs", "chantiers", "planifications", 
                    "soldes", "disponibilites", "horaires_preparateurs"
                ],
                "etiquettes_system": [
                    "etiquettes_grille", "planifications_etiquettes"
                ]
            },
            "message": "🎉 Votre base de données est prête à recevoir des données !",
            "next_steps": [
                "Utilisez Beta-API.html avec les routes /chantiers/*",
                "Utilisez Grille semaine.html avec les routes /etiquettes-grille/*",
                "Ajoutez vos préparateurs via POST /preparateurs",
                "Créez vos chantiers via POST /chantiers"
            ]
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur création des tables: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

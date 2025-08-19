from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional, Any
from datetime import datetime
import json
import os

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

def ensure_chantiers_planification_tables(conn):
    """Créer les nouvelles tables chantiers_planification et planifications"""
    cur = conn.cursor()
    
    # Table principale des chantiers
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chantiers_planification (
            id SERIAL PRIMARY KEY,
            type_activite VARCHAR(50) NOT NULL,
            description TEXT,
            group_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table des planifications (détails jour/heure/préparateurs)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS planifications (
            id SERIAL PRIMARY KEY,
            chantier_id INTEGER REFERENCES chantiers_planification(id) ON DELETE CASCADE,
            date_jour DATE NOT NULL,
            heure_debut INTEGER NOT NULL,
            heure_fin INTEGER NOT NULL,
            preparateurs TEXT[] NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Index pour optimiser les requêtes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planifications_chantier_id ON planifications(chantier_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planifications_date ON planifications(date_jour)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chantiers_group_id ON chantiers_planification(group_id)")
    
    conn.commit()

def ensure_etiquettes_table(conn):
    """Créer la table des étiquettes de planification (ancienne structure - Grille semaine)"""
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etiquettes_planification (
            id SERIAL PRIMARY KEY,
            preparateur VARCHAR(100) NOT NULL,
            date_jour DATE NOT NULL,
            heure_debut INTEGER NOT NULL,
            heure_fin INTEGER NOT NULL,
            type_activite VARCHAR(50) NOT NULL DEFAULT 'activite',
            description TEXT,
            group_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Index pour optimiser les requêtes
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_etiquettes_preparateur_date 
        ON etiquettes_planification (preparateur, date_jour)
    """)
    
    conn.commit()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "API Pilotage RIP fonctionne!", "status": "✅ Version avec séparation des systèmes Chantiers vs Étiquettes"}

@app.get("/debug/system-status")
def debug_system_status():
    """Diagnostic complet des deux systèmes : Chantiers de préparation vs Étiquettes"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        status = {
            "timestamp": datetime.now().isoformat(),
            "chantiers_preparation": {},
            "etiquettes_grille": {},
            "conflicts": [],
            "recommendations": []
        }
        
        # ===== DIAGNOSTIC SYSTÈME CHANTIERS DE PRÉPARATION (BETA-API) =====
        try:
            # Table chantiers (préparation)
            cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'chantiers')")
            chantiers_table_exists = cur.fetchone()[0]
            
            if chantiers_table_exists:
                cur.execute("SELECT COUNT(*) FROM chantiers")
                chantiers_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(DISTINCT status) FROM chantiers")
                statuses_count = cur.fetchone()[0]
            else:
                chantiers_count = 0
                statuses_count = 0
                
            status["chantiers_preparation"] = {
                "table_exists": chantiers_table_exists,
                "total_chantiers": chantiers_count,
                "distinct_statuses": statuses_count,
                "usage": "Beta-API.html - Gestion des chantiers RIP",
                "structure": "ID, label, status, prepTime, endDate, preparateur"
            }
            
        except Exception as e:
            status["chantiers_preparation"] = {"error": str(e)}
        
        # ===== DIAGNOSTIC SYSTÈME ÉTIQUETTES (GRILLE SEMAINE) =====
        etiquettes_count = 0
        chantiers_planif_count = 0
        planifications_count = 0
        
        try:
            # Table étiquettes_planification (ancienne structure)
            cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'etiquettes_planification')")
            etiquettes_table_exists = cur.fetchone()[0]
            
            if etiquettes_table_exists:
                cur.execute("SELECT COUNT(*) FROM etiquettes_planification")
                etiquettes_count = cur.fetchone()[0]
        except:
            etiquettes_table_exists = False
            
        try:
            # Tables chantiers_planification + planifications (nouvelle structure)
            cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'chantiers_planification')")
            chantiers_planif_table_exists = cur.fetchone()[0]
            
            cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'planifications')")
            planifications_table_exists = cur.fetchone()[0]
            
            if chantiers_planif_table_exists:
                cur.execute("SELECT COUNT(*) FROM chantiers_planification")
                chantiers_planif_count = cur.fetchone()[0]
                
            if planifications_table_exists:
                cur.execute("SELECT COUNT(*) FROM planifications")
                planifications_count = cur.fetchone()[0]
        except:
            chantiers_planif_table_exists = False
            planifications_table_exists = False
            
        status["etiquettes_grille"] = {
            "ancienne_structure": {
                "table_exists": etiquettes_table_exists,
                "total_etiquettes": etiquettes_count,
                "usage": "Grille semaine.html - Étiquettes visuelles"
            },
            "nouvelle_structure": {
                "chantiers_planification_exists": chantiers_planif_table_exists,
                "planifications_exists": planifications_table_exists,
                "total_chantiers": chantiers_planif_count,
                "total_planifications": planifications_count,
                "usage": "Grille semaine.html - Structure moderne"
            }
        }
        
        # ===== DÉTECTION DES CONFLITS =====
        if chantiers_table_exists and (etiquettes_table_exists or chantiers_planif_table_exists):
            status["conflicts"].append({
                "type": "endpoints_collision",
                "description": "Risque de collision sur l'endpoint /chantiers",
                "impact": "Les deux systèmes utilisent des endpoints similaires"
            })
            
        if etiquettes_table_exists and chantiers_planif_table_exists:
            status["conflicts"].append({
                "type": "double_structure",
                "description": "Deux structures d'étiquettes coexistent",
                "impact": "Confusion possible entre ancienne et nouvelle structure"
            })
            
        # ===== RECOMMANDATIONS =====
        if len(status["conflicts"]) == 0:
            status["recommendations"].append("✅ Aucun conflit détecté")
        else:
            status["recommendations"].extend([
                "🧹 Utilisez DELETE /etiquettes/cleanup pour supprimer toutes les tables d'étiquettes",
                "🗑️ Ou utilisez DELETE /etiquettes/data-only pour vider les données seulement",
                "🔄 Choisissez une seule structure : étiquettes OU chantiers_planification"
            ])
            
        return status
        
    except Exception as e:
        return {
            "status": "❌ Erreur lors du diagnostic",
            "error": str(e)
        }
    finally:
        if conn:
            conn.close()

@app.get("/test-database")
def test_database():
    """Test de connexion à la base PostgreSQL"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        return {
            "status": "❌ Échec",
            "error": "DATABASE_URL non définie",
            "solution": "Vérifiez la variable d'environnement sur Render"
        }
    
    try:
        # Test d'import psycopg3 (ou psycopg2 en fallback)
        try:
            import psycopg
            psycopg_status = f"✅ psycopg3 v{psycopg.__version__}"
            psycopg_module = psycopg
        except ImportError:
            import psycopg2
            psycopg_status = f"✅ psycopg2 v{psycopg2.__version__}"
            psycopg_module = psycopg2
    except ImportError as e:
        return {
            "status": "❌ Échec", 
            "error": f"Aucun module psycopg disponible: {e}",
            "database_url_present": True,
            "solution": "Installer psycopg[binary] ou psycopg2-binary"
        }
    
    try:
        # Test de connexion
        from urllib.parse import urlparse
        url = urlparse(database_url)
        
        # Adapter les paramètres selon la version psycopg
        if 'psycopg3' in psycopg_status:
            # psycopg3 utilise 'dbname' au lieu de 'database'
            conn = psycopg_module.connect(
                dbname=url.path[1:],
                user=url.username,
                password=url.password,
                host=url.hostname,
                port=url.port
            )
        else:
            # psycopg2 utilise 'database'
            conn = psycopg_module.connect(
                database=url.path[1:],
                user=url.username,
                password=url.password,
                host=url.hostname,
                port=url.port
            )
        
        # Test d'une requête simple
        cur = conn.cursor()
        cur.execute("SELECT version();")
        db_version = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
        table_count = cur.fetchone()[0]
        
        conn.close()
        
        return {
            "status": "✅ Succès complet !",
            "psycopg": psycopg_status,
            "database_url": "✅ Présente",
            "connection": "✅ Réussie",
            "database_version": db_version[:50] + "...",
            "tables_count": f"{table_count} tables publiques",
            "next_step": "Base prête pour la migration des données !"
        }
        
    except Exception as e:
        return {
            "status": "❌ Échec connexion",
            "psycopg": psycopg_status,
            "database_url": "✅ Présente", 
            "connection_error": str(e),
            "solution": "Vérifiez les paramètres de la base PostgreSQL"
        }

@app.get("/migrate-data")
def migrate_data():
    """Migration des données db.json vers PostgreSQL"""
    try:
        from database_config import get_database_connection
        import json
        
        # Vérifier si les tables existent déjà
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier si les données sont déjà migrées
        cur.execute("SELECT COUNT(*) FROM preparateurs")
        data_count = cur.fetchone()[0]
        
        if data_count > 0:
            conn.close()
            return {"status": "✅ Données déjà migrées", "message": f"{data_count} préparateurs trouvés"}
        
        # Créer les tables PostgreSQL si elles n'existent pas
        cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'preparateurs')")
        tables_exist = cur.fetchone()[0]
        
        if not tables_exist:
            cur.execute("""
            CREATE TABLE preparateurs (
                nom TEXT PRIMARY KEY,
                nni TEXT
            );

            CREATE TABLE disponibilites (
                id SERIAL PRIMARY KEY,
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
                forced_planning_lock JSONB DEFAULT NULL,
                FOREIGN KEY (preparateur_nom) REFERENCES preparateurs(nom)
            );

            CREATE TABLE planifications (
                id SERIAL PRIMARY KEY,
                chantier_id TEXT,
                semaine TEXT,
                minutes INTEGER,
                FOREIGN KEY (chantier_id) REFERENCES chantiers(id)
            );
            """)
            conn.commit()
        
        # Migration des verrous de planification forcée (pour les bases existantes)
        try:
            # Vérifier si la colonne forced_planning_lock existe déjà
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'chantiers' AND column_name = 'forced_planning_lock'
            """)
            column_exists = cur.fetchone()
            
            if not column_exists:
                # Ajouter la colonne forced_planning_lock aux bases existantes
                cur.execute("""
                    ALTER TABLE chantiers 
                    ADD COLUMN forced_planning_lock JSONB DEFAULT NULL
                """)
                
                # Créer l'index GIN pour améliorer les performances sur les requêtes JSON
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chantiers_forced_planning_lock 
                    ON chantiers USING GIN (forced_planning_lock)
                """)
                
                conn.commit()
                print("✅ Migration: Colonne forced_planning_lock ajoutée aux chantiers existants")
            
        except Exception as e:
            print(f"⚠️ Avertissement migration verrous: {e}")
            # Ne pas faire échouer toute la migration pour cette erreur
        
        # Charger et migrer les données db.json
        try:
            # Essayer plusieurs chemins possibles pour db.json
            json_paths = ['db.json', 'API/db.json', './db.json']
            data = None
            
            for path in json_paths:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        break
                except FileNotFoundError:
                    continue
            
            if data is None:
                raise FileNotFoundError("db.json non trouvé")
                
        except FileNotFoundError:
            # Si db.json n'existe pas, créer des données de test
            data = {
                "preparateurs": {
                    "Eric CHAPUIS": "F51742",
                    "Sylvain MATHAIS": "H13773"
                },
                "chantiers": {},
                "data": {}
            }
        
        # Insérer les préparateurs
        for nom, nni in data.get('preparateurs', {}).items():
            cur.execute("INSERT INTO preparateurs (nom, nni) VALUES (%s, %s) ON CONFLICT (nom) DO NOTHING", (nom, nni))
        
        # Insérer les chantiers
        for chantier_id, chantier in data.get('chantiers', {}).items():
            cur.execute("""
                INSERT INTO chantiers (id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante) 
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """, (
                chantier.get('id', chantier_id),
                chantier.get('label', ''),
                chantier.get('status', 'Nouveau'),
                chantier.get('prepTime', 0),
                chantier.get('endDate', ''),
                chantier.get('preparateur', ''),
                chantier.get('ChargeRestante', chantier.get('prepTime', 0))
            ))
            
            # Insérer les planifications du chantier
            for semaine, minutes in chantier.get('planification', {}).items():
                cur.execute("""
                    INSERT INTO planifications (chantier_id, semaine, minutes) 
                    VALUES (%s, %s, %s)
                """, (chantier['id'], semaine, minutes))
        
        # Insérer les disponibilités (data)
        for preparateur_nom, disponibilites in data.get('data', {}).items():
            for semaine, info in disponibilites.items():
                # Gérer les différents formats de données
                if isinstance(info, dict):
                    minutes = info.get('minutes', 0)
                    updated_at = info.get('updatedAt', '')
                else:
                    # Si c'est juste un nombre
                    minutes = info if isinstance(info, (int, float)) else 0
                    updated_at = ''
                
                cur.execute("""
                    INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt) 
                    VALUES (%s, %s, %s, %s)
                """, (preparateur_nom, semaine, minutes, updated_at))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "✅ Migration complète !",
            "message": "Tables créées et données migrées",
            "preparateurs": len(data.get('preparateurs', {})),
            "chantiers": len(data.get('chantiers', {})),
            "next_step": "API prête à fonctionner !"
        }
        
    except Exception as e:
        return {
            "status": "❌ Erreur", 
            "error": str(e),
            "error_type": type(e).__name__,
            "debug_info": "Erreur lors de la migration des données"
        }

@app.get("/migrate-forced-planning")
def migrate_forced_planning():
    """Migration spécifique pour ajouter le support des verrous de planification forcée"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier si la colonne forced_planning_lock existe déjà
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'chantiers' AND column_name = 'forced_planning_lock'
        """)
        column_exists = cur.fetchone()
        
        if column_exists:
            conn.close()
            return {
                "status": "✅ Migration déjà effectuée", 
                "message": "La colonne forced_planning_lock existe déjà"
            }
        
        # Ajouter la colonne forced_planning_lock aux bases existantes
        cur.execute("""
            ALTER TABLE chantiers 
            ADD COLUMN forced_planning_lock JSONB DEFAULT NULL
        """)
        
        # Créer l'index GIN pour améliorer les performances sur les requêtes JSON
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chantiers_forced_planning_lock 
            ON chantiers USING GIN (forced_planning_lock)
        """)
        
        conn.commit()
        conn.close()
        
        return {
            "status": "✅ Migration réussie !",
            "message": "Colonne forced_planning_lock ajoutée avec succès",
            "next_step": "Les verrous de planification forcée sont maintenant disponibles"
        }
        
    except Exception as e:
        return {
            "status": "❌ Erreur migration", 
            "error": str(e),
            "error_type": type(e).__name__,
            "debug_info": "Erreur lors de la migration des verrous"
        }

@app.get("/migrate-soldes")
def migrate_soldes():
    """Migration pour créer la table des soldes de planification"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier si la table soldes existe déjà
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'soldes'
        """)
        table_exists = cur.fetchone()
        
        if table_exists:
            return {
                "status": "✅ Migration déjà effectuée", 
                "message": "La table soldes existe déjà",
                "table_info": "Table prête à recevoir les données"
            }
        
        # Création de la table soldes
        cur.execute("""
            CREATE TABLE soldes (
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
            CREATE INDEX idx_soldes_chantier_id ON soldes (chantier_id)
        """)
        
        cur.execute("""
            CREATE INDEX idx_soldes_semaine ON soldes (semaine)
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
            CREATE TRIGGER update_soldes_updated_at 
            BEFORE UPDATE ON soldes 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)
        
        conn.commit()
        
        # Vérifier la création
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'soldes'
            ORDER BY ordinal_position
        """)
        
        columns = []
        for row in cur.fetchall():
            column_name, data_type, is_nullable = row
            columns.append(f"{column_name}: {data_type} ({'NULL' if is_nullable == 'YES' else 'NOT NULL'})")
        
        return {
            "status": "✅ Migration réussie !",
            "message": "Table soldes créée avec succès",
            "structure": {
                "columns": columns,
                "constraints": [
                    "Unicité sur (chantier_id, semaine)",
                    "Minutes >= 0", 
                    "Format de semaine validé (YYYY-WXX-1)"
                ],
                "indexes": ["idx_soldes_chantier_id", "idx_soldes_semaine"],
                "triggers": ["update_soldes_updated_at"]
            },
            "next_step": "La table soldes est maintenant prête à recevoir les données"
        }
        
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return {
            "status": "❌ Erreur migration", 
            "error": str(e),
            "error_type": type(e).__name__,
            "debug_info": "Erreur lors de la création de la table soldes"
        }
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.get("/chantiers")
def get_chantiers():
    """Récupérer tous les chantiers de préparation depuis PostgreSQL (Beta-API)"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier si la colonne forced_planning_lock existe
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'chantiers' AND column_name = 'forced_planning_lock'
        """)
        column_exists = cur.fetchone()
        
        if column_exists:
            # La colonne existe, requête complète avec soldes
            cur.execute("""
                SELECT c.id, c.label, c.status, c.prepTime, c.endDate, c.preparateur_nom, c.ChargeRestante,
                       c.forced_planning_lock, p.chantier_id, p.semaine, p.minutes,
                       s.semaine as solde_semaine, s.minutes as solde_minutes
                FROM chantiers c
                LEFT JOIN planifications p ON c.id = p.chantier_id
                LEFT JOIN soldes s ON c.id = s.chantier_id
                ORDER BY c.id, p.semaine, s.semaine
            """)
            
            rows = cur.fetchall()
            
            # Regrouper les résultats par chantier (avec verrous et soldes)
            chantiers = {}
            for row in rows:
                chantier_id = row[0]
                if chantier_id not in chantiers:
                    chantiers[chantier_id] = {
                        "id": row[0],
                        "label": row[1],
                        "status": row[2],
                        "prepTime": row[3],
                        "endDate": row[4],
                        "preparateur": row[5],
                        "ChargeRestante": row[6],
                        "forcedPlanningLock": row[7] or {},
                        "planification": {},
                        "soldes": {}
                    }
                
                # Ajouter la planification si elle existe
                if row[9] and row[10]:  # semaine et minutes de planification
                    chantiers[chantier_id]["planification"][row[9]] = row[10]
                
                # Ajouter le solde si il existe
                if row[11] and row[12]:  # semaine et minutes de solde
                    chantiers[chantier_id]["soldes"][row[11]] = row[12]
        else:
            # La colonne n'existe pas encore, requête sans forced_planning_lock mais avec soldes
            cur.execute("""
                SELECT c.id, c.label, c.status, c.prepTime, c.endDate, c.preparateur_nom, c.ChargeRestante,
                       p.chantier_id, p.semaine, p.minutes,
                       s.semaine as solde_semaine, s.minutes as solde_minutes
                FROM chantiers c
                LEFT JOIN planifications p ON c.id = p.chantier_id
                LEFT JOIN soldes s ON c.id = s.chantier_id
                ORDER BY c.id, p.semaine, s.semaine
            """)
            
            rows = cur.fetchall()
            
            # Regrouper les résultats par chantier (sans verrous mais avec soldes)
            chantiers = {}
            for row in rows:
                chantier_id = row[0]
                if chantier_id not in chantiers:
                    chantiers[chantier_id] = {
                        "id": row[0],
                        "label": row[1],
                        "status": row[2],
                        "prepTime": row[3],
                        "endDate": row[4],
                        "preparateur": row[5],
                        "ChargeRestante": row[6],
                        "forcedPlanningLock": {},  # Valeur par défaut
                        "planification": {},
                        "soldes": {}
                    }
                
                # Ajouter la planification si elle existe
                if row[8] and row[9]:  # semaine et minutes de planification (décalé car pas de forced_planning_lock)
                    chantiers[chantier_id]["planification"][row[8]] = row[9]
                
                # Ajouter le solde si il existe
                if row[10] and row[11]:  # semaine et minutes de solde
                    chantiers[chantier_id]["soldes"][row[10]] = row[11]
        
        return chantiers
        
    except Exception as e:
        print(f"🚨 Erreur GET /chantiers: {str(e)}")
        return {"error": f"Erreur base de données: {str(e)}"}
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.get("/preparateurs")
def get_preparateurs():
    """Récupérer tous les préparateurs depuis PostgreSQL"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT nom, nni FROM preparateurs ORDER BY nom")
        rows = cur.fetchall()
        conn.close()
        
        # Convertir en dictionnaire nom -> nni
        preparateurs = {row[0]: row[1] for row in rows}
        
        return preparateurs
        
    except Exception as e:
        return {"error": f"Erreur base de données: {str(e)}"}

@app.post("/preparateurs")
def sync_preparateurs(preparateurs_data: Dict[str, Any]):
    """Synchroniser les préparateurs avec PostgreSQL"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        preparateurs = preparateurs_data.get('preparateurs', {})
        synced_count = 0
        
        # Insérer ou mettre à jour chaque préparateur
        for nom, nni in preparateurs.items():
            cur.execute("""
                INSERT INTO preparateurs (nom, nni) 
                VALUES (%s, %s) 
                ON CONFLICT (nom) DO UPDATE SET nni = EXCLUDED.nni
            """, (nom, nni))
            synced_count += 1
        
        conn.commit()
        conn.close()
        
        return {"status": "✅ Préparateurs synchronisés", "count": synced_count}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.delete("/preparateurs/{nom}")
def delete_preparateur(nom: str):
    """Supprimer un préparateur de PostgreSQL"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Supprimer d'abord les disponibilités liées à ce préparateur
        cur.execute("DELETE FROM disponibilites WHERE preparateur_nom = %s", (nom,))
        disponibilites_deleted = cur.rowcount
        
        # Supprimer le préparateur
        cur.execute("DELETE FROM preparateurs WHERE nom = %s", (nom,))
        preparateur_deleted = cur.rowcount
        
        # Mettre les chantiers assignés à ce préparateur comme non-assignés
        cur.execute("UPDATE chantiers SET preparateur_nom = NULL WHERE preparateur_nom = %s", (nom,))
        chantiers_updated = cur.rowcount
        
        conn.commit()
        conn.close()
        
        if preparateur_deleted > 0:
            return {
                "status": "✅ Préparateur supprimé", 
                "nom": nom,
                "disponibilites_supprimees": disponibilites_deleted,
                "chantiers_mis_a_jour": chantiers_updated
            }
        else:
            return {"status": "⚠️ Préparateur non trouvé", "nom": nom}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.put("/preparateurs/{ancien_nom}")
def update_preparateur(ancien_nom: str, preparateur_data: Dict[str, Any]):
    """Modifier un préparateur (nom et/ou NNI) avec mise à jour en cascade"""
    try:
        from database_config import get_database_connection
        
        nouveau_nom = preparateur_data.get('nom', ancien_nom)
        nouveau_nni = preparateur_data.get('nni')
        
        if not nouveau_nni:
            raise HTTPException(status_code=400, detail="NNI requis")
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier que l'ancien préparateur existe
        cur.execute("SELECT nom FROM preparateurs WHERE nom = %s", (ancien_nom,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Préparateur '{ancien_nom}' non trouvé")
        
        # Si le nom change, vérifier que le nouveau nom n'existe pas déjà
        if ancien_nom != nouveau_nom:
            cur.execute("SELECT nom FROM preparateurs WHERE nom = %s", (nouveau_nom,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail=f"Le préparateur '{nouveau_nom}' existe déjà")
        
        # ⚠️ Pour contourner les contraintes de clé étrangère, on doit d'abord 
        # créer le nouveau préparateur, puis supprimer l'ancien
        
        if ancien_nom != nouveau_nom:
            # 1. Créer le nouveau préparateur
            cur.execute("INSERT INTO preparateurs (nom, nni) VALUES (%s, %s)", (nouveau_nom, nouveau_nni))
            
            # 2. Mettre à jour les chantiers pour pointer vers le nouveau préparateur
            cur.execute("UPDATE chantiers SET preparateur_nom = %s WHERE preparateur_nom = %s", (nouveau_nom, ancien_nom))
            chantiers_updated = cur.rowcount
            
            # 3. Mettre à jour les disponibilités pour pointer vers le nouveau préparateur
            cur.execute("UPDATE disponibilites SET preparateur_nom = %s WHERE preparateur_nom = %s", (nouveau_nom, ancien_nom))
            disponibilites_updated = cur.rowcount
            
            # 4. Supprimer l'ancien préparateur (maintenant plus référencé)
            cur.execute("DELETE FROM preparateurs WHERE nom = %s", (ancien_nom,))
            preparateur_updated = cur.rowcount
        else:
            # Si seul le NNI change, mise à jour simple
            cur.execute("UPDATE preparateurs SET nni = %s WHERE nom = %s", (nouveau_nni, ancien_nom))
            preparateur_updated = cur.rowcount
            chantiers_updated = 0
            disponibilites_updated = 0
        
        conn.commit()
        conn.close()
        
        return {
            "status": "✅ Préparateur modifié avec succès",
            "ancien_nom": ancien_nom,
            "nouveau_nom": nouveau_nom,
            "nouveau_nni": nouveau_nni,
            "chantiers_mis_a_jour": chantiers_updated,
            "disponibilites_mises_a_jour": disponibilites_updated
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.get("/disponibilites")
def get_disponibilites():
    """Récupérer toutes les disponibilités depuis PostgreSQL"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT preparateur_nom, semaine, minutes, updatedAt 
            FROM disponibilites 
            ORDER BY preparateur_nom, semaine
        """)
        
        rows = cur.fetchall()
        conn.close()
        
        # Regrouper par préparateur
        disponibilites = {}
        for row in rows:
            preparateur = row[0]
            if preparateur not in disponibilites:
                disponibilites[preparateur] = {}
            
            disponibilites[preparateur][row[1]] = {
                "minutes": row[2],
                "updatedAt": row[3]
            }
        
        return {"data": disponibilites}
        
    except Exception as e:
        return {"error": f"Erreur base de données: {str(e)}"}

# ========================================================================
# 🏗️ ENDPOINTS CRUD POUR CHANTIERS DE PRÉPARATION (BETA-API.html)
# ========================================================================
# Ces endpoints gèrent les chantiers classiques de préparation avec :
# - Structure : ID, label, status, prepTime, endDate, preparateur, ChargeRestante
# - Table principale : `chantiers`
# - Tables liées : `planifications` (semaine/minutes), `soldes`
# - Usage : Interface Beta-API.html pour la gestion des chantiers RIP

@app.post("/chantiers")
def create_chantier(chantier: Dict[str, Any]):
    """Créer un nouveau chantier de préparation dans PostgreSQL (Beta-API)"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Insérer le chantier
        cur.execute("""
            INSERT INTO chantiers (id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                label = EXCLUDED.label,
                status = EXCLUDED.status,
                prepTime = EXCLUDED.prepTime,
                endDate = EXCLUDED.endDate,
                preparateur_nom = EXCLUDED.preparateur_nom,
                ChargeRestante = EXCLUDED.ChargeRestante
        """, (
            chantier.get('id'),
            chantier.get('label'),
            chantier.get('status'),
            chantier.get('prepTime'),
            chantier.get('endDate'),
            chantier.get('preparateur'),
            chantier.get('ChargeRestante', chantier.get('prepTime'))
        ))
        
        conn.commit()
        conn.close()
        
        return {"status": "✅ Chantier créé/mis à jour", "id": chantier.get('id')}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.put("/chantiers/{chantier_id}")
def update_chantier(chantier_id: str, chantier: Dict[str, Any]):
    """Mettre à jour un chantier de préparation existant (Beta-API)"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Construire la requête dynamiquement selon les champs fournis
        updates = []
        params = []
        
        if 'label' in chantier and chantier['label'] is not None:
            updates.append("label = %s")
            params.append(chantier['label'])
        if 'status' in chantier and chantier['status'] is not None:
            updates.append("status = %s")
            params.append(chantier['status'])
        if 'prepTime' in chantier and chantier['prepTime'] is not None:
            updates.append("prepTime = %s")
            params.append(chantier['prepTime'])
        if 'endDate' in chantier and chantier['endDate'] is not None:
            updates.append("endDate = %s")
            params.append(chantier['endDate'])
        if 'preparateur' in chantier and chantier['preparateur'] is not None:
            updates.append("preparateur_nom = %s")
            params.append(chantier['preparateur'])
        if 'ChargeRestante' in chantier and chantier['ChargeRestante'] is not None:
            updates.append("ChargeRestante = %s")
            params.append(chantier['ChargeRestante'])
        
        if not updates:
            return {"status": "⚠️ Aucune modification fournie"}
        
        params.append(chantier_id)
        query = f"UPDATE chantiers SET {', '.join(updates)} WHERE id = %s"
        
        cur.execute(query, params)
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        conn.commit()
        conn.close()
        
        return {"status": "✅ Chantier mis à jour", "id": chantier_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.put("/planification")
def update_planification(planif: Dict[str, Any]):
    """Mettre à jour la planification d'un chantier de préparation avec préservation intelligente de l'historique (Beta-API)"""
    try:
        from database_config import get_database_connection
        from datetime import datetime, timedelta
        import re
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        chantier_id = planif.get('chantier_id')
        planifications = planif.get('planifications', {})
        preserve_past = planif.get('preserve_past', True)  # Par défaut, préserver l'historique
        
        if preserve_past:
            # 🛡️ MODE INTELLIGENT : Préserver les semaines passées
            
            # Calculer la semaine courante (format: "2025-W33-1")
            now = datetime.utcnow()
            if now.weekday() == 6:  # Si dimanche, reculer d'un jour
                now = now - timedelta(days=1)
            
            # Calculer le numéro de semaine ISO
            year, week_num, _ = now.isocalendar()
            current_week_key = f"{year}-W{week_num:02d}-1"
            
            print(f"🔍 Mode préservation activé - Semaine courante: {current_week_key}")
            
            # Supprimer SEULEMENT les planifications >= semaine courante
            cur.execute("""
                DELETE FROM planifications 
                WHERE chantier_id = %s 
                AND semaine >= %s
            """, (chantier_id, current_week_key))
            
            deleted_count = cur.rowcount
            print(f"📅 Planifications supprimées (>= {current_week_key}): {deleted_count}")
            
        else:
            # 🗑️ MODE LEGACY : Supprimer tout (rétrocompatibilité)
            cur.execute("DELETE FROM planifications WHERE chantier_id = %s", (chantier_id,))
            deleted_count = cur.rowcount
            print(f"🧹 Mode legacy - Toutes planifications supprimées: {deleted_count}")
        
        # Insérer les nouvelles planifications
        inserted_count = 0
        for semaine, minutes in planifications.items():
            if minutes > 0:  # Ne stocker que les planifications non nulles
                cur.execute("""
                    INSERT INTO planifications (chantier_id, semaine, minutes) 
                    VALUES (%s, %s, %s)
                """, (chantier_id, semaine, minutes))
                inserted_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            "status": "✅ Planification mise à jour avec préservation intelligente",
            "chantier_id": chantier_id,
            "mode": "preservation" if preserve_past else "legacy",
            "current_week": current_week_key if preserve_past else None,
            "deleted_future": deleted_count,
            "inserted_new": inserted_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.put("/disponibilites")
def update_disponibilites(dispo: Dict[str, Any]):
    """Mettre à jour les disponibilités d'un préparateur"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        preparateur_nom = dispo.get('preparateur_nom')
        disponibilites = dispo.get('disponibilites', {})
        
        # Supprimer les anciennes disponibilités pour ce préparateur
        cur.execute("DELETE FROM disponibilites WHERE preparateur_nom = %s", (preparateur_nom,))
        
        # Insérer les nouvelles disponibilités
        for semaine, info in disponibilites.items():
            minutes = info.get('minutes', 0) if isinstance(info, dict) else info
            updated_at = info.get('updatedAt', '') if isinstance(info, dict) else ''
            
            if minutes > 0:  # Ne stocker que les disponibilités non nulles
                cur.execute("""
                    INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt) 
                    VALUES (%s, %s, %s, %s)
                """, (preparateur_nom, semaine, minutes, updated_at))
        
        conn.commit()
        conn.close()
        
        return {"status": "✅ Disponibilités mises à jour", "preparateur": preparateur_nom}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.put("/sync-planning")
def sync_complete_planning(data: Dict[str, Any]):
    """Synchronisation complète de la planification après répartition automatique (Beta-API)"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Mettre à jour tous les chantiers
        if 'chantiers' in data:
            for chantier_id, chantier_data in data['chantiers'].items():
                # Mettre à jour le chantier principal
                cur.execute("""
                    UPDATE chantiers SET 
                        label = %s, status = %s, prepTime = %s, 
                        endDate = %s, preparateur_nom = %s, ChargeRestante = %s
                    WHERE id = %s
                """, (
                    chantier_data.get('label', ''),
                    chantier_data.get('status', 'Nouveau'),
                    chantier_data.get('prepTime', 0),
                    chantier_data.get('endDate', ''),
                    chantier_data.get('preparateur'),
                    chantier_data.get('ChargeRestante', chantier_data.get('prepTime', 0)),
                    chantier_id
                ))
                
                # Supprimer l'ancienne planification
                cur.execute("DELETE FROM planifications WHERE chantier_id = %s", (chantier_id,))
                
                # Insérer la nouvelle planification
                planification = chantier_data.get('planification', {})
                for semaine, minutes in planification.items():
                    if minutes > 0:
                        cur.execute("""
                            INSERT INTO planifications (chantier_id, semaine, minutes) 
                            VALUES (%s, %s, %s)
                        """, (chantier_id, semaine, minutes))
        
        # Mettre à jour les disponibilités
        if 'data' in data:
            for preparateur_nom, disponibilites in data['data'].items():
                # Supprimer les anciennes disponibilités
                cur.execute("DELETE FROM disponibilites WHERE preparateur_nom = %s", (preparateur_nom,))
                
                # Insérer les nouvelles disponibilités
                for semaine, info in disponibilites.items():
                    minutes = info.get('minutes', 0) if isinstance(info, dict) else info
                    updated_at = info.get('updatedAt', '') if isinstance(info, dict) else ''
                    
                    if minutes > 0:
                        cur.execute("""
                            INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt) 
                            VALUES (%s, %s, %s, %s)
                        """, (preparateur_nom, semaine, minutes, updated_at))
        
        conn.commit()
        conn.close()
        
        return {"status": "✅ Planification complète synchronisée"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

# ===== ENDPOINTS POUR VERROUS DE PLANIFICATION FORCÉE =====

@app.get("/chantiers/{chantier_id}/forced-planning-lock")
def get_forced_planning_lock(chantier_id: str):
    """Récupérer les verrous de planification forcée d'un chantier"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT forced_planning_lock FROM chantiers WHERE id = %s", (chantier_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        return {"chantier_id": chantier_id, "forced_planning_lock": row[0] or {}}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.put("/chantiers/{chantier_id}/forced-planning-lock")
def update_forced_planning_lock(chantier_id: str, lock_data: Dict[str, Any]):
    """Mettre à jour les verrous de planification forcée d'un chantier"""
    try:
        from database_config import get_database_connection
        import json
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Valider et normaliser les données de verrous
        forced_planning_lock = lock_data.get('forced_planning_lock', {})
        
        # Convertir en JSON pour PostgreSQL
        lock_json = json.dumps(forced_planning_lock) if forced_planning_lock else None
        
        # Mettre à jour le chantier avec les nouveaux verrous
        cur.execute("""
            UPDATE chantiers 
            SET forced_planning_lock = %s 
            WHERE id = %s
        """, (lock_json, chantier_id))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "✅ Verrous de planification mis à jour",
            "chantier_id": chantier_id,
            "forced_planning_lock": forced_planning_lock
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.delete("/chantiers/{chantier_id}/forced-planning-lock")
def clear_forced_planning_lock(chantier_id: str):
    """Supprimer tous les verrous de planification forcée d'un chantier"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Supprimer tous les verrous
        cur.execute("""
            UPDATE chantiers 
            SET forced_planning_lock = NULL 
            WHERE id = %s
        """, (chantier_id,))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "✅ Verrous de planification supprimés",
            "chantier_id": chantier_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.put("/forced-planning-lock")
def sync_forced_planning_lock_put(lock_data: Dict[str, Any]):
    """Synchroniser les verrous de planification forcée depuis le client (méthode PUT)"""
    try:
        from database_config import get_database_connection
        import json
        
        chantier_id = lock_data.get('chantier_id')
        forced_planning_lock = lock_data.get('forced_planning_lock', {})
        
        if not chantier_id:
            raise HTTPException(status_code=400, detail="chantier_id requis")
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Convertir en JSON pour PostgreSQL
        lock_json = json.dumps(forced_planning_lock) if forced_planning_lock else None
        
        # Mettre à jour les verrous
        cur.execute("""
            UPDATE chantiers 
            SET forced_planning_lock = %s 
            WHERE id = %s
        """, (lock_json, chantier_id))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "✅ Verrous synchronisés",
            "chantier_id": chantier_id,
            "locked_segments": len(forced_planning_lock)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")

@app.post("/forced-planning-lock")
def sync_forced_planning_lock(lock_data: Dict[str, Any]):
    """Synchroniser les verrous de planification forcée depuis le client (méthode POST)"""
    conn = None
    try:
        from database_config import get_database_connection
        import json
        
        chantier_id = lock_data.get('chantier_id')
        forced_planning_lock = lock_data.get('forced_planning_lock', {})
        
        if not chantier_id:
            raise HTTPException(status_code=400, detail="chantier_id requis")
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Migration automatique : Vérifier si la colonne forced_planning_lock existe
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'chantiers' AND column_name = 'forced_planning_lock'
        """)
        column_exists = cur.fetchone()
        
        if not column_exists:
            print("🔧 Migration automatique: Ajout de la colonne forced_planning_lock")
            # Ajouter la colonne forced_planning_lock si elle n'existe pas
            cur.execute("""
                ALTER TABLE chantiers 
                ADD COLUMN forced_planning_lock JSONB DEFAULT NULL
            """)
            
            # Créer l'index GIN pour améliorer les performances
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chantiers_forced_planning_lock 
                ON chantiers USING GIN (forced_planning_lock)
            """)
            
            conn.commit()
            print("✅ Migration automatique réussie")
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Convertir en JSON pour PostgreSQL
        lock_json = json.dumps(forced_planning_lock) if forced_planning_lock else None
        
        # Mettre à jour les verrous
        cur.execute("""
            UPDATE chantiers 
            SET forced_planning_lock = %s 
            WHERE id = %s
        """, (lock_json, chantier_id))
        
        conn.commit()
        
        print(f"✅ Verrous synchronisés pour {chantier_id}: {len(forced_planning_lock)} segments")
        
        return {
            "status": "✅ Verrous de planification forcée synchronisés",
            "chantier_id": chantier_id,
            "forced_planning_lock": forced_planning_lock
        }
        
    except Exception as e:
        print(f"🚨 Erreur POST /forced-planning-lock: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.get("/debug-locks")
def debug_forced_planning_locks():
    """DEBUG: Voir tous les verrous de planification forcée"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Récupérer tous les chantiers avec leurs verrous
        cur.execute("""
            SELECT id, label, forced_planning_lock 
            FROM chantiers 
            WHERE forced_planning_lock IS NOT NULL 
            AND forced_planning_lock != 'null'
            AND forced_planning_lock != '{}'
        """)
        
        rows = cur.fetchall()
        
        locks_info = []
        for row in rows:
            locks_info.append({
                "chantier_id": row[0],
                "label": row[1],
                "forced_planning_lock": row[2]
            })
        
        return {
            "status": "✅ Debug verrous",
            "total_locks": len(locks_info),
            "locks": locks_info
        }
        
    except Exception as e:
        print(f"🚨 Erreur DEBUG locks: {str(e)}")
        return {"error": f"Erreur: {str(e)}"}
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.post("/clear-all-locks")
def clear_all_forced_planning_locks():
    """URGENCE: Supprimer TOUS les verrous de planification forcée"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Supprimer TOUS les verrous
        cur.execute("""
            UPDATE chantiers 
            SET forced_planning_lock = NULL
        """)
        
        cleared_count = cur.rowcount
        conn.commit()
        
        print(f"🧹 NETTOYAGE D'URGENCE: {cleared_count} verrous supprimés")
        
        return {
            "status": "🧹 TOUS les verrous supprimés",
            "cleared_count": cleared_count,
            "message": "Base nettoyée, testez maintenant vos fonctions"
        }
        
    except Exception as e:
        print(f"🚨 Erreur CLEAR ALL locks: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

# ===== ENDPOINTS CRUD POUR SOLDES =====

@app.get("/soldes/{chantier_id}")
def get_soldes(chantier_id: str):
    """Récupérer tous les soldes d'un chantier"""
    conn = None
    try:
        from database_config import get_database_connection
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT semaine, minutes
            FROM soldes
            WHERE chantier_id = %s
            ORDER BY semaine
        """, (chantier_id,))
        
        soldes = {}
        for row in cur.fetchall():
            semaine, minutes = row
            soldes[semaine] = minutes
        
        return {
            "chantier_id": chantier_id,
            "soldes": soldes,
            "status": "success"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des soldes: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.put("/soldes")
def update_soldes(solde_data: Dict[str, Any]):
    """Mettre à jour les soldes d'un chantier"""
    conn = None
    try:
        from database_config import get_database_connection
        conn = get_database_connection()
        cur = conn.cursor()
        
        chantier_id = solde_data.get('chantier_id')
        soldes = solde_data.get('soldes', {})
        
        if not chantier_id:
            raise HTTPException(status_code=400, detail="chantier_id requis")
        
        # Supprimer les anciens soldes pour ce chantier
        cur.execute("DELETE FROM soldes WHERE chantier_id = %s", (chantier_id,))
        
        # Insérer les nouveaux soldes
        for semaine, minutes in soldes.items():
            if minutes > 0:  # Ne stocker que les soldes positifs
                cur.execute("""
                    INSERT INTO soldes (chantier_id, semaine, minutes)
                    VALUES (%s, %s, %s)
                """, (chantier_id, semaine, minutes))
        
        conn.commit()
        
        return {
            "chantier_id": chantier_id,
            "soldes_count": len([m for m in soldes.values() if m > 0]),
            "status": "success"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour des soldes: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.post("/soldes")
def create_or_update_solde(solde_data: Dict[str, Any]):
    """Créer ou mettre à jour un solde spécifique"""
    conn = None
    try:
        from database_config import get_database_connection
        conn = get_database_connection()
        cur = conn.cursor()
        
        chantier_id = solde_data.get('chantier_id')
        semaine = solde_data.get('semaine')
        minutes = solde_data.get('minutes', 0)
        
        if not chantier_id or not semaine:
            raise HTTPException(status_code=400, detail="chantier_id et semaine requis")
        
        if minutes <= 0:
            # Si minutes <= 0, supprimer le solde
            cur.execute("""
                DELETE FROM soldes 
                WHERE chantier_id = %s AND semaine = %s
            """, (chantier_id, semaine))
        else:
            # Sinon, insérer ou mettre à jour
            cur.execute("""
                INSERT INTO soldes (chantier_id, semaine, minutes)
                VALUES (%s, %s, %s)
                ON CONFLICT (chantier_id, semaine) 
                DO UPDATE SET minutes = %s
            """, (chantier_id, semaine, minutes, minutes))
        
        conn.commit()
        
        return {
            "chantier_id": chantier_id,
            "semaine": semaine,
            "minutes": minutes,
            "status": "success"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création/mise à jour du solde: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.delete("/soldes/{chantier_id}")
def delete_all_soldes(chantier_id: str):
    """Supprimer tous les soldes d'un chantier"""
    conn = None
    try:
        from database_config import get_database_connection
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("DELETE FROM soldes WHERE chantier_id = %s", (chantier_id,))
        deleted_count = cur.rowcount
        
        conn.commit()
        
        return {
            "chantier_id": chantier_id,
            "deleted_count": deleted_count,
            "status": "success"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression des soldes: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.delete("/soldes/{chantier_id}/{semaine}")
def delete_solde(chantier_id: str, semaine: str):
    """Supprimer un solde spécifique"""
    conn = None
    try:
        from database_config import get_database_connection
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("""
            DELETE FROM soldes 
            WHERE chantier_id = %s AND semaine = %s
        """, (chantier_id, semaine))
        
        deleted_count = cur.rowcount
        conn.commit()
        
        return {
            "chantier_id": chantier_id,
            "semaine": semaine,
            "deleted": deleted_count > 0,
            "status": "success"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression du solde: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.delete("/chantiers/{chantier_id}")
def delete_chantier(chantier_id: str):
    """Supprimer un chantier de préparation spécifique et toutes ses données associées (Beta-API)"""
    conn = None
    try:
        from database_config import get_database_connection
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier si le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        chantier = cur.fetchone()
        
        if not chantier:
            raise HTTPException(status_code=404, detail=f"Chantier {chantier_id} non trouvé")
        
        # Supprimer toutes les données associées au chantier
        # 1. Supprimer les soldes
        cur.execute("DELETE FROM soldes WHERE chantier_id = %s", (chantier_id,))
        soldes_deleted = cur.rowcount
        
        # 2. Supprimer les planifications
        cur.execute("DELETE FROM planifications WHERE chantier_id = %s", (chantier_id,))
        planifications_deleted = cur.rowcount
        
        # 3. Supprimer le chantier
        cur.execute("DELETE FROM chantiers WHERE id = %s", (chantier_id,))
        chantier_deleted = cur.rowcount
        
        conn.commit()
        
        return {
            "chantier_id": chantier_id,
            "deleted": True,
            "planifications_deleted": planifications_deleted,
            "soldes_deleted": soldes_deleted,
            "status": "success",
            "message": f"Chantier {chantier_id} supprimé avec {planifications_deleted} planifications et {soldes_deleted} soldes associés"
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression du chantier: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.delete("/chantiers")
def delete_all_chantiers():
    """Supprimer tous les chantiers de préparation et toutes leurs données associées (Beta-API)"""
    conn = None
    try:
        from database_config import get_database_connection
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Compter les éléments avant suppression
        cur.execute("SELECT COUNT(*) FROM chantiers")
        chantiers_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM soldes")
        soldes_count = cur.fetchone()[0]
        
        if chantiers_count == 0:
            return {
                "deleted": False,
                "message": "Aucun chantier à supprimer",
                "status": "success"
            }
        
        # Supprimer toutes les données
        # 1. Supprimer tous les soldes
        cur.execute("DELETE FROM soldes")
        soldes_deleted = cur.rowcount
        
        # 2. Supprimer toutes les planifications
        cur.execute("DELETE FROM planifications")
        planifications_deleted = cur.rowcount
        
        # 3. Supprimer tous les chantiers
        cur.execute("DELETE FROM chantiers")
        chantiers_deleted = cur.rowcount
        
        conn.commit()
        
        return {
            "deleted": True,
            "chantiers_deleted": chantiers_deleted,
            "planifications_deleted": planifications_deleted,
            "soldes_deleted": soldes_deleted,
            "status": "success",
            "message": f"Tous les chantiers supprimés ({chantiers_deleted} chantiers, {planifications_deleted} planifications et {soldes_deleted} soldes)"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression de tous les chantiers: {str(e)}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

# ===== ENDPOINTS POUR LES HORAIRES DES PRÉPARATEURS =====

@app.get("/horaires")
def get_all_horaires():
    """Récupérer tous les horaires de tous les préparateurs"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
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
            conn.close()

@app.get("/horaires/{preparateur_nom}")
def get_horaires_preparateur(preparateur_nom: str):
    """Récupérer les horaires d'un préparateur spécifique"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
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
            conn.close()

@app.put("/horaires/{preparateur_nom}")
def update_horaires_preparateur(preparateur_nom: str, horaires_data: Dict[str, Any]):
    """Mettre à jour les horaires d'un préparateur"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
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
            conn.close()

@app.post("/horaires")
def sync_all_horaires(horaires_data: Dict[str, Any]):
    """Synchroniser tous les horaires des préparateurs"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
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
            conn.close()

@app.delete("/horaires/{preparateur_nom}")
def delete_horaires_preparateur(preparateur_nom: str):
    """Supprimer tous les horaires d'un préparateur"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
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
            conn.close()

# ========================================================================
# 🏷️ ENDPOINTS POUR LES ÉTIQUETTES DE PLANIFICATION (GRILLE SEMAINE)
# ========================================================================
# Ces endpoints gèrent les étiquettes visuelles de la grille semaine avec :
# - Structure : type_activite, description, date_jour, heure_debut/fin, preparateurs[]
# - Tables : `etiquettes_planification` OU nouvelles tables `chantiers_planification` + `planifications`
# - Usage : Interface Grille semaine.html pour les étiquettes visuelles

# ===== ENDPOINTS POUR LES ÉTIQUETTES DE PLANIFICATION =====

@app.post("/cleanup/remove-old-structure")
def remove_old_etiquettes_structure():
    """Supprimer l'ancienne structure etiquettes_planification"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier si l'ancienne table existe
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'etiquettes_planification'
            )
        """)
        old_table_exists = cur.fetchone()[0]
        
        if old_table_exists:
            # Compter les enregistrements avant suppression
            cur.execute("SELECT COUNT(*) FROM etiquettes_planification")
            records_count = cur.fetchone()[0]
            
            # Supprimer la table
            cur.execute("DROP TABLE IF EXISTS etiquettes_planification CASCADE")
            conn.commit()
            
            return {
                "status": "✅ Ancienne structure supprimée",
                "table_removed": "etiquettes_planification",
                "records_deleted": records_count,
                "message": "Vous pouvez maintenant utiliser uniquement la nouvelle structure chantiers-planification"
            }
        else:
            return {
                "status": "ℹ️ Ancienne table déjà absente",
                "message": "La table etiquettes_planification n'existait pas"
            }
            
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "status": "❌ Erreur suppression",
            "error": str(e)
        }
    finally:
        if conn:
            conn.close()

@app.post("/cleanup/fresh-start")
def fresh_start():
    """Nettoyage complet - Supprimer ancienne structure et créer la nouvelle"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Supprimer l'ancienne table si elle existe
        cur.execute("DROP TABLE IF EXISTS etiquettes_planification CASCADE")
        
        # Supprimer les nouvelles tables si elles existent (pour un restart propre)
        cur.execute("DROP TABLE IF EXISTS planifications CASCADE")
        cur.execute("DROP TABLE IF EXISTS chantiers_planification CASCADE")
        
        # Créer la nouvelle structure
        ensure_chantiers_planification_tables(conn)
        
        return {
            "status": "✅ Redémarrage propre terminé",
            "actions": [
                "Ancienne table etiquettes_planification supprimée",
                "Nouvelles tables chantiers_planification et planifications créées",
                "Prêt pour créer des données avec POST /chantiers-planification"
            ],
            "next_step": "Testez avec POST /chantiers-planification"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "status": "❌ Erreur redémarrage",
            "error": str(e)
        }
    finally:
        if conn:
            conn.close()

@app.post("/chantiers/init")
def initialize_chantiers_tables():
    """Initialiser les nouvelles tables chantiers_planification et planifications"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_chantiers_planification_tables(conn)
        return {
            "status": "✅ Nouvelles tables initialisées",
            "tables": ["chantiers_planification", "planifications"],
            "message": "Prêt pour la migration des données"
        }
    except Exception as e:
        return {
            "status": "❌ Erreur initialisation",
            "error": str(e)
        }
    finally:
        if conn:
            conn.close()

@app.get("/debug/nouvelles-tables")
def debug_nouvelles_tables():
    """Vérifier la structure des nouvelles tables chantiers_planification et planifications"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        result = {}
        
        # Vérifier chantiers_planification
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'chantiers_planification'
            )
        """)
        
        if cur.fetchone()[0]:
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'chantiers_planification'
                ORDER BY ordinal_position
            """)
            result["chantiers_planification"] = {
                "exists": True,
                "columns": [{"name": col[0], "type": col[1], "nullable": col[2]} for col in cur.fetchall()]
            }
        else:
            result["chantiers_planification"] = {"exists": False}
        
        # Vérifier planifications
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'planifications'
            )
        """)
        
        if cur.fetchone()[0]:
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'planifications'
                ORDER BY ordinal_position
            """)
            result["planifications"] = {
                "exists": True,
                "columns": [{"name": col[0], "type": col[1], "nullable": col[2]} for col in cur.fetchall()]
            }
        else:
            result["planifications"] = {"exists": False}
        
        return {
            "status": "✅ Vérification terminée",
            "tables": result
        }
        
    except Exception as e:
        return {
            "status": "❌ Erreur vérification",
            "error": str(e)
        }
    finally:
        if conn:
            conn.close()

@app.get("/debug/etiquettes-structure")
def debug_etiquettes_structure():
    """Vérifier la structure de la table etiquettes_planification"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier si la table existe
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'etiquettes_planification'
            )
        """)
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            return {
                "status": "❌ Table etiquettes_planification n'existe pas",
                "solution": "Utilisez POST /etiquettes/init pour la créer"
            }
        
        # Récupérer la structure des colonnes
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'etiquettes_planification'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        
        # Récupérer quelques exemples de données
        cur.execute("SELECT * FROM etiquettes_planification LIMIT 3")
        sample_data = cur.fetchall()
        
        # Compter les enregistrements
        cur.execute("SELECT COUNT(*) FROM etiquettes_planification")
        total_count = cur.fetchone()[0]
        
        return {
            "status": "✅ Structure analysée",
            "table_exists": table_exists,
            "total_records": total_count,
            "columns": [{"name": col[0], "type": col[1], "nullable": col[2]} for col in columns],
            "sample_data": sample_data[:2] if sample_data else [],
            "column_names": [col[0] for col in columns]
        }
        
    except Exception as e:
        return {
            "status": "❌ Erreur analyse",
            "error": str(e)
        }
    finally:
        if conn:
            conn.close()

@app.post("/etiquettes/init")
def init_etiquettes_table():
    """Initialiser la table des étiquettes de planification (Grille semaine - ancienne structure)"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_table(conn)
        
        # Vérifier que la table a été créée
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'etiquettes_planification'
        """)
        table_exists = cur.fetchone()[0] > 0
        
        return {
            "status": "✅ Table étiquettes initialisée",
            "table_exists": table_exists,
            "message": "La table etiquettes_planification est prête à être utilisée"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'initialisation: {str(e)}")
    finally:
        if conn:
            conn.close()

@app.delete("/etiquettes/cleanup")
def cleanup_etiquettes_tables():
    """SUPPRESSION COMPLÈTE : Supprimer toutes les tables d'étiquettes et leurs données (Grille semaine)"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Compter les données avant suppression
        try:
            cur.execute("SELECT COUNT(*) FROM etiquettes_planification")
            etiquettes_count = cur.fetchone()[0]
        except:
            etiquettes_count = 0
            
        try:
            cur.execute("SELECT COUNT(*) FROM chantiers_planification")
            chantiers_planif_count = cur.fetchone()[0]
        except:
            chantiers_planif_count = 0
            
        try:
            cur.execute("SELECT COUNT(*) FROM planifications WHERE chantier_id IN (SELECT id FROM chantiers_planification)")
            planifs_count = cur.fetchone()[0]
        except:
            planifs_count = 0
        
        # Supprimer les tables d'étiquettes (ordre important pour les contraintes)
        cur.execute("DROP TABLE IF EXISTS planifications CASCADE")
        cur.execute("DROP TABLE IF EXISTS chantiers_planification CASCADE") 
        cur.execute("DROP TABLE IF EXISTS etiquettes_planification CASCADE")
        
        conn.commit()
        
        return {
            "status": "🧹 Nettoyage complet terminé",
            "tables_supprimees": [
                "etiquettes_planification",
                "chantiers_planification", 
                "planifications"
            ],
            "donnees_supprimees": {
                "etiquettes": etiquettes_count,
                "chantiers_planification": chantiers_planif_count,
                "planifications": planifs_count
            },
            "message": "Toutes les données d'étiquettes ont été supprimées. Les chantiers de préparation (Beta-API) sont conservés.",
            "next_step": "Vous pouvez maintenant choisir quelle structure utiliser : étiquettes ou chantiers_planification"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "status": "❌ Erreur lors du nettoyage",
            "error": str(e),
            "message": "Certaines tables n'ont peut-être pas pu être supprimées"
        }
    finally:
        if conn:
            conn.close()

@app.delete("/etiquettes/data-only")
def cleanup_etiquettes_data_only():
    """SUPPRESSION DONNÉES SEULEMENT : Vider les tables d'étiquettes mais conserver la structure (Grille semaine)"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Compter les données avant suppression
        try:
            cur.execute("SELECT COUNT(*) FROM etiquettes_planification")
            etiquettes_count = cur.fetchone()[0]
        except:
            etiquettes_count = 0
            
        try:
            cur.execute("SELECT COUNT(*) FROM planifications WHERE chantier_id IN (SELECT id FROM chantiers_planification)")
            planifs_count = cur.fetchone()[0]
        except:
            planifs_count = 0
            
        try:
            cur.execute("SELECT COUNT(*) FROM chantiers_planification")
            chantiers_planif_count = cur.fetchone()[0]
        except:
            chantiers_planif_count = 0
        
        # Vider les données (ordre important pour les contraintes)
        cur.execute("DELETE FROM planifications WHERE chantier_id IN (SELECT id FROM chantiers_planification)")
        cur.execute("DELETE FROM chantiers_planification")
        cur.execute("DELETE FROM etiquettes_planification")
        
        # Reset des séquences auto-increment
        cur.execute("ALTER SEQUENCE etiquettes_planification_id_seq RESTART WITH 1")
        cur.execute("ALTER SEQUENCE chantiers_planification_id_seq RESTART WITH 1")  
        cur.execute("ALTER SEQUENCE planifications_id_seq RESTART WITH 1")
        
        conn.commit()
        
        return {
            "status": "🗑️ Données supprimées",
            "tables_videes": [
                "etiquettes_planification",
                "chantiers_planification",
                "planifications"
            ],
            "donnees_supprimees": {
                "etiquettes": etiquettes_count,
                "chantiers_planification": chantiers_planif_count,
                "planifications": planifs_count
            },
            "message": "Toutes les données d'étiquettes ont été supprimées. La structure des tables est conservée.",
            "next_step": "Les tables sont prêtes à recevoir de nouvelles données"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "status": "❌ Erreur lors de la suppression",
            "error": str(e),
            "message": "Certaines données n'ont peut-être pas pu être supprimées"
        }
    finally:
        if conn:
            conn.close()

# ========================================================================
# 🏗️ GESTION DES CHANTIERS DE PLANIFICATION (NOUVELLE STRUCTURE - GRILLE SEMAINE)
# ========================================================================
# Ces endpoints gèrent la nouvelle structure pour remplacer les étiquettes :
# - Tables : `chantiers_planification` (master) + `planifications` (détails)
# - Usage : Alternative moderne aux étiquettes pour Grille semaine.html
# - Avantage : Structure plus cohérente et possibilité de grouper les planifications

@app.get("/chantiers-planification")
def get_all_chantiers_planification():
    """Récupérer tous les chantiers de planification avec leurs planifications (Grille semaine - nouvelle structure)"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_chantiers_planification_tables(conn)
        cur = conn.cursor()
        
        # Récupérer tous les chantiers avec leurs planifications
        cur.execute("""
            SELECT 
                c.id, c.type_activite, c.description, c.group_id, 
                c.created_at, c.updated_at,
                p.id as planif_id, p.date_jour, p.heure_debut, p.heure_fin, p.preparateurs
            FROM chantiers_planification c
            LEFT JOIN planifications p ON c.id = p.chantier_id
            ORDER BY c.created_at DESC, p.date_jour ASC, p.heure_debut ASC
        """)
        
        results = cur.fetchall()
        
        # Grouper les résultats par chantier
        chantiers = {}
        for row in results:
            chantier_id = row[0]
            
            if chantier_id not in chantiers:
                chantiers[chantier_id] = {
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
                chantiers[chantier_id]["planifications"].append({
                    "id": row[6],
                    "date_jour": row[7].strftime('%Y-%m-%d'),
                    "heure_debut": row[8],
                    "heure_fin": row[9],
                    "preparateurs": row[10]
                })
        
        chantiers_list = list(chantiers.values())
        
        return {
            "status": "✅ Chantiers récupérés",
            "count": len(chantiers_list),
            "chantiers": chantiers_list
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")
    finally:
        if conn:
            conn.close()

@app.post("/chantiers-planification")
def create_chantier_planification(chantier_data: Dict[str, Any]):
    """Créer un nouveau chantier de planification avec ses planifications (Grille semaine - nouvelle structure)"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_chantiers_planification_tables(conn)
        cur = conn.cursor()
        
        # Valider les données requises
        required_fields = ['type_activite', 'planifications']
        for field in required_fields:
            if field not in chantier_data:
                raise HTTPException(status_code=400, detail=f"Champ requis manquant: {field}")
        
        if not chantier_data['planifications']:
            raise HTTPException(status_code=400, detail="Au moins une planification est requise")
        
        # Créer le chantier principal
        cur.execute("""
            INSERT INTO chantiers_planification (type_activite, description, group_id)
            VALUES (%s, %s, %s)
            RETURNING id, created_at, updated_at
        """, (
            chantier_data['type_activite'],
            chantier_data.get('description'),
            chantier_data.get('group_id')
        ))
        
        chantier_result = cur.fetchone()
        chantier_id = chantier_result[0]
        
        # Créer les planifications
        planifications_creees = []
        for planif in chantier_data['planifications']:
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
                INSERT INTO planifications (chantier_id, date_jour, heure_debut, heure_fin, preparateurs)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, created_at
            """, (
                chantier_id,
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
            "status": "✅ Chantier créé",
            "chantier": {
                "id": chantier_id,
                "type_activite": chantier_data['type_activite'],
                "description": chantier_data.get('description'),
                "group_id": chantier_data.get('group_id'),
                "created_at": chantier_result[1].isoformat(),
                "updated_at": chantier_result[2].isoformat(),
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
            conn.close()

@app.post("/migrate-to-chantiers")
def migrate_etiquettes_to_chantiers():
    """Migrer les données des étiquettes vers la nouvelle structure chantiers"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_etiquettes_table(conn)
        ensure_chantiers_planification_tables(conn)
        cur = conn.cursor()
        
        # D'abord, vérifier combien d'étiquettes nous avons
        cur.execute("SELECT COUNT(*) FROM etiquettes_planification")
        total_etiquettes = cur.fetchone()[0]
        
        if total_etiquettes == 0:
            return {
                "status": "⚠️ Aucune donnée à migrer",
                "message": "La table etiquettes_planification est vide"
            }
        
        chantiers_crees = []
        
        # Étape 1: Migrer les étiquettes avec group_id (groupées)
        cur.execute("""
            SELECT DISTINCT group_id, type_activite, description
            FROM etiquettes_planification 
            WHERE group_id IS NOT NULL
            ORDER BY group_id
        """)
        
        groups_distincts = cur.fetchall()
        print(f"Groups distincts trouvés: {len(groups_distincts)}")
        
        for group_id, type_activite, description in groups_distincts:
            # Créer le chantier pour ce groupe
            cur.execute("""
                INSERT INTO chantiers_planification (type_activite, description, group_id)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (type_activite, description, group_id))
            
            chantier_id = cur.fetchone()[0]
            
            # Récupérer toutes les étiquettes de ce groupe
            cur.execute("""
                SELECT preparateur, date_jour, heure_debut, heure_fin
                FROM etiquettes_planification 
                WHERE group_id = %s
                ORDER BY date_jour, heure_debut
            """, (group_id,))
            
            etiquettes_du_groupe = cur.fetchall()
            
            # Grouper par date/heure pour regrouper les préparateurs
            planifications_map = {}
            for preparateur, date_jour, heure_debut, heure_fin in etiquettes_du_groupe:
                date_str = date_jour.strftime('%Y-%m-%d')
                key = f"{date_str}_{heure_debut}_{heure_fin}"
                
                if key not in planifications_map:
                    planifications_map[key] = {
                        'date_jour': date_str,
                        'heure_debut': heure_debut,
                        'heure_fin': heure_fin,
                        'preparateurs': []
                    }
                planifications_map[key]['preparateurs'].append(preparateur)
            
            # Créer les planifications regroupées
            planifications_creees = 0
            for planif_data in planifications_map.values():
                cur.execute("""
                    INSERT INTO planifications (chantier_id, date_jour, heure_debut, heure_fin, preparateurs)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    chantier_id,
                    planif_data['date_jour'],
                    planif_data['heure_debut'],
                    planif_data['heure_fin'],
                    planif_data['preparateurs']
                ))
                planifications_creees += 1
            
            chantiers_crees.append({
                "chantier_id": chantier_id,
                "type_activite": type_activite,
                "description": description,
                "group_id": group_id,
                "etiquettes_source": len(etiquettes_du_groupe),
                "planifications_creees": planifications_creees
            })
        
        # Étape 2: Migrer les étiquettes individuelles (sans group_id)
        cur.execute("""
            SELECT id, preparateur, date_jour, heure_debut, heure_fin, type_activite, description
            FROM etiquettes_planification 
            WHERE group_id IS NULL
            ORDER BY id
        """)
        
        etiquettes_individuelles = cur.fetchall()
        
        for etiquette_id, preparateur, date_jour, heure_debut, heure_fin, type_activite, description in etiquettes_individuelles:
            # Créer un chantier individuel
            cur.execute("""
                INSERT INTO chantiers_planification (type_activite, description, group_id)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (type_activite, description, etiquette_id))  # Utiliser l'ancien ID comme group_id
            
            chantier_id = cur.fetchone()[0]
            
            # Créer la planification unique
            cur.execute("""
                INSERT INTO planifications (chantier_id, date_jour, heure_debut, heure_fin, preparateurs)
                VALUES (%s, %s, %s, %s, %s)
            """, (chantier_id, date_jour, heure_debut, heure_fin, [preparateur]))
            
            chantiers_crees.append({
                "chantier_id": chantier_id,
                "type_activite": type_activite,
                "description": description,
                "group_id": f"individual_{etiquette_id}",
                "etiquettes_source": 1,
                "planifications_creees": 1
            })
        
        conn.commit()
        
        return {
            "status": "✅ Migration terminée",
            "summary": {
                "total_etiquettes_source": total_etiquettes,
                "groups_distincts": len(groups_distincts),
                "etiquettes_individuelles": len(etiquettes_individuelles),
                "chantiers_crees": len(chantiers_crees),
                "total_planifications": sum(c["planifications_creees"] for c in chantiers_crees)
            },
            "chantiers": chantiers_crees[:3],  # Afficher les 3 premiers
            "message": "Migration réussie ! Testez avec GET /chantiers-planification"
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "status": "❌ Erreur migration",
            "error": str(e),
            "debug": "Vérifiez les logs pour plus de détails"
        }
    finally:
        if conn:
            conn.close()

@app.put("/chantiers-planification/{chantier_id}")
def update_chantier_planification(chantier_id: int, chantier_data: Dict[str, Any]):
    """Mettre à jour un chantier de planification"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_chantiers_planification_tables(conn)
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers_planification WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Mettre à jour les informations du chantier
        update_fields = []
        update_values = []
        
        for field in ['type_activite', 'description', 'group_id']:
            if field in chantier_data:
                update_fields.append(f"{field} = %s")
                update_values.append(chantier_data[field])
        
        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            update_values.append(chantier_id)
            
            query = f"""
                UPDATE chantiers_planification 
                SET {', '.join(update_fields)}
                WHERE id = %s
            """
            cur.execute(query, update_values)
        
        # Mettre à jour les planifications si fournies
        if 'planifications' in chantier_data:
            # Supprimer les anciennes planifications
            cur.execute("DELETE FROM planifications WHERE chantier_id = %s", (chantier_id,))
            
            # Créer les nouvelles planifications
            for planif in chantier_data['planifications']:
                cur.execute("""
                    INSERT INTO planifications (chantier_id, date_jour, heure_debut, heure_fin, preparateurs)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    chantier_id,
                    planif['date_jour'],
                    planif['heure_debut'],
                    planif['heure_fin'],
                    planif['preparateurs']
                ))
        
        conn.commit()
        
        # Récupérer le chantier mis à jour
        cur.execute("""
            SELECT c.id, c.type_activite, c.description, c.group_id, c.updated_at,
                   p.id, p.date_jour, p.heure_debut, p.heure_fin, p.preparateurs
            FROM chantiers_planification c
            LEFT JOIN planifications p ON c.id = p.chantier_id
            WHERE c.id = %s
            ORDER BY p.date_jour, p.heure_debut
        """, (chantier_id,))
        
        results = cur.fetchall()
        if not results:
            raise HTTPException(status_code=404, detail="Chantier non trouvé après mise à jour")
        
        # Construire la réponse
        first_row = results[0]
        chantier = {
            "id": first_row[0],
            "type_activite": first_row[1],
            "description": first_row[2],
            "group_id": first_row[3],
            "updated_at": first_row[4].isoformat(),
            "planifications": []
        }
        
        for row in results:
            if row[5]:  # Si planification existe
                chantier["planifications"].append({
                    "id": row[5],
                    "date_jour": row[6].strftime('%Y-%m-%d'),
                    "heure_debut": row[7],
                    "heure_fin": row[8],
                    "preparateurs": row[9]
                })
        
        return {
            "status": "✅ Chantier mis à jour",
            "chantier": chantier
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
            conn.close()

@app.delete("/chantiers-planification/{chantier_id}")
def delete_chantier_planification(chantier_id: int):
    """Supprimer un chantier de planification et toutes ses planifications"""
    conn = None
    try:
        conn = get_db_connection()
        ensure_chantiers_planification_tables(conn)
        cur = conn.cursor()
        
        # Récupérer les informations avant suppression
        cur.execute("""
            SELECT c.type_activite, c.description, c.group_id, 
                   COUNT(p.id) as nb_planifications
            FROM chantiers_planification c
            LEFT JOIN planifications p ON c.id = p.chantier_id
            WHERE c.id = %s
            GROUP BY c.id, c.type_activite, c.description, c.group_id
        """, (chantier_id,))
        
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        type_activite, description, group_id, nb_planifications = result
        
        # Supprimer le chantier (les planifications sont supprimées automatiquement via CASCADE)
        cur.execute("DELETE FROM chantiers_planification WHERE id = %s", (chantier_id,))
        conn.commit()
        
        return {
            "status": "✅ Chantier supprimé",
            "chantier_id": chantier_id,
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
            conn.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

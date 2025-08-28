from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional, Any
import os
import json


# Render → Uvicorn → FastAPI

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


# Variables globales pour le pool de connexions
connection_pool = None

def init_connection_pool():
    """Initialiser le pool de connexions au startup"""
    global connection_pool
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        print("⚠️ DATABASE_URL non définie - pool désactivé")
        return
    
    try:
        # Essayer psycopg3 avec pool
        import psycopg_pool
        connection_pool = psycopg_pool.ConnectionPool(
            database_url, 
            min_size=2,        
            max_size=10,       
            max_idle=10,       
            max_lifetime=300,  
            timeout=5,
            # ✨ NOUVELLES OPTIMISATIONS ULTRA-MODERNES :
            reconnect_timeout=30,            # Reconnexion automatique si DB restart
            reconnect_failed=2,              # 2 tentatives de reconnexion
            kwargs={                         # Optimisations TCP/SSL avancées
                "sslmode": "require",        # SSL obligatoire
                "connect_timeout": 5,        # 5 sec timeout connexion
                "keepalives_idle": 600,      # 10 min avant premier keep-alive
                "keepalives_interval": 30,   # Keep-alive toutes les 30 sec
                "keepalives_count": 3        # 3 tentatives keep-alive avant abandon
            }
        )
        print("✅ Pool de connexions psycopg3 ULTRA-MODERNE initialisé (2-10 connexions)")
    except ImportError:
        try:
            # Fallback sur psycopg2 avec pool simple
            import psycopg2.pool
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                2, 10, database_url
            )
            print("✅ Pool de connexions psycopg2 initialisé (2-10 connexions)")
        except ImportError:
            print("⚠️ Aucun module de pool disponible - pool désactivé")
            connection_pool = None

def get_db_connection():  # ✅ SUPPRIMER le paramètre auto_create_tables complètement
    """Obtenir une connexion du pool (SANS création automatique de tables)"""
    global connection_pool
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL non définie")
    
    conn = None
    
    # Si le pool est disponible, l'utiliser    
    if connection_pool:
        try:
            if hasattr(connection_pool, 'getconn'):
                # psycopg2 pool
                conn = connection_pool.getconn()
                conn._pool_type = 'psycopg2_pool'
            else:
                # psycopg3 pool
                conn = connection_pool.connection()
                conn._pool_type = 'psycopg3_pool'
        except Exception as e:
            print(f"⚠️ Erreur pool, fallback connexion directe: {e}")
    
    # Fallback : créer une connexion directe si pas encore de connexion
    if not conn:
        try:
            # Essayer psycopg3 d'abord
            import psycopg
            conn = psycopg.connect(database_url)
            conn._pool_type = 'direct_psycopg3'
        except ImportError:
            try:
                # Fallback sur psycopg2
                import psycopg2
                conn = psycopg2.connect(database_url)
                conn._pool_type = 'direct_psycopg2'
            except ImportError:
                raise Exception("Aucun module psycopg disponible")
    
    # ✅ SUPPRESSION COMPLÈTE : Plus aucune création automatique de tables
    # Les tables ne sont créées que manuellement via /admin/create-all-tables
    
    return conn

def close_db_connection(conn):
    """Libérer une connexion selon son type (rétrocompatible)"""
    if not conn:
        return
        
    global connection_pool
    
    # Récupérer le type depuis les métadonnées
    conn_type = getattr(conn, '_pool_type', 'unknown')
    
    try:
        if conn_type == 'psycopg2_pool' and connection_pool:
            # psycopg2 pool - remettre dans le pool
            connection_pool.putconn(conn)
            
        elif conn_type == 'psycopg3_pool':
            # psycopg3 pool - NE PAS FERMER ! Le pool gère automatiquement
            # La connexion retourne au pool automatiquement grâce au context manager
            pass
            
        else:
            # Connexion directe - fermer normalement
            conn.close()
            
    except Exception as e:
        print(f"⚠️ Erreur lors de la libération: {e}")
        try:
            conn.close()
        except:
            pass

__all__ = ['get_db_connection', 'close_db_connection', 'ensure_chantiers_tables', 'ensure_etiquettes_grille_tables']


# Import conditionnel des routers pour éviter les erreurs de déploiement
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

try:
    from disponibilite import router as disponibilites_router
    DISPONIBILITES_AVAILABLE = True
except ImportError:
    disponibilites_router = None
    DISPONIBILITES_AVAILABLE = False

try:
    from texte_etiquette import router as texte_etiquette_router
    TEXTE_ETIQUETTE_AVAILABLE = True
except ImportError:
    texte_etiquette_router = None
    TEXTE_ETIQUETTE_AVAILABLE = False


def ensure_etiquettes_grille_tables(conn):
    """S'assurer que les tables pour les étiquettes de grille existent avec support du texte"""
    cur = conn.cursor()
    
    try:
        # Table principale des étiquettes de grille AVEC la colonne texte
        cur.execute("""
            CREATE TABLE IF NOT EXISTS etiquettes_grille (
                id SERIAL PRIMARY KEY,
                type_activite VARCHAR(255) NOT NULL,
                description TEXT,
                group_id VARCHAR(100),
                texte TEXT DEFAULT '',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # ✅ AMÉLIORATION : Vérification robuste de la colonne texte (migration)
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'etiquettes_grille' AND column_name = 'texte'
        """)
        
        if not cur.fetchone():
            # Ajouter la colonne texte si elle n'existe pas
            cur.execute("ALTER TABLE etiquettes_grille ADD COLUMN texte TEXT DEFAULT ''")
            print("✅ Migration: Colonne 'texte' ajoutée à etiquettes_grille")
        
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
        
        # ✅ AMÉLIORATION : Index pour les recherches dans le texte (PostgreSQL)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_etiquettes_type_activite 
            ON etiquettes_grille (type_activite)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_etiquettes_group_id 
            ON etiquettes_grille (group_id)
        """)
        
        # ✅ NOUVEAU : Index pour recherche full-text dans le texte des étiquettes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_etiquettes_texte_search 
            ON etiquettes_grille 
            USING gin(to_tsvector('french', COALESCE(texte, '')))
        """)
        
        # ✅ NOUVEAU : Index pour les étiquettes avec texte non-vide
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_etiquettes_has_text 
            ON etiquettes_grille (texte) 
            WHERE texte IS NOT NULL AND texte != ''
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_planif_etiquettes_date 
            ON planifications_etiquettes (date_jour)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_planif_etiquettes_etiquette 
            ON planifications_etiquettes (etiquette_id)
        """)
        
        # ✅ AMÉLIORATION : Trigger pour updated_at automatique
        cur.execute("""
            CREATE OR REPLACE FUNCTION update_etiquettes_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        
        cur.execute("""
            DROP TRIGGER IF EXISTS update_etiquettes_grille_updated_at ON etiquettes_grille;
            CREATE TRIGGER update_etiquettes_grille_updated_at 
                BEFORE UPDATE ON etiquettes_grille 
                FOR EACH ROW EXECUTE FUNCTION update_etiquettes_updated_at();
        """)
        
        conn.commit()
        print("✅ Tables étiquettes de grille créées/vérifiées avec support du texte")
        
    except Exception as e:
        print(f"🚨 Erreur lors de la création des tables étiquettes: {e}")
        conn.rollback()
        raise

def ensure_chantiers_tables(conn):
    """S'assurer que les tables pour les chantiers et préparateurs existent"""
    cur = conn.cursor()
    
    try:
        # ========================================================================
        # 1. CRÉATION DES TABLES PRINCIPALES
        # ========================================================================
        
        # Table des préparateurs (doit être créée en premier pour les références)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS preparateurs (
                nom VARCHAR(255) PRIMARY KEY,
                nni VARCHAR(50) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table des chantiers (SANS forced_planning_lock)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chantiers (
                id VARCHAR(255) PRIMARY KEY,
                label VARCHAR(500) NOT NULL,
                status VARCHAR(100) DEFAULT 'Nouveau',
                prepTime INTEGER DEFAULT 0,
                endDate VARCHAR(50),
                preparateur_nom VARCHAR(255) REFERENCES preparateurs(nom) ON UPDATE CASCADE ON DELETE SET NULL,
                ChargeRestante INTEGER DEFAULT 0,
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

        # Table des verrous de planification (NOUVEAU !)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS verrous_planification (
                id SERIAL PRIMARY KEY,
                chantier_id VARCHAR(255) NOT NULL REFERENCES chantiers(id) ON DELETE CASCADE,
                semaine VARCHAR(50) NOT NULL,
                preparateur_nom VARCHAR(255) NOT NULL,
                minutes INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                
                CONSTRAINT unique_verrou_chantier_semaine UNIQUE (chantier_id, semaine)
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
        
        # ========================================================================
        # 2. MIGRATION : SUPPRIMER L'ANCIENNE COLONNE FORCED_PLANNING_LOCK
        # ========================================================================
        
        # Vérifier si l'ancienne colonne existe et la supprimer
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'chantiers' AND column_name = 'forced_planning_lock'
        """)
        if cur.fetchone():
            print("🔄 Migration: Suppression de forced_planning_lock")
            cur.execute("DROP INDEX IF EXISTS idx_chantiers_forced_planning_lock")
            cur.execute("ALTER TABLE chantiers DROP COLUMN forced_planning_lock")
            print("✅ Migration: forced_planning_lock supprimé")
        
        # Index pour améliorer les performances
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chantiers_status ON chantiers (status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chantiers_preparateur ON chantiers (preparateur_nom)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planifications_chantier ON planifications (chantier_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_planifications_semaine ON planifications (semaine)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_soldes_chantier ON soldes (chantier_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_soldes_semaine ON soldes (semaine)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_verrous_chantier ON verrous_planification (chantier_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_verrous_semaine ON verrous_planification (semaine)")
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
        print("✅ Tables créées/vérifiées avec succès")
        
    except Exception as e:
        print(f"🚨 Erreur lors de la création des tables: {e}")
        conn.rollback()
        raise


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    # 🚀 STARTUP
    init_connection_pool()
    print("🚀 Application démarrée avec pool de connexions")
    
    yield  # ← App tourne ici (toutes tes routes sync)
    
    # 🛑 SHUTDOWN
    global connection_pool
    if connection_pool:
        try:
            if hasattr(connection_pool, 'closeall'):
                connection_pool.closeall()
            elif hasattr(connection_pool, 'close'):
                connection_pool.close()
            print("✅ Pool de connexions fermé proprement")
        except Exception as e:
            print(f"⚠️ Erreur lors de la fermeture du pool: {e}")

app = FastAPI(
    title="API de Planification",
    description="API pour la gestion des chantiers et des étiquettes de planification",
    version="2.0.0",
    lifespan=lifespan  # ← Remplace les @app.on_event()
)



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclure les routers seulement s'ils sont disponibles
if BETA_API_AVAILABLE and beta_api_router:
    app.include_router(beta_api_router, prefix="", tags=["Beta-API"])

if GRILLE_SEMAINE_AVAILABLE and grille_semaine_router:
    app.include_router(grille_semaine_router, prefix="", tags=["Grille Semaine"])

if DISPONIBILITES_AVAILABLE and disponibilites_router:
    app.include_router(disponibilites_router, prefix="", tags=["Disponibilités"])

if TEXTE_ETIQUETTE_AVAILABLE and texte_etiquette_router:
    app.include_router(texte_etiquette_router, prefix="", tags=["Templates et Texte Étiquettes"])
    
@app.get("/")
def read_root():
    """Point d'entrée de l'API"""
    modules_status = {
        "beta_api": "✅ Disponible" if BETA_API_AVAILABLE else "❌ Non disponible",
        "grille_semaine": "✅ Disponible" if GRILLE_SEMAINE_AVAILABLE else "❌ Non disponible",
        "disponibilites": "✅ Disponible" if DISPONIBILITES_AVAILABLE else "❌ Non disponible",
        "texte_etiquette": "✅ Disponible" if TEXTE_ETIQUETTE_AVAILABLE else "❌ Non disponible"
    }
    
    pool_status = "✅ Actif" if connection_pool else "❌ Désactivé"
    
    # ✅ AJOUT : Vérifier les tables spécifiques
    tables_status = {}
    if TEXTE_ETIQUETTE_AVAILABLE:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Vérifier table text_templates
            cur.execute("SELECT COUNT(*) FROM text_templates")
            templates_count = cur.fetchone()[0]
            tables_status["text_templates"] = f"✅ {templates_count} template(s)"
            
            # Vérifier colonne texte dans etiquettes
            cur.execute("SELECT COUNT(*) FROM etiquettes_grille WHERE texte IS NOT NULL AND texte != ''")
            etiquettes_with_text = cur.fetchone()[0]
            tables_status["etiquettes_with_text"] = f"✅ {etiquettes_with_text} étiquette(s) avec texte"
            
            close_db_connection(conn)
        except Exception:
            tables_status["text_templates"] = "⚠️ Non vérifiable"
            tables_status["etiquettes_with_text"] = "⚠️ Non vérifiable"
    
    return {
        "message": "API de Planification",
        "version": "2.0.0",
        "pool_connexions": pool_status,
        "modules": modules_status,
        "endpoints": {
            "beta_api": "Gestion des chantiers et préparateurs" if BETA_API_AVAILABLE else "Module non chargé",
            "grille_semaine": "Gestion des étiquettes et horaires" if GRILLE_SEMAINE_AVAILABLE else "Module non chargé",
            "disponibilites": "Gestion des disponibilités" if DISPONIBILITES_AVAILABLE else "Module non chargé",
            "texte_etiquette": "Gestion des templates et textes d'étiquettes" if TEXTE_ETIQUETTE_AVAILABLE else "Module non chargé"
        },
        # ✅ AJOUT : Statut détaillé des tables
        "tables_status": tables_status if TEXTE_ETIQUETTE_AVAILABLE else {}
    }


@app.get("/health")
def health_check():
    """Vérification de santé de l'API"""
    pool_info = {}
    if connection_pool:
        try:
            if hasattr(connection_pool, 'get_stats'):
                # psycopg3 pool stats - c'est un DICTIONNAIRE !
                stats = connection_pool.get_stats()
                pool_info = {
                    "pool_size": stats.get("pool_size", "N/A"),           
                    "pool_available": stats.get("pool_available", "N/A"), 
                    "requests_waiting": stats.get("requests_waiting", "N/A"), 
                    "max_idle": "10 secondes",
                    "max_lifetime": "5 minutes"
                }
            else:
                # psycopg2 pool - info basique
                pool_info = {
                    "pool": "active", 
                    "type": "psycopg2",
                    "note": "Stats limitées"
                }
        except Exception as e:
            pool_info = {"pool_error": str(e)}
    else:
        pool_info = {"pool": "disabled", "reason": "Pool non initialisé"}
    
    return {
        "status": "healthy", 
        "service": "planning-api",
        "pool": pool_info
    }




# ========================================================================
# ENDPOINTS DE NETTOYAGE COMPLET DE LA BASE DE DONNÉES
# ========================================================================


@app.delete("/admin/reset-database")
def reset_complete_database():
    """DANGER: Vider complètement toute la base de données - À utiliser avec précaution!"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Liste des tables principales de l'application
        tables_to_check = [
            'chantiers', 'planifications', 'soldes', 'preparateurs', 
            'disponibilites', 'etiquettes_grille', 'planifications_etiquettes',
            'horaires_preparateurs', 'etiquettes_planification', 'text_templates'  # ← AJOUT
        ]
        
        # ... rest of existing code ...
        
        # 1. Supprimer les tables de planifications en premier (dépendent des autres)
        for table in ['planifications', 'planifications_etiquettes', 'soldes', 'disponibilites', 'text_templates']:  # ← AJOUT
            try:
                cur.execute(f"DELETE FROM {table}")
                deleted = cur.rowcount
                if deleted > 0:
                    deletion_summary.append({"table": table, "deleted": deleted})
            except Exception as e:
                # Table n'existe peut-être pas
                pass
        
        # ... rest of existing code ...

@app.delete("/admin/drop-all-tables")
def drop_all_tables():
    """DANGER EXTRÊME: Supprimer complètement toutes les tables - Structure ET données!"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Lister toutes les tables de l'application
        cur.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename IN ('chantiers', 'planifications', 'soldes', 'preparateurs', 
                             'disponibilites', 'etiquettes_grille', 'planifications_etiquettes',
                             'horaires_preparateurs', 'etiquettes_planification', 'text_templates')  -- ← AJOUT
        """)
        
        # ... rest of existing code ...


@app.post("/admin/create-all-tables")
def create_all_tables():
    """Créer toutes les tables de l'application"""
    conn = None
    try:
        conn = get_db_connection()
        
        # Créer les tables des chantiers et préparateurs
        ensure_chantiers_tables(conn)
        
        # Créer les tables des étiquettes
        ensure_etiquettes_grille_tables(conn)
        
        # ✅ AJOUT : Créer les tables des templates de texte
        from texte_etiquette import ensure_text_templates_table
        try:
            ensure_text_templates_table(conn)
            templates_table_created = True
        except Exception as e:
            print(f"⚠️ Erreur création table templates: {e}")
            templates_table_created = False
        
        # Vérifier que les tables ont bien été créées
        cur = conn.cursor()
        cur.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename IN ('preparateurs', 'chantiers', 'planifications', 'soldes', 
                             'disponibilites', 'horaires_preparateurs',
                             'etiquettes_grille', 'planifications_etiquettes', 'text_templates')  -- ← AJOUT
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
                ],
                "texte_system": [
                    "text_templates"
                ] if templates_table_created else []  # ← AJOUT
            },
            "message": "🎉 Votre base de données est prête à recevoir des données !",
            "next_steps": [
                "Utilisez Beta-API.html avec les routes /chantiers/*",
                "Utilisez Grille semaine.html avec les routes /etiquettes-grille/*",
                "Utilisez les routes /text-templates/* pour gérer les templates",  # ← AJOUT
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
           close_db_connection(conn)

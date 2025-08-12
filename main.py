from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional, Any
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "API Pilotage RIP fonctionne!", "status": "✅ Version temporaire sans base de données"}

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

@app.get("/chantiers")
def get_chantiers():
    """Récupérer tous les chantiers depuis PostgreSQL"""
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
            # La colonne existe, requête complète
            cur.execute("""
                SELECT c.id, c.label, c.status, c.prepTime, c.endDate, c.preparateur_nom, c.ChargeRestante,
                       c.forced_planning_lock, p.chantier_id, p.semaine, p.minutes
                FROM chantiers c
                LEFT JOIN planifications p ON c.id = p.chantier_id
                ORDER BY c.id, p.semaine
            """)
            
            rows = cur.fetchall()
            
            # Regrouper les résultats par chantier (avec verrous)
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
                        "planification": {}
                    }
                
                # Ajouter la planification si elle existe
                if row[9] and row[10]:  # semaine et minutes
                    chantiers[chantier_id]["planification"][row[9]] = row[10]
        else:
            # La colonne n'existe pas encore, requête sans forced_planning_lock
            cur.execute("""
                SELECT c.id, c.label, c.status, c.prepTime, c.endDate, c.preparateur_nom, c.ChargeRestante,
                       p.chantier_id, p.semaine, p.minutes
                FROM chantiers c
                LEFT JOIN planifications p ON c.id = p.chantier_id
                ORDER BY c.id, p.semaine
            """)
            
            rows = cur.fetchall()
            
            # Regrouper les résultats par chantier (sans verrous)
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
                        "planification": {}
                    }
                
                # Ajouter la planification si elle existe
                if row[8] and row[9]:  # semaine et minutes (décalé car pas de forced_planning_lock)
                    chantiers[chantier_id]["planification"][row[8]] = row[9]
        
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

# ===== ENDPOINTS CRUD POUR CHANTIERS =====

@app.post("/chantiers")
def create_chantier(chantier: Dict[str, Any]):
    """Créer un nouveau chantier dans PostgreSQL"""
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
    """Mettre à jour un chantier existant"""
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
    """Mettre à jour la planification d'un chantier avec préservation intelligente de l'historique"""
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
    """Synchronisation complète de la planification après répartition automatique"""
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

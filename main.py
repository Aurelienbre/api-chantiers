from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional, Any
import os
import json

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


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================================================================
# GESTION DES CHANTIERS DE PLANIFICATION (Beta-API.html)
# ========================================================================


# Preparateurs

@app.get("/preparateurs")
def get_preparateurs():
    """Récupérer tous les préparateurs depuis PostgreSQL"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        # Créer les tables si elles n'existent pas
        ensure_chantiers_tables(conn)
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



# Chantiers

@app.get("/chantiers")
def get_chantiers():
    """Récupérer tous les chantiers depuis PostgreSQL"""
    conn = None
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        # Créer les tables si elles n'existent pas
        ensure_chantiers_tables(conn)
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
    


# Disponibilité et planification

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


# Verouillages des chantiers

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


# Soldes des chantiers

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
    """Supprimer un chantier spécifique et toutes ses données associées"""
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
    """Supprimer tous les chantiers et toutes leurs données associées"""
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



# ========================================================================
#  GESTION DES ETIQUETTES DE PLANIFICATION (Grille semaine.html)
# ========================================================================

# Horaires des préparateurs 

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



# Gestion des étiquettes de planification

@app.get("/etiquettes-grille")
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
            conn.close()

@app.post("/etiquettes-grille")
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
            conn.close()

@app.put("/etiquettes-grille/{etiquette_id}")
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
            conn.close()

@app.put("/etiquettes-grille/{etiquette_id}/horaires")
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
            conn.close()

@app.post("/etiquettes-grille/{etiquette_id}/planifications")
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
            conn.close()

@app.put("/etiquettes-grille/{etiquette_id}/planifications/{planification_id}")
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
            conn.close()

@app.delete("/etiquettes-grille/{etiquette_id}")
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
            conn.close()


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

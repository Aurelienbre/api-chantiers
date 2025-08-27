"""
Routes pour la gestion des chantiers de planification (Beta-API.html)

Ce module contient toutes les routes relatives à :
- La gestion des préparateurs
- La gestion des chantiers
- La planification et les disponibilités
- Les verrous de planification
- Les soldes des chantiers
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Optional, Any
from main import get_db_connection, close_db_connection


# Créer le router pour les routes Beta-API
router = APIRouter(
    prefix="",
    tags=["Beta-API Chantiers"],
    responses={404: {"description": "Not found"}},
)



# ========================================================================
# GESTION DES CHANTIERS DE PLANIFICATION (Beta-API.html)
# ========================================================================

# Preparateurs

@router.get("/preparateurs")
def get_preparateurs():
    """Récupérer tous les préparateurs depuis PostgreSQL"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT nom, nni FROM preparateurs ORDER BY nom")
        rows = cur.fetchall()

        # Convertir en dictionnaire nom -> nni
        preparateurs = {row[0]: row[1] for row in rows}
        
        return preparateurs
        
    except Exception as e:
        print(f"🚨 Erreur GET /preparateurs: {str(e)}")
        return {"error": f"Erreur base de données: {str(e)}"}
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.post("/preparateurs")
def sync_preparateurs(preparateurs_data: Dict[str, Any]):
    """Synchroniser les préparateurs avec PostgreSQL (optimisé)"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        preparateurs = preparateurs_data.get('preparateurs', {})
        
        if not preparateurs:
            return {"status": "⚠️ Aucun préparateur à synchroniser", "count": 0}
        
        # ✅ OPTIMISATION : Bulk insert avec executemany()
        preparateurs_data_list = [(nom, nni) for nom, nni in preparateurs.items()]
        
        cur.executemany("""
            INSERT INTO preparateurs (nom, nni) 
            VALUES (%s, %s) 
            ON CONFLICT (nom) DO UPDATE SET nni = EXCLUDED.nni
        """, preparateurs_data_list)
        
        conn.commit()

        return {"status": "✅ Préparateurs synchronisés", "count": len(preparateurs_data_list)}
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.put("/preparateurs/{ancien_nom}")
def update_preparateur(ancien_nom: str, preparateur_data: Dict[str, Any]):
    """Modifier un préparateur (nom et/ou NNI) avec mise à jour en cascade"""
    conn = None
    try:
        nouveau_nom = preparateur_data.get('nom', ancien_nom)
        nouveau_nni = preparateur_data.get('nni')
        
        if not nouveau_nni:
            raise HTTPException(status_code=400, detail="NNI requis")
        
        conn = get_db_connection()
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

        return {
            "status": "✅ Préparateur modifié avec succès",
            "ancien_nom": ancien_nom,
            "nouveau_nom": nouveau_nom,
            "nouveau_nni": nouveau_nni,
            "chantiers_mis_a_jour": chantiers_updated,
            "disponibilites_mises_a_jour": disponibilites_updated
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.delete("/preparateurs/{nom}")
def delete_preparateur(nom: str):
    """Supprimer un préparateur de PostgreSQL"""
    conn = None
    try:
        conn = get_db_connection()
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
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass

# Chantiers

@router.get("/chantiers")
def get_chantiers():
    """Récupérer tous les chantiers depuis PostgreSQL avec optimisation SQL"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ✅ OPTIMISATION : Faire l'agrégation côté SQL
        cur.execute("""
            SELECT 
                c.id,
                c.label,
                c.status,
                c.prepTime,
                c.endDate,
                c.preparateur_nom,
                c.ChargeRestante,
                -- Agrégation des planifications en JSON
                COALESCE(
                    json_object_agg(p.semaine, p.minutes) FILTER (WHERE p.semaine IS NOT NULL),
                    '{}'::json
                ) as planification,
                -- Agrégation des soldes en JSON
                COALESCE(
                    json_object_agg(s.semaine, s.minutes) FILTER (WHERE s.semaine IS NOT NULL),
                    '{}'::json
                ) as soldes,
                -- Agrégation des verrous en JSON
                COALESCE(
                    json_object_agg(
                        v.semaine, 
                        json_build_object('preparateur', v.preparateur_nom, 'minutes', v.minutes)
                    ) FILTER (WHERE v.semaine IS NOT NULL),
                    '{}'::json
                ) as forcedPlanningLock
            FROM chantiers c
            LEFT JOIN planifications p ON c.id = p.chantier_id
            LEFT JOIN soldes s ON c.id = s.chantier_id  
            LEFT JOIN verrous_planification v ON c.id = v.chantier_id
            GROUP BY c.id, c.label, c.status, c.prepTime, c.endDate, c.preparateur_nom, c.ChargeRestante
            ORDER BY c.id
        """)
        
        rows = cur.fetchall()
        
        # ✅ Plus de traitement Python complexe !
        chantiers = {}
        for row in rows:
            chantiers[row[0]] = {
                "id": row[0],
                "label": row[1] or "",
                "status": row[2] or "Nouveau", 
                "prepTime": row[3] or 0,
                "endDate": row[4] or "",
                "preparateur": row[5] or None,
                "ChargeRestante": row[6] or 0,
                "planification": row[7],      # ← Déjà au format JSON !
                "soldes": row[8],             # ← Déjà au format JSON !
                "forcedPlanningLock": row[9]  # ← Déjà au format JSON !
            }
        
        return chantiers
        
    except Exception as e:
        print(f"🚨 Erreur GET /chantiers: {str(e)}")
        return {"error": f"Erreur base de données: {str(e)}"}
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.post("/chantiers")
def create_chantier(chantier: Dict[str, Any]):
    """Créer un nouveau chantier dans PostgreSQL"""
    chantier_id = chantier.get('id')
    if not chantier_id:
        raise HTTPException(status_code=400, detail="ID du chantier requis")

    conn = None
    try:
        
        conn = get_db_connection()
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
        return {"status": "✅ Chantier créé/mis à jour", "id": chantier.get('id')}
        
    except Exception as e:
        if conn:
            conn.rollback()  # ← MANQUANT
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.put("/chantiers/{chantier_id}")
def update_chantier(chantier_id: str, chantier: Dict[str, Any]):
    """Mettre à jour un chantier avec requête sécurisée optimisée"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ✅ OPTIMISATION : Mapping des champs sécurisé
        field_mapping = {
            'label': 'label',
            'status': 'status', 
            'prepTime': 'prepTime',
            'endDate': 'endDate',
            'preparateur': 'preparateur_nom',
            'ChargeRestante': 'ChargeRestante'
        }
        
        # Construire la requête sécurisée
        updates = []
        params = []
        
        for field_name, db_column in field_mapping.items():
            if field_name in chantier and chantier[field_name] is not None:
                updates.append(f"{db_column} = %s")
                params.append(chantier[field_name])
        
        if not updates:
            return {"status": "⚠️ Aucune modification fournie"}
        
        # ✅ Requête avec vérification d'existence intégrée
        params.append(chantier_id)
        query = f"""
            UPDATE chantiers 
            SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, label, status
        """
        
        cur.execute(query, params)
        result = cur.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        conn.commit()
        
        return {
            "status": "✅ Chantier mis à jour", 
            "id": result[0],
            "label": result[1],
            "status": result[2]
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)


# Disponibilité et planification

@router.put("/planification")
def update_planification(planif: Dict[str, Any]):
    """Mettre à jour la planification d'un chantier avec préservation intelligente de l'historique"""
    conn = None
    try:
        from datetime import datetime, timedelta
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        chantier_id = planif.get('chantier_id')
        planifications = planif.get('planifications', {})
        preserve_past = planif.get('preserve_past', True)
        
        if preserve_past:
            # Calculer la semaine courante
            now = datetime.utcnow()
            if now.weekday() == 6:
                now = now - timedelta(days=1)
            
            year, week_num, _ = now.isocalendar()
            current_week_key = f"{year}-W{week_num:02d}"
            
            # Supprimer seulement les planifications >= semaine courante
            cur.execute("""
                DELETE FROM planifications 
                WHERE chantier_id = %s 
                AND semaine >= %s
            """, (chantier_id, current_week_key))
            
            deleted_count = cur.rowcount
            
        else:
            # Mode legacy : Supprimer tout
            cur.execute("DELETE FROM planifications WHERE chantier_id = %s", (chantier_id,))
            deleted_count = cur.rowcount
        
        # ✅ CORRECTION : Utiliser ON CONFLICT pour éviter les doublons
        inserted_count = 0
        for semaine, minutes in planifications.items():
            if minutes > 0:
                cur.execute("""
                    INSERT INTO planifications (chantier_id, semaine, minutes) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (chantier_id, semaine) 
                    DO UPDATE SET minutes = EXCLUDED.minutes
                """, (chantier_id, semaine, minutes))
                inserted_count += 1
        
        conn.commit()

        return {
            "status": "✅ Planification mise à jour avec préservation intelligente",
            "chantier_id": chantier_id,
            "mode": "preservation" if preserve_past else "legacy",
            "deleted_future": deleted_count,
            "inserted_new": inserted_count
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.put("/disponibilites")
def update_disponibilites(dispo: Dict[str, Any]):
    """Mettre à jour les disponibilités d'un préparateur"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        preparateur_nom = dispo.get('preparateur_nom')
        disponibilites = dispo.get('disponibilites', {})
        
        # Supprimer les anciennes disponibilités pour ce préparateur
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

        return {"status": "✅ Disponibilités mises à jour", "preparateur": preparateur_nom}
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.put("/sync-planning")
def sync_complete_planning(data: Dict[str, Any]):
    """Synchronisation complète avec transaction explicite optimisée"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ✅ Transaction explicite pour TOUT grouper
        cur.execute("BEGIN")
        
        try:
            # ✅ OPTIMISATION : Préparer toutes les données avant insertion
            chantiers_data = []
            planifications_data = []
            disponibilites_data = []
            
            # Préparer les données chantiers
            if 'chantiers' in data:
                for chantier_id, chantier_data in data['chantiers'].items():
                    chantiers_data.append((
                        chantier_data.get('label', ''),
                        chantier_data.get('status', 'Nouveau'),
                        chantier_data.get('prepTime', 0),
                        chantier_data.get('endDate', ''),
                        chantier_data.get('preparateur'),
                        chantier_data.get('ChargeRestante', chantier_data.get('prepTime', 0)),
                        chantier_id
                    ))
                    
                    # Préparer les planifications
                    planifications = chantier_data.get('planification', {})
                    for semaine, minutes in planifications.items():
                        if minutes > 0:
                            planifications_data.append((chantier_id, semaine, minutes))
            
            # Préparer les disponibilités
            if 'data' in data:
                for preparateur_nom, disponibilites in data['data'].items():
                    for semaine, info in disponibilites.items():
                        minutes = info.get('minutes', 0) if isinstance(info, dict) else info
                        updated_at = info.get('updatedAt', '') if isinstance(info, dict) else ''
                        if minutes > 0:
                            disponibilites_data.append((preparateur_nom, semaine, minutes, updated_at))
            
            # ✅ BULK OPERATIONS avec executemany()
            if chantiers_data:
                cur.executemany("""
                    UPDATE chantiers SET 
                        label = %s, status = %s, prepTime = %s, 
                        endDate = %s, preparateur_nom = %s, ChargeRestante = %s
                    WHERE id = %s
                """, chantiers_data)
            
            # Suppression groupée des planifications
            if planifications_data:
                chantier_ids = list(set(row[0] for row in planifications_data))
                cur.executemany("DELETE FROM planifications WHERE chantier_id = %s", 
                               [(cid,) for cid in chantier_ids])
                
                # Insertion groupée des planifications
                cur.executemany("""
                    INSERT INTO planifications (chantier_id, semaine, minutes) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (chantier_id, semaine) 
                    DO UPDATE SET minutes = EXCLUDED.minutes
                """, planifications_data)
            
            # Disponibilités groupées
            if disponibilites_data:
                preparateurs = list(set(row[0] for row in disponibilites_data))
                cur.executemany("DELETE FROM disponibilites WHERE preparateur_nom = %s",
                               [(prep,) for prep in preparateurs])
                
                cur.executemany("""
                    INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt) 
                    VALUES (%s, %s, %s, %s)
                """, disponibilites_data)
            
            # ✅ Commit unique à la fin
            cur.execute("COMMIT")
            
            return {
                "status": "✅ Planification complète synchronisée (optimisée)",
                "chantiers_updated": len(chantiers_data),
                "planifications_inserted": len(planifications_data), 
                "disponibilites_inserted": len(disponibilites_data)
            }
            
        except Exception as e:
            # ✅ Rollback en cas d'erreur
            cur.execute("ROLLBACK")
            raise
            
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)


@router.get("/disponibilites")
def get_disponibilites():
    """Récupérer toutes les disponibilités depuis PostgreSQL"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT preparateur_nom, semaine, minutes, updatedAt 
            FROM disponibilites 
            ORDER BY preparateur_nom, semaine
        """)
        
        rows = cur.fetchall()

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
        print(f"🚨 Erreur GET /disponibilites: {str(e)}")
        return {"error": f"Erreur base de données: {str(e)}"}
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


# Verouillages des chantiers

@router.get("/chantiers/{chantier_id}/forced-planning-lock")
def get_forced_planning_lock(chantier_id: str):
    """Récupérer les verrous de planification forcée d'un chantier"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Récupérer tous les verrous de ce chantier depuis la table verrous_planification
        cur.execute("""
            SELECT semaine, preparateur_nom, minutes 
            FROM verrous_planification 
            WHERE chantier_id = %s 
            ORDER BY semaine
        """, (chantier_id,))
        
        rows = cur.fetchall()
        
        # Construire le dictionnaire des verrous au format attendu
        forced_planning_lock = {}
        for row in rows:
            semaine, preparateur_nom, minutes = row
            forced_planning_lock[semaine] = {
                "preparateur": preparateur_nom,
                "minutes": minutes
            }
        
        return {
            "chantier_id": chantier_id, 
            "forced_planning_lock": forced_planning_lock
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.put("/chantiers/{chantier_id}/forced-planning-lock")
def update_forced_planning_lock(chantier_id: str, lock_data: Dict[str, Any]):
    """Mettre à jour les verrous de planification forcée d'un chantier"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Valider et normaliser les données de verrous
        forced_planning_lock = lock_data.get('forced_planning_lock', {})
        
        # Supprimer les anciens verrous pour ce chantier
        cur.execute("DELETE FROM verrous_planification WHERE chantier_id = %s", (chantier_id,))
        
        # Insérer les nouveaux verrous
        inserted_count = 0
        for semaine, verrou_info in forced_planning_lock.items():
            if isinstance(verrou_info, dict):
                preparateur = verrou_info.get('preparateur', '')
                minutes = verrou_info.get('minutes', 0)
            else:
                # Format legacy : juste les minutes
                preparateur = ''
                minutes = verrou_info
            
            if minutes > 0:  # Ne stocker que les verrous avec des minutes
                cur.execute("""
                    INSERT INTO verrous_planification (chantier_id, semaine, preparateur_nom, minutes)
                    VALUES (%s, %s, %s, %s)
                """, (chantier_id, semaine, preparateur, minutes))
                inserted_count += 1
        
        conn.commit()

        return {
            "status": "✅ Verrous de planification mis à jour",
            "chantier_id": chantier_id,
            "verrous_inserted": inserted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.delete("/chantiers/{chantier_id}/forced-planning-lock")
def clear_forced_planning_lock(chantier_id: str):
    """Supprimer tous les verrous de planification forcée d'un chantier"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Supprimer tous les verrous de ce chantier
        cur.execute("DELETE FROM verrous_planification WHERE chantier_id = %s", (chantier_id,))
        deleted_count = cur.rowcount
        
        conn.commit()

        return {
            "status": "✅ Verrous de planification supprimés",
            "chantier_id": chantier_id,
            "verrous_deleted": deleted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass

@router.put("/forced-planning-lock")
def sync_forced_planning_lock_put(lock_data: Dict[str, Any]):
    """Synchroniser les verrous de planification forcée depuis le client (méthode PUT)"""
    conn = None
    try:
        chantier_id = lock_data.get('chantier_id')
        forced_planning_lock = lock_data.get('forced_planning_lock', {})
        
        if not chantier_id:
            raise HTTPException(status_code=400, detail="chantier_id requis")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Supprimer les anciens verrous pour ce chantier
        cur.execute("DELETE FROM verrous_planification WHERE chantier_id = %s", (chantier_id,))
        
        # Insérer les nouveaux verrous
        inserted_count = 0
        for semaine, verrou_info in forced_planning_lock.items():
            if isinstance(verrou_info, dict):
                preparateur = verrou_info.get('preparateur', '')
                minutes = verrou_info.get('minutes', 0)
            else:
                # Format legacy : juste les minutes
                preparateur = ''
                minutes = verrou_info
            
            if minutes > 0:  # Ne stocker que les verrous avec des minutes
                cur.execute("""
                    INSERT INTO verrous_planification (chantier_id, semaine, preparateur_nom, minutes)
                    VALUES (%s, %s, %s, %s)
                """, (chantier_id, semaine, preparateur, minutes))
                inserted_count += 1
        
        conn.commit()

        return {
            "status": "✅ Verrous synchronisés",
            "chantier_id": chantier_id,
            "verrous_inserted": inserted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


@router.post("/forced-planning-lock")
def sync_forced_planning_lock(lock_data: Dict[str, Any]):
    """Synchroniser les verrous de planification forcée depuis le client (méthode POST)"""
    conn = None
    try:
        chantier_id = lock_data.get('chantier_id')
        forced_planning_lock = lock_data.get('forced_planning_lock', {})
        
        if not chantier_id:
            raise HTTPException(status_code=400, detail="chantier_id requis")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier que le chantier existe
        cur.execute("SELECT id FROM chantiers WHERE id = %s", (chantier_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Chantier non trouvé")
        
        # Supprimer les anciens verrous pour ce chantier
        cur.execute("DELETE FROM verrous_planification WHERE chantier_id = %s", (chantier_id,))
        
        # Insérer les nouveaux verrous
        inserted_count = 0
        for semaine, verrou_info in forced_planning_lock.items():
            if isinstance(verrou_info, dict):
                preparateur = verrou_info.get('preparateur', '')
                minutes = verrou_info.get('minutes', 0)
            else:
                # Format legacy : juste les minutes
                preparateur = ''
                minutes = verrou_info
            
            if minutes > 0:  # Ne stocker que les verrous avec des minutes
                cur.execute("""
                    INSERT INTO verrous_planification (chantier_id, semaine, preparateur_nom, minutes)
                    VALUES (%s, %s, %s, %s)
                """, (chantier_id, semaine, preparateur, minutes))
                inserted_count += 1
        
        conn.commit()
        
        print(f"✅ Verrous synchronisés pour {chantier_id}: {inserted_count} verrous")
        
        return {
            "status": "✅ Verrous de planification forcée synchronisés",
            "chantier_id": chantier_id,
            "verrous_inserted": inserted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"🚨 Erreur POST /forced-planning-lock: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur base de données: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass


# Soldes des chantiers

@router.get("/soldes/{chantier_id}")
def get_soldes(chantier_id: str):
    """Récupérer tous les soldes d'un chantier"""
    conn = None
    try:
        conn = get_db_connection()
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
                close_db_connection(conn)
            except:
                pass


@router.put("/soldes")
def update_soldes(solde_data: Dict[str, Any]):
    """Mettre à jour les soldes d'un chantier"""
    conn = None
    try:
        conn = get_db_connection()
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
                close_db_connection(conn)
            except:
                pass


@router.post("/soldes")
def create_or_update_solde(solde_data: Dict[str, Any]):
    """Créer ou mettre à jour un solde spécifique"""
    conn = None
    try:
        conn = get_db_connection()
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
                close_db_connection(conn)
            except:
                pass


@router.delete("/soldes/{chantier_id}")
def delete_all_soldes(chantier_id: str):
    """Supprimer tous les soldes d'un chantier"""
    conn = None
    try:
        conn = get_db_connection()
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
                close_db_connection(conn)
            except:
                pass


@router.delete("/soldes/{chantier_id}/{semaine}")
def delete_solde(chantier_id: str, semaine: str):
    """Supprimer un solde spécifique"""
    conn = None
    try:
        conn = get_db_connection()
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
                close_db_connection(conn)
            except:
                pass


@router.delete("/chantiers/{chantier_id}")
def delete_chantier(chantier_id: str):
    """Supprimer un chantier spécifique et toutes ses données associées"""
    conn = None
    try:
        conn = get_db_connection()
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

        # 3. Supprimer le verrou
        cur.execute("DELETE FROM verrous_planification WHERE chantier_id = %s", (chantier_id,))
        verrous_deleted = cur.rowcount
        
        # 4. Supprimer le chantier
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
                close_db_connection(conn)
            except:
                pass


@router.delete("/chantiers")
def delete_all_chantiers():
    """Supprimer tous les chantiers et toutes leurs données associées"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Supprimer tous les soldes
        cur.execute("DELETE FROM soldes")
        soldes_deleted = cur.rowcount
        
        # 2. Supprimer toutes les planifications
        cur.execute("DELETE FROM planifications")
        planifications_deleted = cur.rowcount
        
        # 3. Supprimer tous les verrous
        cur.execute("DELETE FROM verrous_planification")
        verrous_deleted = cur.rowcount
        
        # 4. Supprimer tous les chantiers
        cur.execute("DELETE FROM chantiers")
        chantiers_deleted = cur.rowcount
        
        conn.commit()
        
        return {
            "deleted": True,
            "chantiers_deleted": chantiers_deleted,
            "planifications_deleted": planifications_deleted,
            "soldes_deleted": soldes_deleted,
            "verrous_deleted": verrous_deleted,
            "status": "success",
            "message": f"Tous les chantiers supprimés ({chantiers_deleted} chantiers, {planifications_deleted} planifications, {soldes_deleted} soldes et {verrous_deleted} verrous)"
        }
    
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression de tous les chantiers: {str(e)}")
    finally:
        if conn:
            try:
                close_db_connection(conn)
            except:
                pass

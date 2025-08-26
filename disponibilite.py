"""
Routes pour la gestion des disponibilités calculées automatiquement

Ce module contient toutes les routes relatives au nouveau système de disponibilités :
- Calcul automatique basé sur horaires - étiquettes planifiées
- Migration du format des semaines vers le standard YYYY-WXX
- Comparaison ancien/nouveau système
- Sauvegarde des disponibilités calculées
"""

import re
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from typing import Dict, Optional, Any, List
from main import get_db_connection, close_db_connection

# Créer le router pour les disponibilités
router = APIRouter(
    prefix="",
    tags=["Disponibilités Calculées"],
    responses={404: {"description": "Not found"}},
)

# ========================================================================
# UTILITAIRES POUR LE FORMAT DES SEMAINES
# ========================================================================

def valider_format_semaine(semaine: str) -> bool:
    """Valider le format de semaine YYYY-WXX (standard ISO)"""
    return bool(re.match(r'^\d{4}-W\d{2}$', semaine))

def semaine_courante() -> str:
    """Obtenir la semaine courante au format YYYY-WXX (standard ISO)"""
    today = datetime.now()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"

def dates_de_semaine(semaine: str) -> dict:
    """Convertir une semaine YYYY-WXX en dates"""
    if not valider_format_semaine(semaine):
        raise ValueError(f"Format de semaine invalide: {semaine}. Utilisez YYYY-WXX (ex: 2025-W35)")
    
    # Extraire l'année et le numéro de semaine du format ISO
    year_str, week_part = semaine.split('-')
    year = int(year_str)
    week_num = int(week_part[1:])  # Enlever le 'W' et convertir
    
    jan4 = datetime(year, 1, 4)
    week_start = jan4 + timedelta(days=(week_num - 1) * 7 - jan4.weekday())
    
    return {
        'lundi': week_start,
        'mardi': week_start + timedelta(days=1),
        'mercredi': week_start + timedelta(days=2),
        'jeudi': week_start + timedelta(days=3),
        'vendredi': week_start + timedelta(days=4),
        'samedi': week_start + timedelta(days=5),
        'dimanche': week_start + timedelta(days=6),
        'debut': week_start.date(),
        'fin': (week_start + timedelta(days=6)).date()
    }

# ========================================================================
# FONCTION DE CALCUL DES DISPONIBILITÉS (RÉUTILISABLE)
# ========================================================================

def calculer_disponibilites_preparateur(preparateur_nom: str, semaine: str, conn):
    """
    Fonction pure de calcul des disponibilités d'un préparateur
    Séparée de la logique HTTP pour réutilisabilité
    
    Args:
        preparateur_nom: Nom du préparateur
        semaine: Semaine au format YYYY-WW
        conn: Connexion à la base de données
        
    Returns:
        dict: Détails complets des disponibilités calculées
    """
    cur = conn.cursor()
    
    # 1. Récupérer les horaires du préparateur
    cur.execute("""
        SELECT jour_semaine, heure_debut, heure_fin
        FROM horaires_preparateurs
        WHERE preparateur_nom = %s
        ORDER BY CASE jour_semaine 
                     WHEN 'lundi' THEN 1 WHEN 'mardi' THEN 2 WHEN 'mercredi' THEN 3 
                     WHEN 'jeudi' THEN 4 WHEN 'vendredi' THEN 5 WHEN 'samedi' THEN 6 
                     WHEN 'dimanche' THEN 7 
                 END,
                 heure_debut
    """, (preparateur_nom,))
    
    horaires_preparateur = cur.fetchall()
    
    if not horaires_preparateur:
        return {
            "preparateur": preparateur_nom,
            "semaine": semaine,
            "disponibilite_minutes": 0,
            "disponibilite_heures": 0,
            "message": "Aucun horaire défini pour ce préparateur",
            "detail_par_jour": {}
        }
    
    # 2. Calculer les minutes totales d'horaires par jour
    horaires_par_jour = {}
    total_minutes_horaires = 0
    
    for jour, heure_debut, heure_fin in horaires_preparateur:
        if jour not in horaires_par_jour:
            horaires_par_jour[jour] = []
        
        # Convertir en minutes depuis minuit
        debut_minutes = heure_debut.hour * 60 + heure_debut.minute
        fin_minutes = heure_fin.hour * 60 + heure_fin.minute
        duree_minutes = fin_minutes - debut_minutes
        
        horaires_par_jour[jour].append({
            'debut': debut_minutes,
            'fin': fin_minutes,
            'duree': duree_minutes
        })
        
        total_minutes_horaires += duree_minutes
    
    # 3. Calculer les dates de la semaine
    dates_info = dates_de_semaine(semaine)
    dates_semaine = {k: v for k, v in dates_info.items() if k not in ['debut', 'fin']}
    
    # 4. Récupérer les étiquettes planifiées pour cette semaine
    cur.execute("""
        SELECT p.date_jour, p.heure_debut, p.heure_fin, p.preparateurs,
               e.type_activite, e.description
        FROM planifications_etiquettes p
        INNER JOIN etiquettes_grille e ON p.etiquette_id = e.id
        WHERE p.date_jour BETWEEN %s AND %s
        AND p.preparateurs LIKE %s
    """, (dates_info['debut'], dates_info['fin'], f'%{preparateur_nom}%'))
    
    etiquettes_planifiees = cur.fetchall()
    
    # 5. Calculer les minutes occupées par les étiquettes
    minutes_occupees_par_jour = {}
    total_minutes_occupees = 0
    etiquettes_details = []
    
    for date_jour, heure_debut, heure_fin, preparateurs, type_activite, description in etiquettes_planifiees:
        # Vérifier que le préparateur est bien dans la liste (éviter les faux positifs)
        preparateurs_list = [p.strip() for p in preparateurs.split(',')]
        if preparateur_nom not in preparateurs_list:
            continue
        
        # Déterminer le jour de la semaine
        jour_semaine = None
        for jour, date in dates_semaine.items():
            if date.date() == date_jour:
                jour_semaine = jour
                break
        
        if not jour_semaine or jour_semaine not in horaires_par_jour:
            continue  # Pas d'horaires définis pour ce jour
        
        # Convertir en minutes
        debut_etiquette = heure_debut.hour * 60 + heure_debut.minute
        fin_etiquette = heure_fin.hour * 60 + heure_fin.minute
        
        # Calculer l'intersection avec les horaires de travail
        minutes_occupees_jour = 0
        
        for horaire in horaires_par_jour[jour_semaine]:
            # Calculer l'intersection entre l'étiquette et l'horaire de travail
            debut_intersection = max(debut_etiquette, horaire['debut'])
            fin_intersection = min(fin_etiquette, horaire['fin'])
            
            if debut_intersection < fin_intersection:
                minutes_occupees_jour += fin_intersection - debut_intersection
        
        if jour_semaine not in minutes_occupees_par_jour:
            minutes_occupees_par_jour[jour_semaine] = 0
        minutes_occupees_par_jour[jour_semaine] += minutes_occupees_jour
        total_minutes_occupees += minutes_occupees_jour
        
        # Détails pour debug
        etiquettes_details.append({
            "type_activite": type_activite,
            "description": description,
            "date_jour": str(date_jour),
            "jour_semaine": jour_semaine,
            "heure_debut": str(heure_debut),
            "heure_fin": str(heure_fin),
            "duree_etiquette_minutes": fin_etiquette - debut_etiquette,
            "duree_intersection_minutes": minutes_occupees_jour
        })
    
    # 6. Calculer la disponibilité finale
    disponibilite_minutes = total_minutes_horaires - total_minutes_occupees
    disponibilite_heures = round(disponibilite_minutes / 60, 2)
    
    # 7. Détail par jour
    detail_par_jour = {}
    for jour, horaires in horaires_par_jour.items():
        total_jour = sum(h['duree'] for h in horaires)
        occupe_jour = minutes_occupees_par_jour.get(jour, 0)
        detail_par_jour[jour] = {
            'horaires_minutes': total_jour,
            'occupees_minutes': occupe_jour,
            'disponibles_minutes': total_jour - occupe_jour,
            'disponibles_heures': round((total_jour - occupe_jour) / 60, 2),
            'creneaux_horaires': [f"{h['debut']//60:02d}:{h['debut']%60:02d}-{h['fin']//60:02d}:{h['fin']%60:02d}" for h in horaires]
        }
    
    return {
        "preparateur": preparateur_nom,
        "semaine": semaine,
        "periode": f"Du {dates_info['debut']} au {dates_info['fin']}",
        "disponibilite_minutes": disponibilite_minutes,
        "disponibilite_heures": disponibilite_heures,
        "total_horaires_minutes": total_minutes_horaires,
        "total_horaires_heures": round(total_minutes_horaires / 60, 2),
        "total_occupees_minutes": total_minutes_occupees,
        "total_occupees_heures": round(total_minutes_occupees / 60, 2),
        "detail_par_jour": detail_par_jour,
        "nb_etiquettes_planifiees": len(etiquettes_planifiees),
        "etiquettes_details": etiquettes_details
    }

# ========================================================================
# ROUTES UTILITAIRES
# ========================================================================

@router.get("/semaine-courante")
def get_semaine_courante():
    """Obtenir la semaine courante au format standard"""
    current_week = semaine_courante()
    return {
        "semaine": current_week,
        "format": "YYYY-WXX (Standard ISO)",
        "dates": dates_de_semaine(current_week)
    }

@router.get("/semaines-disponibles")
def get_semaines_disponibles():
    """Lister les semaines avec des données de planification"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Récupérer les semaines avec des planifications
        cur.execute("""
            SELECT DISTINCT 
                EXTRACT(YEAR FROM p.date_jour) as annee,
                EXTRACT(WEEK FROM p.date_jour) as semaine_num,
                COUNT(p.id) as nb_planifications
            FROM planifications_etiquettes p
            GROUP BY 
                EXTRACT(YEAR FROM p.date_jour),
                EXTRACT(WEEK FROM p.date_jour)
            ORDER BY annee DESC, semaine_num DESC
            LIMIT 20
        """)
        
        semaines = []
        for row in cur.fetchall():
            annee, semaine_num, nb_planifications = row
            semaine_format = f"{int(annee)}-W{int(semaine_num):02d}"
            try:
                dates_info = dates_de_semaine(semaine_format)
                semaines.append({
                    "semaine": semaine_format,
                    "annee": int(annee),
                    "numero": int(semaine_num),
                    "debut": str(dates_info['debut']),
                    "fin": str(dates_info['fin']),
                    "nb_planifications": nb_planifications
                })
            except ValueError:
                # Ignorer les semaines avec un format invalide
                continue
        
        return {
            "semaines_disponibles": semaines,
            "semaine_courante": semaine_courante(),
            "total_semaines": len(semaines)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des semaines: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

# ========================================================================
# ROUTES DE CALCUL DES DISPONIBILITÉS (GET - LECTURE SEULE)
# ========================================================================

@router.get("/disponibilites-calculees/{preparateur_nom}")
def get_disponibilites_calculees_preparateur(preparateur_nom: str, semaine: Optional[str] = None):
    """
    GET : Calculer et retourner les disponibilités d'un préparateur 
    (calcul à la volée, pas de sauvegarde)
    """
    conn = None
    try:
        conn = get_db_connection()
        
        # Si pas de semaine spécifiée, prendre la semaine courante
        if not semaine:
            semaine = semaine_courante()
        
        # Vérifier le format de la semaine
        if not valider_format_semaine(semaine):
            raise HTTPException(status_code=400, detail="Format de semaine invalide. Utilisez YYYY-WXX (ex: 2025-W35)")
        
        # Utiliser la fonction de calcul pure
        resultat = calculer_disponibilites_preparateur(preparateur_nom, semaine, conn)
        
        return {
            "status": "✅ Disponibilités calculées",
            "calcul_type": "temps_reel",
            "timestamp": datetime.now().isoformat(),
            **resultat
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul des disponibilités: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

@router.get("/disponibilites-calculees")
def get_disponibilites_calculees_tous_preparateurs(semaine: Optional[str] = None):
    """GET : Calculer les disponibilités pour tous les préparateurs"""
    conn = None
    try:
        conn = get_db_connection()
        
        # Si pas de semaine spécifiée, prendre la semaine courante
        if not semaine:
            semaine = semaine_courante()
        
        if not valider_format_semaine(semaine):
            raise HTTPException(status_code=400, detail="Format de semaine invalide. Utilisez YYYY-WXX (ex: 2025-W35)")

        # Récupérer tous les préparateurs ayant des horaires
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT preparateur_nom 
            FROM horaires_preparateurs 
            ORDER BY preparateur_nom
        """)
        
        preparateurs = [row[0] for row in cur.fetchall()]
        
        if not preparateurs:
            return {
                "status": "ℹ️ Aucun préparateur trouvé",
                "semaine": semaine,
                "preparateurs": {},
                "message": "Aucun préparateur avec horaires définis"
            }
        
        # Calculer pour chaque préparateur
        resultats_preparateurs = {}
        total_disponibilites = 0
        total_horaires = 0
        total_occupees = 0
        
        for preparateur in preparateurs:
            try:
                resultat = calculer_disponibilites_preparateur(preparateur, semaine, conn)
                resultats_preparateurs[preparateur] = resultat
                total_disponibilites += resultat['disponibilite_minutes']
                total_horaires += resultat['total_horaires_minutes']
                total_occupees += resultat['total_occupees_minutes']
            except Exception as e:
                resultats_preparateurs[preparateur] = {
                    "error": str(e),
                    "disponibilite_minutes": 0,
                    "disponibilite_heures": 0
                }
        
        return {
            "status": "✅ Disponibilités calculées pour tous",
            "calcul_type": "temps_reel",
            "timestamp": datetime.now().isoformat(),
            "semaine": semaine,
            "statistiques_globales": {
                "total_disponibilites_minutes": total_disponibilites,
                "total_disponibilites_heures": round(total_disponibilites / 60, 2),
                "total_horaires_minutes": total_horaires,
                "total_horaires_heures": round(total_horaires / 60, 2),
                "total_occupees_minutes": total_occupees,
                "total_occupees_heures": round(total_occupees / 60, 2),
                "taux_occupation_pourcentage": round((total_occupees / total_horaires * 100), 2) if total_horaires > 0 else 0
            },
            "preparateurs": resultats_preparateurs,
            "nb_preparateurs": len(preparateurs)
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul global: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

# ========================================================================
# ROUTES DE MIGRATION DES ANCIENS FORMATS
# ========================================================================

@router.post("/disponibilites/migration-format-semaines")
def migrer_format_semaines():
    """POST : Migrer les anciennes semaines vers le nouveau format standard"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Récupérer les anciennes données avec format bizarre
        cur.execute("""
            SELECT preparateur_nom, semaine, minutes, "updatedAt"
            FROM disponibilites
            WHERE semaine LIKE '%-%' AND semaine NOT LIKE '____-__'
            ORDER BY semaine
        """)
        
        anciennes_donnees = cur.fetchall()
        
        if not anciennes_donnees:
            return {
                "status": "ℹ️ Aucune donnée à migrer",
                "message": "Toutes les semaines sont déjà au format standard"
            }
        
        migrations = []
        
        for preparateur_nom, ancienne_semaine, minutes, updated_at in anciennes_donnees:
            try:
                # Essayer d'extraire l'année et la semaine du format bizarre
                # Ex: "2025-W36-1" → "2025-36"
                if "W" in ancienne_semaine:
                    parts = ancienne_semaine.split("-")
                    if len(parts) >= 2:
                        annee = parts[0]
                        semaine_num = parts[1].replace("W", "")
                        nouvelle_semaine = f"{annee}-{semaine_num.zfill(2)}"
                        
                        # Supprimer l'ancienne entrée
                        cur.execute("""
                            DELETE FROM disponibilites 
                            WHERE preparateur_nom = %s AND semaine = %s
                        """, (preparateur_nom, ancienne_semaine))
                        
                        # Insérer avec le nouveau format (UPSERT)
                        cur.execute("""
                            INSERT INTO disponibilites (preparateur_nom, semaine, minutes, "updatedAt")
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (preparateur_nom, semaine) 
                            DO UPDATE SET 
                                minutes = EXCLUDED.minutes,
                                "updatedAt" = EXCLUDED."updatedAt"
                        """, (preparateur_nom, nouvelle_semaine, minutes, updated_at))
                        
                        migrations.append({
                            "preparateur": preparateur_nom,
                            "ancien_format": ancienne_semaine,
                            "nouveau_format": nouvelle_semaine,
                            "minutes": minutes,
                            "status": "✅ Migré"
                        })
                        
            except Exception as e:
                migrations.append({
                    "preparateur": preparateur_nom,
                    "ancien_format": ancienne_semaine,
                    "status": "❌ Erreur",
                    "error": str(e)
                })
        
        conn.commit()
        
        return {
            "status": "✅ Migration terminée",
            "nb_total": len(anciennes_donnees),
            "nb_succes": sum(1 for m in migrations if m.get("status") == "✅ Migré"),
            "nb_erreurs": sum(1 for m in migrations if "error" in m),
            "migrations": migrations
        }
        
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la migration: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

# ========================================================================
# ROUTES DE SAUVEGARDE DES DISPONIBILITÉS
# ========================================================================

@router.post("/disponibilites/recalculer")
def recalculer_et_sauvegarder_disponibilites(
    semaine: Optional[str] = None, 
    preparateurs: Optional[List[str]] = None
):
    """POST : Recalculer les disponibilités avec le nouveau format standard et les sauvegarder"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if not semaine:
            semaine = semaine_courante()
        
        if not valider_format_semaine(semaine):
            raise HTTPException(status_code=400, detail="Format de semaine invalide. Utilisez YYYY-WXX (ex: 2025-W35)")
        
        # Vérifier/créer la table disponibilites si nécessaire
        cur.execute("""
            CREATE TABLE IF NOT EXISTS disponibilites (
                id SERIAL PRIMARY KEY,
                preparateur_nom VARCHAR(255) NOT NULL,
                semaine VARCHAR(10) NOT NULL,
                minutes INTEGER NOT NULL DEFAULT 0,
                "updatedAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                
                UNIQUE(preparateur_nom, semaine)
            )
        """)
        
        # Index pour les performances
        cur.execute("CREATE INDEX IF NOT EXISTS idx_disponibilites_semaine ON disponibilites (semaine)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_disponibilites_preparateur ON disponibilites (preparateur_nom)")
        
        if not preparateurs:
            cur.execute("SELECT DISTINCT preparateur_nom FROM horaires_preparateurs")
            preparateurs = [row[0] for row in cur.fetchall()]
        
        resultats_sauvegarde = []
        
        for preparateur_nom in preparateurs:
            try:
                resultat_calcul = calculer_disponibilites_preparateur(preparateur_nom, semaine, conn)
                
                # Sauvegarder avec le nouveau format
                cur.execute("""
                    INSERT INTO disponibilites (preparateur_nom, semaine, minutes, "updatedAt")
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (preparateur_nom, semaine) 
                    DO UPDATE SET 
                        minutes = EXCLUDED.minutes,
                        "updatedAt" = EXCLUDED."updatedAt"
                """, (
                    preparateur_nom,
                    semaine,
                    resultat_calcul['disponibilite_minutes'],
                    datetime.now().isoformat()
                ))
                
                resultats_sauvegarde.append({
                    "preparateur": preparateur_nom,
                    "disponibilite_minutes": resultat_calcul['disponibilite_minutes'],
                    "disponibilite_heures": resultat_calcul['disponibilite_heures'],
                    "total_horaires_heures": resultat_calcul['total_horaires_heures'],
                    "total_occupees_heures": resultat_calcul['total_occupees_heures'],
                    "status": "✅ Sauvegardé"
                })
                
            except Exception as e:
                resultats_sauvegarde.append({
                    "preparateur": preparateur_nom,
                    "status": "❌ Erreur",
                    "error": str(e)
                })
        
        conn.commit()
        
        # Statistiques finales
        nb_succes = sum(1 for r in resultats_sauvegarde if r.get("status") == "✅ Sauvegardé")
        total_dispo_minutes = sum(r.get('disponibilite_minutes', 0) for r in resultats_sauvegarde if 'disponibilite_minutes' in r)
        
        return {
            "status": "✅ Disponibilités recalculées et sauvegardées",
            "format_semaine": "Standard YYYY-WXX",
            "semaine": semaine,
            "timestamp": datetime.now().isoformat(),
            "nb_preparateurs": len(preparateurs),
            "nb_succes": nb_succes,
            "nb_erreurs": sum(1 for r in resultats_sauvegarde if "error" in r),
            "total_disponibilites_minutes": total_dispo_minutes,
            "total_disponibilites_heures": round(total_dispo_minutes / 60, 2),
            "resultats": resultats_sauvegarde
        }
        
    except ValueError as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de la sauvegarde: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

# ========================================================================
# ROUTES DE COMPARAISON ANCIEN/NOUVEAU SYSTÈME
# ========================================================================

@router.get("/disponibilites/comparaison/{semaine}")
def comparer_anciennes_nouvelles_disponibilites(semaine: str):
    """
    GET : Comparer les anciennes disponibilités (importées) avec les nouvelles (calculées)
    Utile pour la migration et validation
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if not valider_format_semaine(semaine):
            raise HTTPException(status_code=400, detail="Format de semaine invalide. Utilisez YYYY-WXX (ex: 2025-W35)")
        
        # Récupérer les anciennes disponibilités sauvegardées
        cur.execute("""
            SELECT preparateur_nom, minutes 
            FROM disponibilites 
            WHERE semaine = %s
        """, (semaine,))
        
        anciennes_dispo = {row[0]: row[1] for row in cur.fetchall()}
        
        # Calculer les nouvelles disponibilités
        cur.execute("SELECT DISTINCT preparateur_nom FROM horaires_preparateurs")
        preparateurs = [row[0] for row in cur.fetchall()]
        
        comparaisons = {}
        
        for preparateur in preparateurs:
            try:
                nouvelles = calculer_disponibilites_preparateur(preparateur, semaine, conn)
                anciennes_minutes = anciennes_dispo.get(preparateur, 0)
                nouvelles_minutes = nouvelles['disponibilite_minutes']
                
                comparaisons[preparateur] = {
                    "anciennes_minutes": anciennes_minutes,
                    "nouvelles_minutes": nouvelles_minutes,
                    "difference_minutes": nouvelles_minutes - anciennes_minutes,
                    "difference_heures": round((nouvelles_minutes - anciennes_minutes) / 60, 2),
                    "identique": anciennes_minutes == nouvelles_minutes,
                    "anciennes_heures": round(anciennes_minutes / 60, 2),
                    "nouvelles_heures": nouvelles['disponibilite_heures'],
                    "total_horaires_heures": nouvelles['total_horaires_heures'],
                    "total_occupees_heures": nouvelles['total_occupees_heures'],
                    "nb_etiquettes": nouvelles['nb_etiquettes_planifiees']
                }
            except Exception as e:
                comparaisons[preparateur] = {
                    "error": str(e),
                    "anciennes_minutes": anciennes_dispo.get(preparateur, 0),
                    "nouvelles_minutes": 0,
                    "identique": False
                }
        
        # Statistiques globales
        total_anciennes = sum(c.get('anciennes_minutes', 0) for c in comparaisons.values())
        total_nouvelles = sum(c.get('nouvelles_minutes', 0) for c in comparaisons.values())
        
        return {
            "semaine": semaine,
            "timestamp": datetime.now().isoformat(),
            "comparaisons": comparaisons,
            "statistiques": {
                "nb_preparateurs": len(comparaisons),
                "nb_identiques": sum(1 for c in comparaisons.values() if c.get('identique', False)),
                "nb_differences": sum(1 for c in comparaisons.values() if not c.get('identique', True)),
                "nb_erreurs": sum(1 for c in comparaisons.values() if 'error' in c),
                "total_anciennes_minutes": total_anciennes,
                "total_nouvelles_minutes": total_nouvelles,
                "total_anciennes_heures": round(total_anciennes / 60, 2),
                "total_nouvelles_heures": round(total_nouvelles / 60, 2),
                "difference_globale_minutes": total_nouvelles - total_anciennes,
                "difference_globale_heures": round((total_nouvelles - total_anciennes) / 60, 2)
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la comparaison: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

# ========================================================================
# ROUTES DE LECTURE DES DISPONIBILITÉS SAUVEGARDÉES
# ========================================================================

@router.get("/disponibilites-sauvegardees/{semaine}")
def get_disponibilites_sauvegardees(semaine: str):
    """GET : Récupérer les disponibilités sauvegardées pour une semaine"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if not valider_format_semaine(semaine):
            raise HTTPException(status_code=400, detail="Format de semaine invalide. Utilisez YYYY-WXX (ex: 2025-W35)")
        
        cur.execute("""
            SELECT preparateur_nom, minutes, "updatedAt", created_at
            FROM disponibilites 
            WHERE semaine = %s
            ORDER BY preparateur_nom
        """, (semaine,))
        
        results = cur.fetchall()
        
        if not results:
            return {
                "semaine": semaine,
                "disponibilites": {},
                "message": "Aucune disponibilité sauvegardée pour cette semaine"
            }
        
        disponibilites = {}
        total_minutes = 0
        
        for row in results:
            preparateur_nom, minutes, updated_at, created_at = row
            disponibilites[preparateur_nom] = {
                "minutes": minutes,
                "heures": round(minutes / 60, 2),
                "updated_at": updated_at.isoformat() if updated_at else None,
                "created_at": created_at.isoformat() if created_at else None
            }
            total_minutes += minutes
        
        return {
            "semaine": semaine,
            "disponibilites": disponibilites,
            "statistiques": {
                "nb_preparateurs": len(disponibilites),
                "total_minutes": total_minutes,
                "total_heures": round(total_minutes / 60, 2)
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

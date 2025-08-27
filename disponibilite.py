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
    """Valider le format de semaine YYYY-WXX (standard ISO 8601)"""
    if not re.match(r'^\d{4}-W\d{2}$', semaine):
        return False
    
    # Validation supplémentaire : vérifier que la semaine existe
    try:
        year_str, week_part = semaine.split('-')
        year = int(year_str)
        week_num = int(week_part[1:])
        
        # Une année a entre 52 et 53 semaines ISO
        if not (1 <= week_num <= 53):
            return False
            
        # ✅ MÉTHODE SIMPLE : Essayer de calculer la date et voir si ça marche
        try:
            jan4 = datetime(year, 1, 4)  # Le 4 janvier est toujours dans la semaine 1 ISO
            week_start = jan4 + timedelta(days=(week_num - 1) * 7 - jan4.weekday())
            
            # Vérifier que la semaine calculée correspond bien au numéro demandé
            calculated_year, calculated_week, _ = week_start.isocalendar()
            return calculated_year == year and calculated_week == week_num
            
        except ValueError:
            return False
        
    except (ValueError, IndexError):
        return False

def semaine_courante() -> str:
    """Obtenir la semaine courante au format YYYY-WXX (standard ISO 8601)"""
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
    
    # ✅ MÉTHODE PLUS ROBUSTE POUR ISO 8601
    try:
        # Utiliser strptime avec le format ISO exact
        date_string = f"{year}-W{week_num:02d}-1"  # Lundi de la semaine
        week_start = datetime.strptime(date_string, "%Y-W%W-%w")
        
        # Fallback avec la méthode actuelle si strptime échoue
        if week_start.isocalendar()[1] != week_num:
            # Méthode alternative plus précise
            jan4 = datetime(year, 1, 4)  # Le 4 janvier est toujours dans la semaine 1 ISO
            week_start = jan4 + timedelta(days=(week_num - 1) * 7 - jan4.weekday())
        
    except ValueError:
        # Méthode de fallback
        try:
            jan4 = datetime(year, 1, 4)
            week_start = jan4 + timedelta(days=(week_num - 1) * 7 - jan4.weekday())
        except ValueError as e:
            raise ValueError(f"Impossible de calculer les dates pour la semaine {semaine}: {e}")
    
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
        semaine: Semaine au format YYYY-WXX
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
# ROUTES DE SAUVEGARDE DES DISPONIBILITÉS
# ========================================================================

@router.post("/disponibilites/recalculer")
def recalculer_et_sauvegarder_disponibilites(
    semaine: Optional[str] = None, 
    semaines: Optional[List[str]] = None,  # ✅ NOUVEAU : accepter plusieurs semaines
    preparateurs: Optional[List[str]] = None
):
    """POST : Recalculer les disponibilités - accepte une seule semaine OU plusieurs semaines"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ✅ DÉTERMINER LES SEMAINES À TRAITER
        semaines_a_traiter = []
        
        if semaines:
            # Mode multi-semaines
            semaines_a_traiter = semaines
        elif semaine:
            # Mode semaine unique
            semaines_a_traiter = [semaine]
        else:
            # Mode par défaut : semaine courante
            semaines_a_traiter = [semaine_courante()]
        
        # ✅ VALIDATION DES FORMATS
        for sem in semaines_a_traiter:
            if not valider_format_semaine(sem):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Format de semaine invalide: {sem}. Utilisez YYYY-WXX (ex: 2025-W35)"
                )
        
        # ✅ VÉRIFICATION DES TABLES REQUISES
        required_tables = ['horaires_preparateurs', 'planifications_etiquettes', 'disponibilites']
        cur.execute(f"""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = ANY(%s)
        """, (required_tables,))
        
        existing_tables = [row[0] for row in cur.fetchall()]
        missing_tables = [t for t in required_tables if t not in existing_tables]
        
        if missing_tables:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Tables de base de données manquantes",
                    "missing_tables": missing_tables,
                    "solution": "Utilisez l'endpoint POST /admin/create-all-tables pour créer les tables"
                }
            )
        
        # ✅ OBTENIR LES PRÉPARATEURS
        if not preparateurs:
            cur.execute("SELECT DISTINCT preparateur_nom FROM horaires_preparateurs")
            preparateurs = [row[0] for row in cur.fetchall()]
        
        if not preparateurs:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Aucun préparateur trouvé",
                    "message": "Aucun préparateur n'a d'horaires définis"
                }
            )
        
        # ✅ TRAITEMENT EN BATCH : TOUTES LES SEMAINES D'UN COUP
        print(f"🔄 Traitement en batch: {len(semaines_a_traiter)} semaines × {len(preparateurs)} préparateurs")
        
        resultats_par_semaine = {}
        batch_upserts = []  # Pour faire tous les UPSERT en une fois
        timestamp_iso = datetime.now().isoformat()
        
        # ✅ CALCULER TOUTES LES COMBINAISONS
        for semaine_courante in semaines_a_traiter:
            resultats_sauvegarde = []
            
            for preparateur_nom in preparateurs:
                try:
                    resultat_calcul = calculer_disponibilites_preparateur(preparateur_nom, semaine_courante, conn)
                    
                    # Préparer les données pour le batch UPSERT
                    batch_upserts.append((
                        preparateur_nom,
                        semaine_courante,
                        resultat_calcul['disponibilite_minutes'],
                        timestamp_iso
                    ))
                    
                    resultats_sauvegarde.append({
                        "preparateur": preparateur_nom,
                        "semaine": semaine_courante,
                        "disponibilite_minutes": resultat_calcul['disponibilite_minutes'],
                        "disponibilite_heures": resultat_calcul['disponibilite_heures'],
                        "total_horaires_heures": resultat_calcul['total_horaires_heures'],
                        "total_occupees_heures": resultat_calcul['total_occupees_heures'],
                        "status": "✅ Calculé"
                    })
                    
                except Exception as e:
                    resultats_sauvegarde.append({
                        "preparateur": preparateur_nom,
                        "semaine": semaine_courante,
                        "status": "❌ Erreur",
                        "error": str(e)
                    })
            
            resultats_par_semaine[semaine_courante] = {
                "semaine": semaine_courante,
                "resultats": resultats_sauvegarde,
                "nb_preparateurs": len(preparateurs),
                "nb_reussites": len([r for r in resultats_sauvegarde if r.get("status") == "✅ Calculé"])
            }
        
        # ✅ SAUVEGARDER TOUT EN UNE SEULE TRANSACTION
        if batch_upserts:
            print(f"💾 Sauvegarde en batch de {len(batch_upserts)} disponibilités...")
            
            cur.executemany("""
                INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (preparateur_nom, semaine) 
                DO UPDATE SET 
                    minutes = EXCLUDED.minutes,
                    updatedAt = EXCLUDED.updatedAt
            """, batch_upserts)
            
            # Marquer comme sauvegardé
            for semaine_key, semaine_data in resultats_par_semaine.items():
                for resultat in semaine_data["resultats"]:
                    if resultat.get("status") == "✅ Calculé":
                        resultat["status"] = "✅ Sauvegardé"
        
        conn.commit()
        
        # ✅ STATISTIQUES FINALES
        total_calculs = sum(len(s["resultats"]) for s in resultats_par_semaine.values())
        total_reussites = sum(s["nb_reussites"] for s in resultats_par_semaine.values())
        
        print(f"✅ Batch terminé: {total_reussites}/{total_calculs} calculs réussis sur {len(semaines_a_traiter)} semaines")
        
        # ✅ RETOUR ADAPTATIF selon le mode
        if len(semaines_a_traiter) == 1:
            # Mode semaine unique : format de retour compatible
            semaine_unique = list(resultats_par_semaine.values())[0]
            return {
                "status": "✅ Disponibilités recalculées et sauvegardées",
                "semaine": semaine_unique["semaine"],
                "resultats": semaine_unique["resultats"],
                "summary": f"{semaine_unique['nb_reussites']}/{semaine_unique['nb_preparateurs']} préparateurs traités"
            }
        else:
            # Mode multi-semaines : format détaillé
            return {
                "status": "✅ Disponibilités recalculées en batch",
                "mode": "multi_semaines",
                "nb_semaines": len(semaines_a_traiter),
                "nb_calculs_total": total_calculs,
                "nb_reussites_total": total_reussites,
                "resultats_par_semaine": resultats_par_semaine,
                "summary": f"{total_reussites}/{total_calculs} calculs réussis sur {len(semaines_a_traiter)} semaines"
            }
        
    except HTTPException:
        # Re-lever les HTTPException sans modification
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Erreur dans recalculer_et_sauvegarder_disponibilites: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")
    finally:
        if conn:
            close_db_connection(conn)

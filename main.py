"""
Module de calcul des disponibilités basé sur la grille semaine
"""

from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Tuple
import logging

# Configuration des logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DisponibiliteCalculator:
    """
    Classe pour calculer automatiquement les disponibilités des préparateurs
    basé sur leurs horaires et les étiquettes planifiées dans la grille semaine
    """
    
    def __init__(self, db_connection):
        """
        Initialise le calculateur avec une connexion à la base de données
        
        Args:
            db_connection: Connexion active à la base PostgreSQL
        """
        self.db = db_connection
    
    def calculate_disponibilites_semaine(self, semaine_id: str, preparateur_nom: Optional[str] = None) -> Dict[str, Dict[str, int]]:
        """
        Calcule les disponibilités pour une semaine donnée
        
        Args:
            semaine_id: Identifiant de la semaine (format: "2025-W34")
            preparateur_nom: Nom du préparateur spécifique (optionnel, sinon tous)
            
        Returns:
            Dict: {preparateur_nom: {semaine: minutes_disponibles}}
        """
        try:
            cur = self.db.cursor()
            
            # Déterminer les dates de début et fin de la semaine
            dates_semaine = self._get_dates_from_semaine_id(semaine_id)
            if not dates_semaine:
                logger.error(f"Impossible de déterminer les dates pour la semaine {semaine_id}")
                return {}
                
            date_debut, date_fin = dates_semaine
            logger.info(f"Calcul des disponibilités pour la semaine {semaine_id} ({date_debut} au {date_fin})")
            
            # Construire la clause WHERE pour le préparateur
            where_preparateur = ""
            params_preparateur = []
            if preparateur_nom:
                where_preparateur = "AND hp.preparateur_nom = %s"
                params_preparateur = [preparateur_nom]
            
            # Récupérer les horaires de tous les préparateurs pour cette semaine
            horaires_query = f"""
                SELECT hp.preparateur_nom, hp.jour_semaine, hp.heure_debut, hp.heure_fin
                FROM horaires_preparateurs hp
                WHERE 1=1 {where_preparateur}
                ORDER BY hp.preparateur_nom, hp.jour_semaine
            """
            
            cur.execute(horaires_query, params_preparateur)
            horaires_preparateurs = cur.fetchall()
            
            # Organiser les horaires par préparateur
            horaires_by_preparateur = {}
            for row in horaires_preparateurs:
                prep_nom, jour, heure_debut, heure_fin = row
                if prep_nom not in horaires_by_preparateur:
                    horaires_by_preparateur[prep_nom] = {}
                horaires_by_preparateur[prep_nom][jour] = (heure_debut, heure_fin)
            
            # Calculer les disponibilités pour chaque préparateur
            disponibilites_result = {}
            
            for prep_nom in horaires_by_preparateur:
                minutes_totales = self._calculate_horaires_totaux_semaine(
                    horaires_by_preparateur[prep_nom], 
                    date_debut, 
                    date_fin
                )
                
                minutes_occupees = self._calculate_minutes_occupees_semaine(
                    prep_nom, 
                    date_debut, 
                    date_fin
                )
                
                minutes_disponibles = max(0, minutes_totales - minutes_occupees)
                
                disponibilites_result[prep_nom] = {
                    semaine_id: minutes_disponibles
                }
                
                logger.info(f"Préparateur {prep_nom}: {minutes_totales}min totales - {minutes_occupees}min occupées = {minutes_disponibles}min disponibles")
            
            return disponibilites_result
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul des disponibilités: {str(e)}")
            raise e
    
    def update_preparateur_disponibilite(self, preparateur_nom: str, semaine_id: str) -> bool:
        """
        Met à jour la disponibilité d'un préparateur spécifique pour une semaine
        
        Args:
            preparateur_nom: Nom du préparateur
            semaine_id: Identifiant de la semaine
            
        Returns:
            bool: True si la mise à jour a réussi
        """
        try:
            # Calculer la nouvelle disponibilité
            nouvelles_dispos = self.calculate_disponibilites_semaine(semaine_id, preparateur_nom)
            
            if preparateur_nom not in nouvelles_dispos:
                logger.warning(f"Aucune donnée de disponibilité calculée pour {preparateur_nom}")
                return False
            
            minutes_disponibles = nouvelles_dispos[preparateur_nom][semaine_id]
            
            # Mettre à jour en base
            cur = self.db.cursor()
            
            # Vérifier si une entrée existe déjà
            cur.execute("""
                SELECT id, minutes FROM disponibilites 
                WHERE preparateur_nom = %s AND semaine = %s
            """, (preparateur_nom, semaine_id))
            
            existing = cur.fetchone()
            current_time = datetime.now().isoformat()
            
            if existing:
                # Mise à jour uniquement si les minutes ont changé
                existing_id, existing_minutes = existing
                if existing_minutes != minutes_disponibles:
                    cur.execute("""
                        UPDATE disponibilites 
                        SET minutes = %s, updatedAt = %s, created_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (minutes_disponibles, current_time, existing_id))
                    logger.info(f"Disponibilité mise à jour pour {preparateur_nom}: {existing_minutes}min → {minutes_disponibles}min")
                else:
                    logger.info(f"Aucun changement pour {preparateur_nom}: {minutes_disponibles}min")
            else:
                # Nouvelle entrée
                cur.execute("""
                    INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt)
                    VALUES (%s, %s, %s, %s)
                """, (preparateur_nom, semaine_id, minutes_disponibles, current_time))
                logger.info(f"Nouvelle disponibilité créée pour {preparateur_nom}: {minutes_disponibles}min")
            
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la disponibilité: {str(e)}")
            self.db.rollback()
            return False
    
    def update_all_disponibilites_semaine(self, semaine_id: str) -> Dict[str, bool]:
        """
        Met à jour les disponibilités de tous les préparateurs pour une semaine
        
        Args:
            semaine_id: Identifiant de la semaine
            
        Returns:
            Dict: {preparateur_nom: success_status}
        """
        try:
            # Calculer toutes les disponibilités
            disponibilites = self.calculate_disponibilites_semaine(semaine_id)
            
            results = {}
            for preparateur_nom in disponibilites:
                success = self.update_preparateur_disponibilite(preparateur_nom, semaine_id)
                results[preparateur_nom] = success
            
            logger.info(f"Mise à jour des disponibilités terminée pour la semaine {semaine_id}: {len(results)} préparateurs traités")
            return results
            
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour globale: {str(e)}")
            return {}
    
    def _get_dates_from_semaine_id(self, semaine_id: str) -> Optional[Tuple[str, str]]:
        """
        Convertit un ID de semaine en dates de début et fin
        
        Args:
            semaine_id: Format "2025-W34" ou "2025-W34-1"
            
        Returns:
            Tuple[str, str]: (date_debut, date_fin) au format YYYY-MM-DD
        """
        try:
            # Parser le format "2025-W34" ou "2025-W34-1"
            if '-1' in semaine_id:
                # Format avec suffixe -1
                year_week_part = semaine_id.replace('-1', '')
            else:
                year_week_part = semaine_id
                
            year_str, week_str = year_week_part.split('-W')
            year = int(year_str)
            week = int(week_str)
            
            # Calculer le premier jour de la semaine (lundi)
            first_day_of_year = datetime(year, 1, 1)
            first_monday = first_day_of_year + timedelta(days=(7 - first_day_of_year.weekday()))
            
            # Calculer le début de la semaine demandée
            week_start = first_monday + timedelta(weeks=week - 1)
            week_end = week_start + timedelta(days=6)
            
            return week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')
            
        except (ValueError, IndexError) as e:
            logger.error(f"Format de semaine invalide {semaine_id}: {str(e)}")
            return None
    
    def _calculate_horaires_totaux_semaine(self, horaires_preparateur: Dict[str, Tuple[time, time]], 
                                          date_debut: str, date_fin: str) -> int:
        """
        Calcule le nombre total de minutes de travail pour un préparateur sur une semaine
        
        Args:
            horaires_preparateur: Dict des horaires par jour de la semaine
            date_debut: Date de début de semaine
            date_fin: Date de fin de semaine
            
        Returns:
            int: Nombre total de minutes
        """
        jours_semaine = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
        total_minutes = 0
        
        for jour in jours_semaine:
            if jour in horaires_preparateur:
                heure_debut, heure_fin = horaires_preparateur[jour]
                
                # Convertir en minutes depuis minuit
                debut_minutes = heure_debut.hour * 60 + heure_debut.minute
                fin_minutes = heure_fin.hour * 60 + heure_fin.minute
                
                # Calculer la durée de travail pour ce jour
                duree_jour = fin_minutes - debut_minutes
                total_minutes += duree_jour
        
        return total_minutes
    
    def _calculate_minutes_occupees_semaine(self, preparateur_nom: str, 
                                           date_debut: str, date_fin: str) -> int:
        """
        Calcule le nombre de minutes occupées par les étiquettes planifiées
        
        Args:
            preparateur_nom: Nom du préparateur
            date_debut: Date de début de semaine
            date_fin: Date de fin de semaine
            
        Returns:
            int: Nombre de minutes occupées
        """
        try:
            cur = self.db.cursor()
            
            # Récupérer toutes les planifications d'étiquettes pour ce préparateur sur la période
            cur.execute("""
                SELECT pe.date_jour, pe.heure_debut, pe.heure_fin, pe.preparateurs
                FROM planifications_etiquettes pe
                WHERE pe.date_jour BETWEEN %s AND %s
                AND pe.preparateurs LIKE %s
            """, (date_debut, date_fin, f'%{preparateur_nom}%'))
            
            planifications = cur.fetchall()
            
            total_minutes_occupees = 0
            
            for row in planifications:
                date_jour, heure_debut, heure_fin, preparateurs = row
                
                # Vérifier que le préparateur est bien dans cette planification
                # (protection contre les faux positifs du LIKE)
                preparateurs_list = [p.strip() for p in preparateurs.split(',')]
                if preparateur_nom in preparateurs_list:
                    # Calculer la durée de cette étiquette
                    debut_minutes = heure_debut.hour * 60 + heure_debut.minute
                    fin_minutes = heure_fin.hour * 60 + heure_fin.minute
                    duree_etiquette = fin_minutes - debut_minutes
                    
                    total_minutes_occupees += duree_etiquette
            
            return total_minutes_occupees
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul des minutes occupées: {str(e)}")
            return 0
    
    def recalculate_all_disponibilites(self) -> Dict[str, int]:
        """
        Recalcule toutes les disponibilités de tous les préparateurs pour toutes les semaines
        Fonction utile pour une remise à zéro complète
        
        Returns:
            Dict: Statistiques du recalcul
        """
        try:
            cur = self.db.cursor()
            
            # Récupérer toutes les combinaisons préparateur/semaine existantes
            cur.execute("""
                SELECT DISTINCT preparateur_nom, semaine 
                FROM disponibilites
                ORDER BY preparateur_nom, semaine
            """)
            
            combinations = cur.fetchall()
            
            stats = {
                'total_processed': 0,
                'successful_updates': 0,
                'errors': 0
            }
            
            for preparateur_nom, semaine in combinations:
                stats['total_processed'] += 1
                success = self.update_preparateur_disponibilite(preparateur_nom, semaine)
                if success:
                    stats['successful_updates'] += 1
                else:
                    stats['errors'] += 1
            
            logger.info(f"Recalcul global terminé: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Erreur lors du recalcul global: {str(e)}")
            return {'error': str(e)}

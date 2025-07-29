// Module des utilitaires de gestion du temps et des semaines
// Contient les constantes, calculs de semaines et fonctions de dates

const WINDOW_SIZE = 10;

/**
 * Extension de Date pour obtenir le numéro de semaine ISO
 * @returns {number} Numéro de semaine ISO
 */
Date.prototype.getWeek = function() {
  const d = new Date(Date.UTC(this.getFullYear(), this.getMonth(), this.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  return Math.ceil((((d - new Date(Date.UTC(d.getUTCFullYear(), 0, 1))) / 86400000) + 1) / 7);
};

/**
 * Calcule le nombre de semaines ISO dans une année
 * @param {number} y - Année
 * @returns {number} Nombre de semaines dans l'année
 */
function getISOWeeksInYear(y) {
  const d = new Date(Date.UTC(y, 11, 31));
  const w = d.getWeek();
  return w === 1 ? 52 : w;
}

/**
 * Obtient la date du lundi d'une semaine ISO donnée
 * @param {number} w - Numéro de semaine
 * @param {number} y - Année
 * @returns {Date} Date du lundi de la semaine
 */
function getDateOfISOWeek(w, y) {
  const d = new Date(Date.UTC(y, 0, 1 + (w - 1) * 7));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + (1 - day + (day <= 4 ? 0 : 7)));
  return d;
}

/**
 * Parse une date au format français "jj/mm/aaaa"
 * @param {string} str - Date au format "jj/mm/aaaa"
 * @returns {Date} Objet Date
 */
function parseDateFR(str) {
  const [day, month, year] = str.split('/').map(Number);
  return new Date(year, month - 1, day);
}

// Génération de la liste des semaines (2024-2028)
const weeks = [];
for (let y = 2024; y <= 2028; y++) {
  const tot = getISOWeeksInYear(y);
  for (let w = 1; w <= tot; w++) {
    const s = getDateOfISOWeek(w, y);
    const e = new Date(s);
    e.setUTCDate(s.getUTCDate() + 6);
    weeks.push({
      id: `S${w}/${y}`,
      label: `${String(s.getUTCDate()).padStart(2, '0')}/${String(s.getUTCMonth() + 1).padStart(2, '0')} - ${String(e.getUTCDate()).padStart(2, '0')}/${String(e.getUTCMonth() + 1).padStart(2, '0')}`,
      start: s,
      end: e
    });
  }
}

// Variables globales pour la navigation
let now = new Date();
let nowId = `S${now.getWeek()}/${now.getFullYear()}`;
let selectedWeek = weeks.findIndex(w => w.id === nowId);
if (selectedWeek < 0) selectedWeek = 0;

// Références aux éléments DOM (initialisées après chargement)
let navEl = null;
let gridEl = null;
let calOverlay = null;

/**
 * Initialise les références DOM
 */
function initDOMReferences() {
  navEl = document.getElementById('week-nav');
  gridEl = document.getElementById('schedule-grid');
  calOverlay = document.getElementById('calendarOverlay');
  
  // Vérification des éléments critiques
  if (!navEl) console.warn('Element week-nav non trouvé');
  if (!gridEl) console.warn('Element schedule-grid non trouvé');
  if (!calOverlay) console.warn('Element calendarOverlay non trouvé');
}

// Auto-initialisation des références DOM
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDOMReferences);
} else {
  initDOMReferences();
}

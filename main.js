// Fichier principal d'initialisation de l'application
// Contient les variables globales et la logique d'initialisation

// ========================================================================
// 📊 VARIABLES GLOBALES
// ========================================================================

// Configuration de l'API
const API_BASE_URL = 'https://api-chantiers.onrender.com'; // URL de votre API locale (à modifier pour Render)

// Données de planification
let data = {};
let preparateursMeta = {};
let chantiers = {};

// Configuration d'affichage
let visibleWeeksCount = 10;

// ========================================================================
// 🌐 FONCTIONS D'API
// ========================================================================

/**
 * Charge les données depuis l'API
 */
async function loadDataFromAPI() {
  try {
    console.log('🔄 Chargement des données depuis l\'API...');
    
    // Chargement en parallèle des 3 endpoints
    const [chantiersResponse, preparateursResponse, disponibilitesResponse] = await Promise.all([
      fetch(`${API_BASE_URL}/chantiers`),
      fetch(`${API_BASE_URL}/preparateurs`),
      fetch(`${API_BASE_URL}/disponibilites`)
    ]);

    // Vérification des réponses
    if (!chantiersResponse.ok || !preparateursResponse.ok || !disponibilitesResponse.ok) {
      throw new Error('Erreur lors du chargement des données');
    }

    // Conversion en JSON
    const [chantiersData, preparateursData, disponibilitesData] = await Promise.all([
      chantiersResponse.json(),
      preparateursResponse.json(),
      disponibilitesResponse.json()
    ]);

    // Mise à jour des variables globales
    chantiers = chantiersData;
    preparateursMeta = preparateursData;
    data = disponibilitesData;

    console.log('✅ Données chargées avec succès:', {
      chantiers: Object.keys(chantiers).length,
      preparateurs: Object.keys(preparateursMeta).length,
      disponibilites: Object.keys(data).length
    });

    return true;
  } catch (error) {
    console.error('❌ Erreur lors du chargement des données:', error);
    
    // Affichage d'un message d'erreur à l'utilisateur
    showErrorMessage('Impossible de charger les données depuis l\'API. Vérifiez que le serveur est démarré.');
    
    return false;
  }
}

/**
 * Affiche un message d'erreur à l'utilisateur
 */
function showErrorMessage(message) {
  // Créer un élément d'erreur temporaire
  const errorDiv = document.createElement('div');
  errorDiv.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: #ff4444;
    color: white;
    padding: 15px;
    border-radius: 5px;
    z-index: 9999;
    max-width: 300px;
  `;
  errorDiv.textContent = message;
  
  document.body.appendChild(errorDiv);
  
  // Supprimer après 5 secondes
  setTimeout(() => {
    if (errorDiv.parentNode) {
      errorDiv.parentNode.removeChild(errorDiv);
    }
  }, 5000);
}

// ========================================================================
// 🎛️ FONCTIONS DE CONTRÔLE
// ========================================================================

/**
 * Met à jour le nombre de semaines affichées
 * @param {string|number} val - Nouvelle valeur du slider
 */
function updateWeeksDisplay(val) {
  visibleWeeksCount = parseInt(val, 10);
  renderAll();
}

/**
 * Fonction principale de rendu
 * Rafraîchit tous les composants visuels
 */
function renderAll() { 
  // Vérification que les éléments DOM sont disponibles
  if (typeof renderNav === 'function') renderNav(); 
  if (typeof renderGrid === 'function') renderGrid(); 
}

// ========================================================================
// 🚀 INITIALISATION DE L'APPLICATION
// ========================================================================

/**
 * Initialise les événements de l'interface
 */
function initEventListeners() {
  const slider = document.getElementById('visible-weeks');
  const sliderContainer = document.querySelector('.vertical-slider-container');
  
  if (slider && sliderContainer) {
    // Fonction pour mettre à jour la valeur affichée
    const updateSliderValue = (value) => {
      sliderContainer.setAttribute('data-value', value + ' sem.');
    };
    
    // Initialiser la valeur affichée
    updateSliderValue(slider.value);
    
    slider.addEventListener('input', (e) => {
      visibleWeeksCount = parseInt(e.target.value, 10);
      updateSliderValue(e.target.value);
      renderGrid();
    });
  }

  // Gestion des boutons avec data-action
  const reloadApiBtn = document.querySelector('[data-action="reload-api"]');
  const importBtn = document.querySelector('[data-action="import"]');
  const exportBtn = document.querySelector('[data-action="export"]');
  const managePrepBtn = document.querySelector('[data-action="manage-prep"]');
  const showAddBtn = document.querySelector('[data-action="show-add-form"]');
  const addPrepBtn = document.querySelector('[data-action="add-preparateur"]');
  const hideAddBtn = document.querySelector('[data-action="hide-add-form"]');
  const closePrepBtn = document.querySelector('[data-action="close-prep-overlay"]');
  
  // Actions principales
  if (reloadApiBtn) reloadApiBtn.addEventListener('click', reloadDataFromAPI);
  if (importBtn) importBtn.addEventListener('click', triggerImport);
  if (exportBtn) exportBtn.addEventListener('click', downloadData);
  if (managePrepBtn) managePrepBtn.addEventListener('click', managePreparateurs);
  
  // Actions de gestion des préparateurs
  if (showAddBtn) showAddBtn.addEventListener('click', showAddForm);
  if (addPrepBtn) addPrepBtn.addEventListener('click', addPreparateur);
  if (hideAddBtn) hideAddBtn.addEventListener('click', hideAddForm);
  if (closePrepBtn) closePrepBtn.addEventListener('click', closePrepOverlay);

  // Gestion du formulaire d'ajout de préparateur
  const addForm = document.getElementById('addForm');
  if (addForm) {
    addForm.addEventListener('submit', (e) => {
      e.preventDefault();
      addPreparateur();
    });
  }
}

/**
 * Initialisation principale de l'application
 * Charge les données depuis l'API puis initialise l'interface
 */
async function initApp() {
  console.log('🚀 Initialisation de l\'application...');
  
  // Attendre que tous les modules soient chargés
  await new Promise(resolve => setTimeout(resolve, 100));
  
  // Charger les données depuis l'API
  const dataLoaded = await loadDataFromAPI();
  
  if (dataLoaded) {
    // Initialiser les événements et l'interface
    initEventListeners();
    renderAll();
    console.log('✅ Application initialisée avec succès');
  } else {
    // En cas d'échec, initialiser quand même l'interface avec des données vides
    console.log('⚠️ Application initialisée sans données');
    initEventListeners();
    renderAll();
  }
}

// ========================================================================
// 🎯 LANCEMENT AUTOMATIQUE
// ========================================================================

// Lancement de l'initialisation selon l'état du DOM
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

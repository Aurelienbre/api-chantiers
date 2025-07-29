// Module de filtre des ressources
// Gère le filtrage des préparateurs dans la grille de planification

// Variables globales pour le filtre
let selectedResources = new Set();
let allResources = [];

/**
 * Ouvre l'interface de filtre des ressources
 */
function openResourcesFilter() {
  const overlay = document.getElementById('resourcesFilterOverlay');
  const input = document.getElementById('resourcesFilterInput');
  const filterContent = document.querySelector('.filter-content');
  
  if (!overlay || !input || !filterContent) {
    console.error('Éléments de filtre non trouvés');
    return;
  }
  
  // Récupérer la liste de tous les préparateurs
  allResources = Object.keys(data).map(name => ({
    name: name,
    nni: preparateursMeta[name] || 'Non défini'
  }));
  
  // Positionner le modal AVANT de l'afficher pour éviter tout mouvement
  const resourcesButton = document.querySelector('.resources-filter-btn');
  if (resourcesButton) {
    const rect = resourcesButton.getBoundingClientRect();
    
    // Positionner le modal près de la cellule
    filterContent.style.top = `${rect.bottom + 10}px`;
    filterContent.style.left = `${Math.max(10, rect.left)}px`;
    
    // Ajuster si le modal sort de l'écran (calculé avant affichage)
    const modalWidth = 400; // Largeur définie dans le CSS
    const modalHeight = 500; // Estimation de la hauteur maximale
    
    if (rect.left + modalWidth > window.innerWidth) {
      filterContent.style.left = `${window.innerWidth - modalWidth - 10}px`;
    }
    if (rect.bottom + modalHeight > window.innerHeight) {
      filterContent.style.top = `${rect.top - modalHeight - 10}px`;
    }
  }
  
  // Afficher l'overlay seulement après positionnement
  overlay.style.display = 'block';
  
  // Focus et affichage des suggestions
  input.focus();
  showAllAvailableResources();
  
  // Mettre à jour l'affichage des ressources sélectionnées
  updateSelectedResourcesDisplay();
}

/**
 * Ferme l'interface de filtre des ressources
 */
function closeResourcesFilter() {
  const overlay = document.getElementById('resourcesFilterOverlay');
  const input = document.getElementById('resourcesFilterInput');
  const suggestions = document.getElementById('resourcesSuggestions');
  
  if (overlay) overlay.style.display = 'none';
  if (input) input.value = '';
  if (suggestions) suggestions.style.display = 'none';
}

/**
 * Affiche toutes les ressources disponibles (non sélectionnées)
 */
function showAllAvailableResources() {
  const suggestions = document.getElementById('resourcesSuggestions');
  if (!suggestions) return;
  
  // Filtrer les ressources non sélectionnées
  const availableResources = allResources.filter(resource => 
    !selectedResources.has(resource.name)
  );
  
  if (availableResources.length === 0) {
    suggestions.style.display = 'none';
    return;
  }
  
  // Afficher toutes les suggestions disponibles
  suggestions.innerHTML = '';
  availableResources.forEach(resource => {
    const item = document.createElement('div');
    item.className = 'suggestion-item';
    item.innerHTML = `
      <div>
        <strong>${resource.name}</strong>
        <small style="color: #64748b; display: block;">${resource.nni}</small>
      </div>
    `;
    item.onclick = () => addResourceToFilter(resource.name);
    suggestions.appendChild(item);
  });
  
  suggestions.style.display = 'block';
}

/**
 * Gère la saisie dans le champ de recherche
 */
function handleResourcesInput() {
  const input = document.getElementById('resourcesFilterInput');
  const suggestions = document.getElementById('resourcesSuggestions');
  
  if (!input || !suggestions) return;
  
  const query = input.value.toLowerCase().trim();
  
  // Si le champ est vide, afficher toutes les ressources disponibles
  if (query.length === 0) {
    showAllAvailableResources();
    return;
  }
  
  // Filtrer les ressources non sélectionnées selon la recherche
  const filtered = allResources.filter(resource => 
    !selectedResources.has(resource.name) &&
    (resource.name.toLowerCase().includes(query) || 
     resource.nni.toLowerCase().includes(query))
  );
  
  if (filtered.length === 0) {
    suggestions.style.display = 'none';
    return;
  }
  
  // Afficher les suggestions filtrées
  suggestions.innerHTML = '';
  filtered.forEach(resource => {
    const item = document.createElement('div');
    item.className = 'suggestion-item';
    item.innerHTML = `
      <div>
        <strong>${resource.name}</strong>
        <small style="color: #64748b; display: block;">${resource.nni}</small>
      </div>
    `;
    item.onclick = () => addResourceToFilter(resource.name);
    suggestions.appendChild(item);
  });
  
  suggestions.style.display = 'block';
}

/**
 * Ajoute une ressource au filtre
 * @param {string} resourceName - Nom de la ressource à ajouter
 */
function addResourceToFilter(resourceName) {
  selectedResources.add(resourceName);
  
  const input = document.getElementById('resourcesFilterInput');
  
  if (input) input.value = '';
  
  // Mettre à jour l'affichage des ressources sélectionnées
  updateSelectedResourcesDisplay();
  
  // Réafficher toutes les ressources disponibles
  showAllAvailableResources();
}

/**
 * Retire une ressource du filtre
 * @param {string} resourceName - Nom de la ressource à retirer
 */
function removeResourceFromFilter(resourceName) {
  selectedResources.delete(resourceName);
  updateSelectedResourcesDisplay();
  
  // Réafficher toutes les ressources disponibles si le champ est vide
  const input = document.getElementById('resourcesFilterInput');
  if (input && input.value.trim() === '') {
    showAllAvailableResources();
  } else {
    handleResourcesInput(); // Rafraîchir avec la recherche actuelle
  }
}

/**
 * Met à jour l'affichage des ressources sélectionnées
 */
function updateSelectedResourcesDisplay() {
  const container = document.getElementById('selectedResources');
  if (!container) return;
  
  container.innerHTML = '';
  
  selectedResources.forEach(resourceName => {
    const chip = document.createElement('div');
    chip.className = 'resource-chip';
    chip.innerHTML = `
      <span>${resourceName}</span>
      <button class="remove-chip" onclick="removeResourceFromFilter('${resourceName}')" title="Retirer ${resourceName}">
        ×
      </button>
    `;
    container.appendChild(chip);
  });
}

/**
 * Efface tous les filtres
 */
function clearResourcesFilter() {
  selectedResources.clear();
  updateSelectedResourcesDisplay();
  
  const input = document.getElementById('resourcesFilterInput');  
  if (input) input.value = '';
  
  // Réafficher toutes les ressources disponibles
  showAllAvailableResources();
}

/**
 * Applique le filtre et met à jour la grille
 */
function applyResourcesFilter() {
  // Si aucune ressource sélectionnée, afficher toutes
  if (selectedResources.size === 0) {
    filteredResources = null;
  } else {
    filteredResources = Array.from(selectedResources);
  }
  
  // Fermer l'interface et rafraîchir la grille
  closeResourcesFilter();
  renderGrid();
}

/**
 * Initialise le module de filtre des ressources
 */
function initResourcesFilter() {
  const input = document.getElementById('resourcesFilterInput');
  const clearBtn = document.getElementById('clearResourcesFilter');
  const applyBtn = document.getElementById('applyResourcesFilter');
  const closeBtn = document.getElementById('closeResourcesFilter');
  const overlay = document.getElementById('resourcesFilterOverlay');
  
  // Événements de saisie
  if (input) {
    input.addEventListener('input', handleResourcesInput);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeResourcesFilter();
      }
    });
  }
  
  // Événements des boutons
  if (clearBtn) clearBtn.addEventListener('click', clearResourcesFilter);
  if (applyBtn) applyBtn.addEventListener('click', applyResourcesFilter);
  if (closeBtn) closeBtn.addEventListener('click', closeResourcesFilter);
  
  // Fermer en cliquant à l'extérieur
  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        closeResourcesFilter();
      }
    });
  }
  
  // Cacher les suggestions en cliquant ailleurs
  document.addEventListener('click', (e) => {
    const suggestions = document.getElementById('resourcesSuggestions');
    const inputContainer = document.querySelector('.filter-input-container');
    
    if (suggestions && inputContainer && !inputContainer.contains(e.target)) {
      suggestions.style.display = 'none';
    }
  });
}

// Variable globale pour stocker les ressources filtrées
let filteredResources = null;

// Auto-initialisation
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initResourcesFilter);
} else {
  initResourcesFilter();
}

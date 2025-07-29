// Module d'import et export des données
// Gère la sauvegarde et le chargement des données JSON

/**
 * Déclenche l'import de fichier JSON
 */
function triggerImport() {
  const importInput = document.getElementById('importFile');
  importInput.click();
}

/**
 * Télécharge les données au format JSON
 */
function downloadData() {
  const exportJson = { 
    data, 
    preparateurs: preparateursMeta, 
    chantiers 
  };
  
  const blob = new Blob([JSON.stringify(exportJson, null, 2)], {
    type: 'application/json'
  });
  
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'planning.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

/**
 * Recharge les données depuis l'API
 */
async function reloadDataFromAPI() {
  if (typeof loadDataFromAPI === 'function') {
    const success = await loadDataFromAPI();
    if (success) {
      renderAll();
      console.log('🔄 Données rechargées depuis l\'API');
    }
  }
}

/**
 * Initialise le module d'import/export
 * Configure les événements sur l'input file
 */
function initImportExportModule() {
  const importInput = document.getElementById('importFile');
  
  if (!importInput) {
    console.warn('Element importFile non trouvé');
    return;
  }
  
  importInput.addEventListener('change', function() {
    const file = this.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const json = JSON.parse(e.target.result);
        
        // Mise à jour des données globales (pour compatibilité locale)
        data = json.data || {};
        preparateursMeta = json.preparateurs || {};
        chantiers = json.chantiers || {};
        
        renderAll();
        console.log('📁 Données importées depuis le fichier JSON');
      } catch {
        alert('JSON invalide');
      }
    };
    reader.readAsText(file);
  });
}

// Auto-initialisation
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initImportExportModule);
} else {
  initImportExportModule();
}

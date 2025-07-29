// Module de gestion des préparateurs
// Gère l'ajout, modification et suppression des préparateurs

let editingPrep = null;

/**
 * Ouvre l'interface de gestion des préparateurs
 */
function managePreparateurs() {
  const overlay = document.getElementById('prepOverlay');
  const list = document.getElementById('prepList');
  
  list.innerHTML = '';
  
  // Affichage de la liste des préparateurs existants
  Object.keys(data).forEach(p => {
    const div = document.createElement('div');
    const nni = preparateursMeta[p] || 'Non défini';
    div.innerHTML = `<span>${p} – ${nni}</span>`;
    
    // Bouton modification
    const btnEdit = document.createElement('button');
    btnEdit.textContent = 'Modif';
    btnEdit.onclick = () => editPreparateur(p);
    
    // Bouton suppression
    const btnDel = document.createElement('button');
    btnDel.textContent = 'Suppr';
    btnDel.onclick = () => removePreparateur(p);
    
    div.appendChild(btnEdit);
    div.appendChild(btnDel);
    list.appendChild(div);
  });
  
  hideAddForm();
  overlay.style.display = 'block';
}

/**
 * Affiche le formulaire d'ajout de préparateur
 */
function showAddForm() {
  document.getElementById('addForm').style.display = 'block';
  document.getElementById('btnShowAdd').style.display = 'none';
}

/**
 * Cache le formulaire d'ajout de préparateur
 */
function hideAddForm() {
  document.getElementById('prepName').value = '';
  document.getElementById('prepNNI').value = '';
  document.getElementById('addForm').style.display = 'none';
  document.getElementById('btnShowAdd').style.display = 'inline-block';
  editingPrep = null;
}

/**
 * Ajoute ou modifie un préparateur
 */
function addPreparateur() {
  const name = document.getElementById('prepName').value.trim();
  const nni = document.getElementById('prepNNI').value.trim();
  
  if (!name || !nni) {
    return alert('Nom et NNI requis');
  }
  
  if (editingPrep) {
    // Mode modification
    const old = editingPrep;
    const oldData = data[old];
    delete data[old];
    delete preparateursMeta[old];
    data[name] = oldData;
    preparateursMeta[name] = nni;
  } else {
    // Mode ajout
    if (data[name]) {
      return alert('Préparateur existe déjà');
    }
    data[name] = {};
    preparateursMeta[name] = nni;
  }
  
  renderAll();
  managePreparateurs();
}

/**
 * Passe en mode édition pour un préparateur
 * @param {string} p - Nom du préparateur à éditer
 */
function editPreparateur(p) {
  editingPrep = p;
  document.getElementById('prepName').value = p;
  document.getElementById('prepNNI').value = preparateursMeta[p] || '';
  showAddForm();
}

/**
 * Supprime un préparateur après confirmation
 * @param {string} p - Nom du préparateur à supprimer
 */
function removePreparateur(p) {
  if (!confirm(`Supprimer ${p} ?`)) return;
  
  delete data[p];
  delete preparateursMeta[p];
  renderAll();
  managePreparateurs();
}

/**
 * Ferme l'overlay de gestion des préparateurs
 */
function closePrepOverlay() {
  const overlay = document.getElementById('prepOverlay');
  overlay.style.display = 'none';
}

/**
 * Initialise le module des préparateurs
 * Attache les événements nécessaires
 */
function initPreparateursModule() {
  // Les fonctions sont déjà globales et utilisées dans le HTML
  // Pas besoin d'initialisation spécifique
}

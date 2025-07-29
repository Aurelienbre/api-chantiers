// Module de création de chantiers
// Interface sidebar pour créer et affecter des chantiers avec mode simulation

// Variables globales
let chantierEnAttenteAffectation = null;
let chantierMouseOverHandler = null;
let chantierMouseOutHandler = null;
let chantierClickHandler = null;
let simulationMode = false;

/**
 * Vérifie que les styles CSS pour la sidebar sont disponibles
 * Les styles sont maintenant définis dans styles.css
 */
function ensureChantierStyles() {
  // Les styles sont maintenant dans styles.css - rien à faire
  // Cette fonction est conservée pour compatibilité
}

/**
 * Nettoyage des handlers d'affectation
 */
function cleanupAffectationHandlers() {
  if (chantierMouseOverHandler) {
    document.removeEventListener('mouseover', chantierMouseOverHandler);
    document.removeEventListener('mouseout', chantierMouseOutHandler);
    document.removeEventListener('click', chantierClickHandler);
    chantierMouseOverHandler = chantierMouseOutHandler = chantierClickHandler = null;
  }
}

/**
 * Nettoyage des handlers de simulation
 */
function cleanupSimulationHandlers() {
  if (chantierMouseOverHandler) {
    document.removeEventListener('mouseover', chantierMouseOverHandler);
    document.removeEventListener('mouseout', chantierMouseOutHandler);
    chantierMouseOverHandler = chantierMouseOutHandler = null;
  }
}

/**
 * Phase d'affectation classique - attend un clic sur un nom de préparateur
 * @param {string} chantierID - ID du chantier à affecter
 */
function attendreClicSurNomPreparateurPourAffectation(chantierID) {
  function overHandler(e) {
    const txt = e.target.textContent.trim();
    if (preparateursMeta[txt]) {
      e.target.style.background = '#cce5ff';
      e.target.style.cursor = 'pointer';
      e.target.title = `Affecter à ${txt}`;
    }
  }
  
  function outHandler(e) {
    const txt = e.target.textContent.trim();
    if (preparateursMeta[txt]) {
      e.target.style.background = '';
      e.target.style.cursor = '';
      e.target.title = '';
    }
  }
  
  function clickHandler(e) {
    if (simulationMode) return;
    const txt = e.target.textContent.trim();
    if (preparateursMeta[txt] && chantierEnAttenteAffectation === chantierID) {
      chantiers[chantierID].preparateur = txt;
      chantierEnAttenteAffectation = null;
      cleanupAffectationHandlers();
      repartitionAutomatique();
      renderAll();
      toggleCreationChantierInterface();
    }
  }
  
  chantierMouseOverHandler = overHandler;
  chantierMouseOutHandler = outHandler;
  chantierClickHandler = clickHandler;
  document.addEventListener('mouseover', overHandler);
  document.addEventListener('mouseout', outHandler);
  document.addEventListener('click', clickHandler);
}

/**
 * Simulation par hover - prévisualise l'affectation
 * @param {Event} e - Événement mouseover
 */
function simulateOver(e) {
  if (!simulationMode) return;
  const txt = e.target.textContent.trim();
  const id = chantierEnAttenteAffectation;
  if (!id || !chantiers[id] || !preparateursMeta[txt]) return;
  
  if (!('_simulOriginalPrep' in chantiers[id])) {
    chantiers[id]._simulOriginalPrep = chantiers[id].preparateur;
  }
  
  chantiers[id].preparateur = txt;
  repartitionAutomatique();
  renderAll();
  
  document.querySelectorAll('.row-header').forEach(cell => {
    if (cell.textContent.trim() === txt) {
      cell.style.background = '#e0f7fa';
    }
  });
}

/**
 * Fin de simulation par hover
 * @param {Event} e - Événement mouseout
 */
function simulateOut(e) {
  if (!simulationMode) return;
  const id = chantierEnAttenteAffectation;
  if (!id || !chantiers[id]) return;
  
  const original = chantiers[id]._simulOriginalPrep;
  chantiers[id].preparateur = original || null;
  delete chantiers[id]._simulOriginalPrep;
  
  repartitionAutomatique();
  closeTooltip();
  renderAll();
  
  document.querySelectorAll('.row-header').forEach(cell => {
    cell.style.background = '';
  });
}

/**
 * Active/désactive la sidebar de création
 */
function toggleCreationChantierInterface() {
  if (simulationMode) return;
  
  const existing = document.querySelector('.chantier-creation-sidebar');
  if (existing) {
    simulationMode = false;
    cleanupSimulationHandlers();
    existing.remove();
    chantierEnAttenteAffectation = null;
    cleanupAffectationHandlers();
    return;
  }
  
  openCreationChantierInterface();
}

/**
 * Active/désactive les champs de saisie
 * @param {boolean} state - État disabled
 * @param {Object} els - Éléments à modifier
 */
function setInputsDisabled(state, els) {
  els.inputID.disabled = state;
  els.inputLabel.disabled = state;
  els.selectStatus.disabled = state;
  els.inputTime.disabled = state;
  els.inputDate.disabled = state;
}

/**
 * Crée et affiche l'interface sidebar de création
 */
function openCreationChantierInterface() {
  ensureChantierStyles();

  // Création des éléments de formulaire
  const inputID = document.createElement('input');
  inputID.placeholder = 'ID du chantier (ex : CH-XXXXXX)';
  
  const inputLabel = document.createElement('input');
  inputLabel.placeholder = 'Libellé';
  
  const selectStatus = document.createElement('select');
  ['Nouveau', 'Prépa. en cours', 'Préparé', 'Travaux réalisés', 'Clôturé', 'Annulé'].forEach(st => {
    selectStatus.add(new Option(st, st));
  });
  
  const inputTime = document.createElement('input');
  inputTime.type = 'number';
  inputTime.step = '0.25';
  inputTime.placeholder = 'Temps (h)';
  inputTime.addEventListener('keypress', e => {
    if (!/[0-9\.]/.test(e.key)) e.preventDefault();
  });
  
  const inputDate = document.createElement('input');
  inputDate.type = 'date';

  // Boutons d'action
  const btnAction = document.createElement('button');
  btnAction.textContent = 'Affecter';
  btnAction.className = 'btn-assign';
  btnAction.disabled = true;
  
  const btnSimulation = document.createElement('button');
  btnSimulation.textContent = 'Simulation';
  btnSimulation.className = 'btn-simulation';
  btnSimulation.disabled = true;
  
  const btnClose = document.createElement('button');
  btnClose.textContent = 'Fermer';
  btnClose.className = 'btn-close';

  // Construction de la sidebar
  const sidebar = document.createElement('div');
  sidebar.className = 'chantier-creation-sidebar open';
  
  const header = document.createElement('h3');
  header.textContent = 'Création chantier';
  sidebar.appendChild(header);
  
  sidebar.append(inputID, inputLabel, selectStatus, inputTime, inputDate, btnAction, btnSimulation, btnClose);
  document.body.appendChild(sidebar);

  // Validation des champs
  function updateActionState() {
    const ready = inputID.value.trim() && inputLabel.value.trim() && inputTime.value.trim() && inputDate.value;
    btnAction.disabled = !ready;
    btnSimulation.disabled = !ready;
  }
  
  [inputID, inputLabel, inputTime, inputDate].forEach(el => el.addEventListener('input', updateActionState));
  selectStatus.addEventListener('change', updateActionState);

  // Événements des boutons
  btnClose.addEventListener('click', toggleCreationChantierInterface);

  btnAction.addEventListener('click', () => {
    if (!btnAction.classList.contains('clicked')) {
      // Début mode affectation
      const id = inputID.value.trim();
      const label = inputLabel.value.trim();
      const status = selectStatus.value;
      const time = parseFloat(inputTime.value) * 60;
      const date = inputDate.value;
      const [Y, M, D] = date.split('-');
      const endDate = `${D}/${M}/${Y}`;
      
      chantiers[id] = { id, label, status, prepTime: Math.round(time), endDate, preparateur: null };
      chantierEnAttenteAffectation = id;
      setInputsDisabled(true, { inputID, inputLabel, selectStatus, inputTime, inputDate });
      btnSimulation.disabled = true;
      btnAction.classList.add('clicked');
      attendreClicSurNomPreparateurPourAffectation(id);
      renderAll();
    } else {
      // Fin mode affectation
      chantierEnAttenteAffectation = null;
      cleanupAffectationHandlers();
      setInputsDisabled(false, { inputID, inputLabel, selectStatus, inputTime, inputDate });
      btnSimulation.disabled = false;
      btnAction.classList.remove('clicked');
    }
  });

  btnSimulation.addEventListener('click', () => {
    const id = inputID.value.trim();
    const label = inputLabel.value.trim();
    const status = selectStatus.value;
    const time = parseFloat(inputTime.value) * 60;
    const date = inputDate.value;
    const [Y, M, D] = date.split('-');
    const endDate = `${D}/${M}/${Y}`;
    
    if (!chantiers[id]) chantiers[id] = { preparateur: null };
    chantiers[id].id = id;
    chantiers[id].label = label;
    chantiers[id].status = status;
    chantiers[id].prepTime = Math.round(time);
    chantiers[id].endDate = endDate;
    chantierEnAttenteAffectation = id;

    if (!btnSimulation.classList.contains('clicked')) {
      // Début simulation
      simulationMode = true;
      chantiers[id]._simulOriginalPrep = chantiers[id].preparateur;
      document.addEventListener('mouseover', simulateOver);
      document.addEventListener('mouseout', simulateOut);
      btnSimulation.classList.add('clicked');
      setInputsDisabled(true, { inputID, inputLabel, selectStatus, inputTime, inputDate });
      btnAction.disabled = true;
      btnClose.disabled = true;
    } else {
      // Fin simulation
      simulationMode = false;
      cleanupSimulationHandlers();
      if (chantiers[id]._simulOriginalPrep !== undefined) {
        chantiers[id].preparateur = chantiers[id]._simulOriginalPrep || null;
        delete chantiers[id]._simulOriginalPrep;
      }
      chantierEnAttenteAffectation = null;
      btnSimulation.classList.remove('clicked');
      setInputsDisabled(false, { inputID, inputLabel, selectStatus, inputTime, inputDate });
      btnAction.disabled = false;
      btnClose.disabled = false;
      renderAll();
    }
  });
}

/**
 * Initialise le module de création de chantiers
 */
function initChantierCreationModule() {
  const btn = document.getElementById('creation_chantier');
  if (btn) {
    btn.removeEventListener('click', toggleCreationChantierInterface);
    btn.addEventListener('click', toggleCreationChantierInterface);
  } else {
    // Retry si l'élément n'est pas encore disponible
    setTimeout(initChantierCreationModule, 200);
  }
}

// Auto-initialisation
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initChantierCreationModule);
} else {
  initChantierCreationModule();
}

// Module de gestion des disponibilités
// Permet l'édition en masse des disponibilités via une interface modale

/**
 * Fonction unique d'édition des disponibilités
 * Ouvre une modale pour saisir les disponibilités au format JSON
 */
function ajout_disponibilite() {
  // Création de l'overlay
  const overlay = document.createElement('div');
  overlay.className = 'availability-overlay';

  // Boîte de dialogue
  const dialog = document.createElement('div');
  dialog.className = 'availability-dialog';

  // Zone de saisie JSON
  const ta = document.createElement('textarea');
  ta.className = 'availability-textarea';
  ta.placeholder = 'Collez ici l\'objet JSON (clefs = NNI, valeurs = minutes)';

  // Boutons
  const ctr = document.createElement('div');
  ctr.className = 'availability-buttons';
  const save = document.createElement('button');
  save.textContent = 'Enregistrer';
  save.className = 'availability-save-btn';
  const cancel = document.createElement('button');
  cancel.textContent = 'Annuler';

  // Enregistrer : parse, met à jour data, rafraîchit et ferme la modale
  save.onclick = () => {
    let parsed;
    try {
      parsed = JSON.parse(ta.value.trim());
    } catch (e) {
      alert('JSON invalide : ' + e.message);
      return;
    }
    const nowIso = new Date().toISOString();
    Object.entries(parsed).forEach(([nni, weeksMap]) => {
      const names = Object.keys(preparateursMeta)
                         .filter(n => preparateursMeta[n] === nni);
      names.forEach(name => {
        if (!data[name]) data[name] = {};
        Object.entries(weeksMap).forEach(([weekKey, minutes]) => {
          data[name][weekKey] = { minutes, updatedAt: nowIso };
        });
      });
    });

    renderAll();
    // on ferme l'overlay avec remove()
    overlay.remove();
  };

  // Annuler : ferme simplement la modale
  cancel.onclick = () => overlay.remove();

  // Montage et affichage
  ctr.append(save, cancel);
  dialog.append(ta, ctr);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
}

/**
 * Initialise le module des disponibilités
 * Attache l'événement au bouton d'édition des disponibilités
 */
function initAvailabilityModule() {
  const btn = document.getElementById('edit-availability-btn');
  if (btn) {
    btn.addEventListener('click', ajout_disponibilite);
  } else {
    console.warn('Bouton edit-availability-btn non trouvé');
  }
}

// Auto-initialisation quand le DOM est prêt
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAvailabilityModule);
} else {
  initAvailabilityModule();
}

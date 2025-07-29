// Module de gestion du calendrier
// Gère l'affichage et la navigation dans le calendrier de planification

/**
 * Ouvre/ferme le calendrier
 * Positionne le calendrier sous le bouton de navigation
 */
function openCalendar() {
  if (!calOverlay || !navEl) {
    console.error('Elements DOM requis non trouvés pour le calendrier');
    return;
  }
  
  if (calOverlay.style.display === 'block') return closeCalendar();
  
  const wk = weeks[selectedWeek];
  const calendarBtn = navEl.querySelector('button.calendar-button');
  if (!calendarBtn) {
    console.error('Bouton calendrier non trouvé');
    return;
  }
  
  const rect = calendarBtn.getBoundingClientRect();
  calOverlay.style.top = `${rect.bottom + window.scrollY + 5}px`;
  calOverlay.style.left = `${rect.left + window.scrollX}px`;
  calOverlay.style.display = 'block';
  renderCalendar(wk.start.getFullYear(), wk.start.getMonth());
}

/**
 * Ferme le calendrier
 */
function closeCalendar() {
  if (calOverlay) {
    calOverlay.style.display = 'none';
  }
}

/**
 * Affiche le calendrier pour un mois donné
 * @param {number} calYear - Année à afficher
 * @param {number} calMonth - Mois à afficher (0-11)
 */
function renderCalendar(calYear, calMonth) {
  calOverlay.innerHTML = '';
  
  // En-tête avec boutons de navigation
  const hdr = document.createElement('header');
  const buttons = ['Aujourd\'hui', '<', '>'];
  buttons.forEach(txt => {
    const btn = document.createElement('button');
    btn.textContent = txt;
    if (txt === 'Aujourd\'hui') {
      btn.onclick = () => selectWeek(weeks.find(w => w.id === nowId) || weeks[0]);
    }
    if (txt === '<') {
      btn.onclick = () => {
        if (calMonth === 0) {
          calYear--;
          calMonth = 11;
        } else calMonth--;
        renderCalendar(calYear, calMonth);
      };
    }
    if (txt === '>') {
      btn.onclick = () => {
        if (calMonth === 11) {
          calYear++;
          calMonth = 0;
        } else calMonth++;
        renderCalendar(calYear, calMonth);
      };
    }
    hdr.appendChild(btn);
  });

  // Sélecteur de mois/année
  const monthSel = document.createElement('select');
  const months = ['janv.', 'fevr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'aout', 'sept.', 'oct.', 'nov.', 'dec.'];

  months.forEach((m, i) => {
    const o = document.createElement('option');
    o.value = i;
    o.textContent = `${m} ${calYear}`;
    if (i === calMonth) o.selected = true;
    monthSel.appendChild(o);
  });

  monthSel.onchange = () => renderCalendar(calYear, parseInt(monthSel.value, 10));
  hdr.appendChild(monthSel);
  calOverlay.appendChild(hdr);

  // Table du calendrier
  const tbl = document.createElement('table');
  const thead = document.createElement('thead');
  const trh = document.createElement('tr');

  ['', 'lu', 'ma', 'me', 'je', 've', 'sa', 'di'].forEach(d => {
    const th = document.createElement('th');
    th.textContent = d;
    trh.appendChild(th);
  });

  thead.appendChild(trh);
  tbl.appendChild(thead);

  // Corps du calendrier avec les semaines
  const first = new Date(calYear, calMonth, 1);
  const last = new Date(calYear, calMonth + 1, 0);
  const tbody = document.createElement('tbody');

  weeks.filter(w => w.start <= last && w.end >= first).forEach(wk => {
    const tr = document.createElement('tr');
    const tdw = document.createElement('td');
    tdw.textContent = wk.id;
    tdw.onclick = () => selectWeek(wk);
    tr.appendChild(tdw);

    // Jours de la semaine
    for (let d = 0; d < 7; d++) {
      const td = document.createElement('td');
      const dt = new Date(wk.start);
      dt.setDate(dt.getDate() + d);
      td.textContent = dt.getDate();
      
      // Styles pour les jours hors mois et jour actuel
      if (dt.getMonth() !== calMonth) td.className = 'disabled';
      if (dt.toDateString() === now.toDateString()) td.classList.add('today');
      if (!td.classList.contains('disabled')) td.onclick = () => selectWeek(wk);
      tr.appendChild(td);
    }

    tbody.appendChild(tr);
  });

  tbl.appendChild(tbody);
  calOverlay.appendChild(tbl);
}

/**
 * Sélectionne une semaine et met à jour l'affichage
 * @param {Object} wk - Objet semaine à sélectionner
 */
function selectWeek(wk) {
  const idx = weeks.findIndex(w => w.id === wk.id);
  if (idx >= 0) selectedWeek = idx;
  renderAll();
  closeCalendar();
}

/**
 * Génère et affiche la barre de navigation des semaines
 */
function renderNav() {
  if (!navEl) {
    console.error('Element navEl non trouvé. Vérifiez que week-nav existe dans le DOM.');
    return;
  }
  
  navEl.innerHTML = '';
  const half = Math.floor(WINDOW_SIZE / 2);
  const start = Math.max(0, Math.min(weeks.length - WINDOW_SIZE, selectedWeek - half));

  weeks.slice(start, start + WINDOW_SIZE).forEach((w, i) => {
    const btn = document.createElement('button');
    const num = +w.id.split('/')[0].substring(1);
    btn.textContent = `S${num}`;
    if (start + i === selectedWeek) btn.classList.add('active');
    btn.onclick = () => selectWeek(w);
    navEl.appendChild(btn);
  });

  // Bouton calendrier
  const cb = document.createElement('button');
  cb.textContent = '📅';
  cb.className = 'calendar-button';
  cb.onclick = openCalendar;
  navEl.appendChild(cb);
}

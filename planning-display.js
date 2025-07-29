// Module d'affichage du planning
// Gère le rendu de la grille de planification avec calculs de marges et tooltips

/**
 * Ferme les tooltips ouverts
 */
function closeTooltip() {
  const tt = document.querySelector('.tooltip');
  if (tt) tt.remove();
}

/**
 * Calcule et applique la largeur optimale des colonnes selon la largeur d'écran
 */
function calculateOptimalColumnWidth() {
  const container = document.querySelector('.planning-container');
  if (!container) return;
  
  const containerWidth = container.clientWidth;
  const resourcesColumnWidth = 192; // 12rem = 192px
  const gapWidth = 8; // 0.5rem de gap
  const paddingWidth = 16; // 0.5rem padding de chaque côté = 1rem = 16px
  const scrollbarWidth = 17; // Largeur approximative de la scrollbar verticale
  
  // Largeur disponible pour les colonnes de semaines
  const availableWidth = containerWidth - resourcesColumnWidth - paddingWidth - scrollbarWidth;
  
  // Calculer la largeur optimale par colonne
  const weekColumns = parseInt(document.documentElement.style.getPropertyValue('--visible-weeks') || '10');
  const totalGaps = (weekColumns) * gapWidth; // Gaps entre toutes les colonnes (y compris après "Ressources")
  const widthPerColumn = (availableWidth - totalGaps) / weekColumns;
  
  // Largeur minimale acceptable pour une colonne (5rem = 80px)
  const minColumnWidth = 80;
  
  // Utiliser la largeur minimale si calculée trop petite, sinon utiliser la largeur calculée
  const optimalWidth = Math.max(minColumnWidth, Math.floor(widthPerColumn));
  
  // Template de grid unifié avec largeur fixe
  const gridTemplate = `12rem repeat(${weekColumns}, ${optimalWidth}px)`;
  document.documentElement.style.setProperty('--grid-template', gridTemplate);
  
  console.log(`Colonnes: ${weekColumns}, Largeur container: ${containerWidth}px, Disponible: ${availableWidth}px, Largeur par colonne: ${optimalWidth}px`);
}

/**
 * Synchronise le scroll horizontal entre l'en-tête et le contenu
 */
function setupScrollSync() {
  const headerEl = document.getElementById('grid-header');
  const contentEl = document.getElementById('schedule-grid');
  
  if (!headerEl || !contentEl) return;
  
  // Variables pour éviter les boucles infinies
  let isHeaderScrolling = false;
  let isContentScrolling = false;
  
  // Synchronisation depuis l'en-tête vers le contenu
  headerEl.addEventListener('scroll', function() {
    if (isContentScrolling) return;
    
    isHeaderScrolling = true;
    contentEl.scrollLeft = headerEl.scrollLeft;
    
    setTimeout(() => {
      isHeaderScrolling = false;
    }, 50);
  });
  
  // Synchronisation depuis le contenu vers l'en-tête
  contentEl.addEventListener('scroll', function() {
    if (isHeaderScrolling) return;
    
    isContentScrolling = true;
    headerEl.scrollLeft = contentEl.scrollLeft;
    
    setTimeout(() => {
      isContentScrolling = false;
    }, 50);
  });
}

/**
 * Affiche la grille de planification avec les disponibilités et charges
 */
function renderGrid() {
  if (!gridEl) {
    console.error('Element gridEl non trouvé. Vérifiez que schedule-grid existe dans le DOM.');
    return;
  }
  
  const VISIBLE = visibleWeeksCount;
  const headerEl = document.getElementById('grid-header');
  
  if (!headerEl) {
    console.error('Element grid-header non trouvé.');
    return;
  }

  // Mise à jour de la variable CSS pour le nombre de colonnes
  document.documentElement.style.setProperty('--visible-weeks', VISIBLE);
  
  // Calculer la largeur optimale des colonnes
  calculateOptimalColumnWidth();
  
  // Vider les conteneurs
  headerEl.innerHTML = '';
  gridEl.innerHTML = '';

  // === EN-TÊTE FIXE ===
  // Cellule "Ressources" dans l'en-tête (cliquable pour filtrer)
  const hdrRes = document.createElement('div');
  hdrRes.className = 'cell header-cell resources-filter-btn';
  hdrRes.innerHTML = `
    <div class="resources-content">
      <span>Ressources</span>
      <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M3 3a1 1 0 011-1h12a1 1 0 011 1v3a1 1 0 01-.293.707L12 11.414V15a1 1 0 01-.293.707l-2 2A1 1 0 018 17v-5.586L3.293 6.707A1 1 0 013 6V3z" clip-rule="evenodd" />
      </svg>
    </div>
  `;
  hdrRes.onclick = openResourcesFilter;
  headerEl.appendChild(hdrRes);

  // En-têtes des semaines dans l'en-tête fixe
  const slice = weeks.slice(selectedWeek, selectedWeek + VISIBLE);
  slice.forEach(w => {
    const h = document.createElement('div');
    h.className = 'cell header-cell';
    if (w.id === nowId) h.classList.add('current-week-col');
    h.innerHTML = `<strong>${w.id}</strong><br><small>${w.label}</small>`;
    headerEl.appendChild(h);
  });

  const currentIndex = weeks.findIndex(w => w.id === nowId);
  const currentWeek = weeks[currentIndex];
  const currentWeekNumber = currentWeek.start.getWeek();
  const currentYear = currentWeek.start.getFullYear();

  // Calcul des marges globales pour chaque préparateur
  const margesGlobales = {};
  Object.keys(data).forEach(name => {
    margesGlobales[name] = {};
    let margePrec = 0;
    for (let i = currentIndex; i < weeks.length; i++) {
      const w = weeks[i];
      const year = w.start.getFullYear();
      const weekNo = String(w.start.getWeek()).padStart(2, '0');
      const weekKey = `${year}-W${weekNo}-1`;
      const stored = data[name][weekKey];
      let mins = 0;
      if (stored && typeof stored === 'object') mins = stored.minutes || 0;
      else if (typeof stored === 'number') mins = stored;
      const dispoH = mins / 60;

      let chargeEcheance = 0;
      Object.values(chantiers).forEach(ch => {
        if (ch.preparateur === name && (ch.status === "Nouveau" || ch.status === "Prépa. en cours")) {
          const [d, m, y] = ch.endDate.split('/');
          const dateEch = new Date(`${y}-${m}-${d}`);
          const echWeek = dateEch.getWeek();
          const echYear = dateEch.getFullYear();
          const isCurrent = (w.start.getWeek() === currentWeekNumber && w.start.getFullYear() === currentYear);
          const isPastEcheance = echYear < currentYear || (echYear === currentYear && echWeek < currentWeekNumber);
          const plannedThisOrLater = ch.planification && Object.keys(ch.planification).some(k => {
            const parts = k.split('-W');
            const y = parseInt(parts[0]);
            const w = parseInt(parts[1]);
            return y > currentYear || (y === currentYear && w >= currentWeekNumber);
          });

          if (
            (echWeek === w.start.getWeek() && echYear === w.start.getFullYear()) ||
            (isCurrent && isPastEcheance && plannedThisOrLater)
          ) {
            chargeEcheance += ch.prepTime;
          }
        }
      });

      const C = chargeEcheance / 60;
      const CA = dispoH + margePrec;
      const M = CA - C;
      margesGlobales[name][weekKey] = { dispo: dispoH, C, CA, M };
      margePrec = M;
    }
  });

  // Calcul des tensions de disponibilité (Tdisp)
  Object.keys(margesGlobales).forEach(name => {
    const keys = weeks.slice(currentIndex).map(w => {
      const y = w.start.getFullYear();
      const wn = String(w.start.getWeek()).padStart(2, '0');
      return `${y}-W${wn}-1`;
    });
    keys.forEach((weekKey, idx) => {
      let minM = Infinity;
      for (let j = idx; j < Math.min(idx + 16, keys.length); j++) {
        const m = margesGlobales[name][keys[j]].M;
        if (m < minM) minM = m;
      }
      margesGlobales[name][weekKey].Tdisp = minM;
    });
  });

  // Calcul des badges d'affichage
  Object.keys(margesGlobales).forEach(name => {
    let lastTdisp = null;
    const keys = weeks.slice(currentIndex).map(w => {
      const y = w.start.getFullYear();
      const wn = String(w.start.getWeek()).padStart(2, '0');
      return `${y}-W${wn}-1`;
    });
    keys.forEach(weekKey => {
      const calc = margesGlobales[name][weekKey];
      let badge = null;
      if (calc.dispo > 0) {
        const raw = calc.Tdisp;
        if (lastTdisp === null) {
          badge = Math.round(raw * 2) / 2;
        } else if (raw !== lastTdisp) {
          let diff = lastTdisp > 0 ? raw - lastTdisp : raw;
          badge = Math.round(diff * 2) / 2;
        }
        lastTdisp = raw;
      }
      calc.badge = badge;
    });
  });

  // Rendu des lignes pour chaque préparateur
  let preparateursToShow = Object.keys(data);
  
  // Appliquer le filtre si des ressources sont sélectionnées
  if (typeof filteredResources !== 'undefined' && filteredResources && filteredResources.length > 0) {
    preparateursToShow = preparateursToShow.filter(name => filteredResources.includes(name));
  }
  
  preparateursToShow.forEach(name => {
    const rh = document.createElement('div');
    rh.className = 'cell row-header';
    rh.textContent = name;
    gridEl.appendChild(rh);

    slice.forEach(w => {
      const weekKey = `${w.start.getFullYear()}-W${String(w.start.getWeek()).padStart(2, '0')}-1`;
      
      // Récupération des disponibilités pour toutes les semaines (passées et futures)
      let dispoH = 0;
      if (margesGlobales[name][weekKey]) {
        // Semaine future avec calcul de marge
        dispoH = margesGlobales[name][weekKey].dispo;
      } else {
        // Semaine passée : récupération directe des données
        const stored = data[name][weekKey];
        let mins = 0;
        if (stored && typeof stored === 'object') mins = stored.minutes || 0;
        else if (typeof stored === 'number') mins = stored;
        dispoH = mins / 60;
      }
      
      const mins = dispoH * 60;

      const cell = document.createElement('div');
      cell.className = 'cell';
      if (w.id === nowId) cell.classList.add('current-week-col');
      gridEl.appendChild(cell);

      const inner = document.createElement('div');
      Object.assign(inner.style, {
        position: 'relative',
        width: '100%',
        height: '100%',
        padding: '4px',
        boxSizing: 'border-box'
      });
      cell.appendChild(inner);

      // Barre de disponibilité
      const ratio = Math.max(0, Math.min(1, mins / 2400));
      const bar = document.createElement('div');
      Object.assign(bar.style, {
        position: 'absolute',
        top: '3px',
        bottom: '3px',
        left: '3px',
        width: `calc(${Math.round(ratio * 100)}% - 6px)`,
        borderRadius: '8px',
        background: w.id === nowId ? '#89cdd4' : '#cdeff1',
        overflow: 'hidden',
        boxSizing: 'border-box'
      });
      inner.appendChild(bar);

      // Badge de tension
      const badgeVal = margesGlobales[name][weekKey]?.badge;
      if (badgeVal !== null && badgeVal !== undefined) {
        const badge = document.createElement('div');
        badge.className = 'tdisp-badge';
        badge.textContent = badgeVal;
        Object.assign(badge.style, {
          position: 'absolute',
          top: '4px',
          right: '4px',
          background: badgeVal > 0 ? 'rgba(144,238,144,0.8)' : 'rgba(255,99,71,0.8)',
          color: '#000',
          borderRadius: '4px',
          padding: '4px 6px',
          fontSize: '0.85rem',
          pointerEvents: 'none'
        });
        inner.appendChild(badge);
      }

      // Segments de chantiers planifiés
      const planned = Object.values(chantiers).filter(ch =>
        ch.preparateur === name && ch.planification && ch.planification[weekKey] > 0
      ).map(ch => ({
        id: ch.id,
        text: ch.label,
        hours: ch.planification[weekKey] / 60,
        endDate: ch.endDate,
        endDateObj: new Date(ch.endDate.split('/').reverse().join('-'))
      })).sort((a, b) => a.endDateObj - b.endDateObj);

      let cum = 0;
      planned.forEach(seg => {
        const leftPct = (cum / dispoH) * 100;
        const widthPct = (seg.hours / dispoH) * 100;
        const s = document.createElement('div');

        Object.assign(s.style, {
          position: 'absolute',
          left: leftPct + '%',
          width: widthPct + '%',
          height: '80%',
          top: '10%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '0.75rem',
          fontWeight: 'bold',
          textAlign: 'center',
          whiteSpace: 'normal',
          overflowWrap: 'break-word',
          overflow: 'hidden',
          padding: '2px 4px',
          boxSizing: 'border-box',
          borderRadius: '8px',
          color: '#333',
          background: '#fff',
          border: '1px solid #bbb',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.2)',
          transition: 'background 0.2s ease, transform 0.1s ease',
          cursor: 'pointer'
        });

        // Coloration selon l'échéance
        const weekDate = w.start;
        const echWeek = seg.endDateObj.getWeek();
        const echYear = seg.endDateObj.getFullYear();
        const isLate = weekDate.getFullYear() > echYear || (weekDate.getFullYear() === echYear && weekDate.getWeek() > echWeek);
        const isSameWeek = weekDate.getFullYear() === echYear && weekDate.getWeek() === echWeek;
        if (isLate) {
          s.style.background = '#f8d7da';
          s.style.border = '1px solid #f5c6cb';
        } else if (isSameWeek) {
          s.style.background = '#fff3cd';
          s.style.border = '1px solid #ffeeba';
        }

        s.textContent = seg.text;
        bar.appendChild(s);

        // Événements de hover pour tooltip
        s.addEventListener('mouseenter', function () {
          s.style.transform = 'scale(1.02)';
          s.style.background = isLate ? '#f1b0b7' : isSameWeek ? '#ffe8a1' : '#f0f0f0';
          closeTooltip();
          const tt = document.createElement('div');
          tt.className = 'tooltip';
          tt.style.position = 'fixed';
          tt.innerHTML =
            `<div><strong>ID:</strong> ${seg.id}</div>
             <div><strong>Libellé:</strong> <span style="word-break: break-all;">${seg.text}</span></div>
             <div><strong>Temps:</strong> ${seg.hours.toFixed(1)} h</div>
             <div><strong>Fin:</strong> ${seg.endDate}</div>`;
          document.body.appendChild(tt);
        });

        s.addEventListener('mousemove', e => {
          const tt = document.querySelector('.tooltip');
          if (tt) {
            // Calcul de la position avec vérification des bords de l'écran
            let x = e.clientX + 10;
            let y = e.clientY + 10;
            
            // Vérifier si le tooltip dépasse à droite
            const ttRect = tt.getBoundingClientRect();
            if (x + ttRect.width > window.innerWidth) {
              x = e.clientX - ttRect.width - 10;
            }
            
            // Vérifier si le tooltip dépasse en bas
            if (y + ttRect.height > window.innerHeight) {
              y = e.clientY - ttRect.height - 10;
            }
            
            // S'assurer que le tooltip reste dans les limites
            x = Math.max(5, Math.min(x, window.innerWidth - ttRect.width - 5));
            y = Math.max(5, Math.min(y, window.innerHeight - ttRect.height - 5));
            
            tt.style.left = x + 'px';
            tt.style.top = y + 'px';
          }
        });

        s.addEventListener('mouseleave', function () {
          s.style.transform = 'scale(1.0)';
          s.style.background = isLate ? '#f8d7da' : isSameWeek ? '#fff3cd' : '#fff';
          closeTooltip();
        });

        s.addEventListener('contextmenu', function (e) {
          e.preventDefault();
          closeTooltip();
          openChantiersInterface(seg.id);
        });

        cum += seg.hours;
      });
    });
  });
  
  // Configurer la synchronisation du scroll horizontal
  setupScrollSync();
}

// Event listener pour recalculer lors du redimensionnement de la fenêtre
let resizeTimer;
window.addEventListener('resize', function() {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(function() {
    calculateOptimalColumnWidth();
  }, 250);
});

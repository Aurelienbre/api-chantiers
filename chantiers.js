// Module de gestion des chantiers
// Interface complète pour la gestion CRUD des chantiers avec filtres

/**
 * Ouvre l'interface de gestion des chantiers
 * @param {string} initialId - ID initial à rechercher (optionnel)
 */
function openChantiersInterface(initialId = '') {
  if (initialId instanceof Event) {
    initialId = '';
  }
  
  // Overlay & dialog
  const overlay = document.createElement('div'); 
  overlay.className = 'modal-overlay';
  const dlg = document.createElement('div'); 
  dlg.className = 'modal-dialog';
  overlay.appendChild(dlg);

  // Header
  const header = document.createElement('div'); 
  header.className = 'modal-header';
  const title = document.createElement('h3');   
  title.textContent = 'Gestion des chantiers';
  const close = document.createElement('button'); 
  close.textContent = '✖️';
  close.onclick = () => overlay.remove();
  header.append(title, close);
  dlg.appendChild(header);

  // Filters panel
  const filterPanel = document.createElement('div'); 
  filterPanel.className = 'filter-panel';
  dlg.appendChild(filterPanel);

  // Statut filters
  const statuses = ['Nouveau','Prépa. en cours','Préparé','Travaux réalisés','Clôturé','Annulé'];
  const selStatuses = new Set(statuses);
  const statusDiv = document.createElement('div');
  statusDiv.innerHTML = '<strong>Statut :</strong>';
  statusDiv.style.display = 'flex'; 
  statusDiv.style.alignItems = 'center'; 
  statusDiv.style.gap = '1rem';
  
  statuses.forEach(st => {
    const btn = document.createElement('button');
    btn.textContent = st; 
    btn.className = 'status-btn';
    btn.onclick = () => {
      if (selStatuses.has(st)) {
        selStatuses.delete(st); 
        btn.classList.add('inactive');
      } else {
        selStatuses.add(st); 
        btn.classList.remove('inactive');
      }
      refreshTable();
    };
    statusDiv.append(btn);
  });
  filterPanel.append(statusDiv);

  // Préparateur autocomplete + chips
  const prepDiv = document.createElement('div');
  const prepInput = document.createElement('input');
  prepInput.setAttribute('list','prep-list');
  prepInput.placeholder = 'ex : Jean ou DUPONT';
  const dl = document.createElement('datalist'); 
  dl.id = 'prep-list';
  
  Object.keys(preparateursMeta).forEach(n => {
    const o = document.createElement('option'); 
    o.value = n; 
    dl.append(o);
  });
  
  const chips = document.createElement('div'); 
  chips.className = 'chips-container';
  const selPreps = new Set();
  
  prepInput.oninput = () => {
    const v = prepInput.value.trim();
    if (v && preparateursMeta[v] && !selPreps.has(v)) {
      selPreps.add(v);
      const chip = document.createElement('div'); 
      chip.className = 'chip'; 
      chip.textContent = v;
      const x = document.createElement('span'); 
      x.className = 'remove'; 
      x.textContent = '×';
      x.onclick = () => { 
        selPreps.delete(v); 
        chips.removeChild(chip); 
        refreshTable(); 
      };
      chip.append(x); 
      chips.append(chip);
      prepInput.value = ''; 
      refreshTable();
    }
  };
  prepDiv.append(prepInput, dl, chips);
  filterPanel.append(prepDiv);

  // Date filters
  const dateDiv = document.createElement('div');
  dateDiv.innerHTML = '<strong>Date :</strong>';
  dateDiv.style.display = 'flex'; 
  dateDiv.style.alignItems = 'center'; 
  dateDiv.style.gap = '1rem';
  const selDates = new Set(['overdue','upcoming']);
  
  [['En retard','overdue'],['À venir','upcoming']].forEach(([lbl,key]) => {
    const btn = document.createElement('button');
    btn.textContent = lbl; 
    btn.className = 'date-btn';
    btn.onclick = () => {
      if (selDates.has(key)) {
        selDates.delete(key); 
        btn.classList.add('inactive');
      } else {
        selDates.add(key); 
        btn.classList.remove('inactive');
      }
      refreshTable();
    };
    dateDiv.append(btn);
  });
  filterPanel.append(dateDiv);

  // ID filter
  const idDiv = document.createElement('div');
  const idInput = document.createElement('input');
  idInput.type = 'text'; 
  idInput.placeholder = 'ex : CH-RAC-1591381';
  idInput.oninput = refreshTable;
  if (initialId) {
    idInput.value = initialId;
  }
  idDiv.append(idInput);
  filterPanel.append(idDiv);

  // Bulk add button
  const addBtn = document.createElement('button');
  addBtn.textContent = '➕ Ajouter des chantiers en masse';
  addBtn.className = 'add-btn';
  addBtn.onclick = openBulkChantiersInterface;
  dlg.append(addBtn);

  // Table
  const tblC = document.createElement('div'); 
  tblC.className = 'table-container';
  const table = document.createElement('table');
  table.innerHTML = `
    <thead>
      <tr>
        <th>ID</th><th>Libellé</th><th>Statut</th>
        <th>Temps (h)</th><th>Fin</th><th>Actions</th>
      </tr>
    </thead>
    <tbody></tbody>`;
  tblC.append(table);
  dlg.append(tblC);
  const tbody = table.querySelector('tbody');

  // Helper pour créer les cellules
  function createCell(content, colspan = 1) {
    const td = document.createElement('td');
    td.colSpan = colspan;
    Object.assign(td.style, { padding: '8px', border: '1px solid #ddd' });
    if (typeof content === 'string' || typeof content === 'number') {
      td.textContent = content;
    } else {
      td.append(content);
    }
    return td;
  }

  // Fonction de rafraîchissement du tableau
  function refreshTable() {
    tbody.innerHTML = '';
    let list = Object.values(chantiers).filter(c => selStatuses.has(c.status));
    if (selPreps.size) list = list.filter(c => selPreps.has(c.preparateur));
    
    const now = new Date();
    list = list.filter(c => {
      const [d,m,y] = c.endDate.split('/');
      const over = new Date(`${y}-${m}-${d}`) < now;
      return (over && selDates.has('overdue')) || (!over && selDates.has('upcoming'));
    });
    
    const idf = idInput.value.trim().toLowerCase();
    if (idf) list = list.filter(c => c.id.toLowerCase().includes(idf));
    
    if (!list.length) {
      const tr = document.createElement('tr');
      tr.append(createCell('Aucun chantier.', 6));
      return tbody.append(tr);
    }
    
    list.forEach(ch => {
      const tr = document.createElement('tr');
      tr.append(createCell(ch.id));
      
      const tdL = createCell(ch.label);
      Object.assign(tdL.style, { whiteSpace: 'normal', wordBreak: 'break-word' });
      tr.append(tdL);
      
      tr.append(createCell(ch.status));
      tr.append(createCell((ch.prepTime/60).toFixed(2) + 'h'));
      tr.append(createCell(ch.endDate));
      
      const tdA = document.createElement('td');
      Object.assign(tdA.style, { display: 'flex', gap: '0.5rem', justifyContent: 'center' });
      
      ['✏️','✔️','❌'].forEach(icon => {
        const btn = document.createElement('button'); 
        btn.textContent = icon; 
        btn.className = 'action-btn';
        
        btn.onclick = () => {
          if (icon === '✏️') enterEditMode(tr, ch);
          if (icon === '✔️') { 
            ch.status = 'Clôturé'; 
            refreshTable(); 
            repartitionAutomatique();
            renderAll();
          }
          if (icon === '❌') { 
            ch.status = 'Annulé'; 
            refreshTable();  
            repartitionAutomatique();
            renderAll();
          }
        };
        tdA.append(btn);
      });
      tr.append(tdA);
      tbody.append(tr);
    });
  }

  // Mode édition inline
  function enterEditMode(tr, ch) {
    tr.innerHTML = ''; 
    tr.append(createCell(ch.id));
    
    const ta = document.createElement('textarea'); 
    ta.value = ch.label; 
    ta.style.width = '100%';
    tr.append(createCell(ta));
    
    const sl = document.createElement('select');
    statuses.forEach(s => {
      const o = new Option(s, s);
      if (s === ch.status) o.selected = true;
      sl.add(o);
    });
    tr.append(createCell(sl));
    
    const it = document.createElement('input'); 
    it.type = 'number'; 
    it.step = '0.25'; 
    it.value = (ch.prepTime/60).toFixed(2);
    it.style.width = '60px';
    tr.append(createCell(it));
    
    const idt = document.createElement('input'); 
    idt.type = 'date';
    const [d,m,y] = ch.endDate.split('/');
    idt.value = `${y}-${m}-${d}`;
    tr.append(createCell(idt));
    
    const td2 = document.createElement('td');
    Object.assign(td2.style, { display: 'flex', gap: '0.5rem', justifyContent: 'center' });
    
    ['💾','❌'].forEach(icon => {
      const btn = document.createElement('button'); 
      btn.textContent = icon; 
      btn.className = 'action-btn';
      
      btn.onclick = () => {
        if (icon === '💾') {
          ch.label = ta.value;
          ch.status = sl.value;
          ch.prepTime = Math.round(parseFloat(it.value)*60) || 0;
          const [Y,Mo,Da] = idt.value.split('-');
          ch.endDate = `${Da}/${Mo}/${Y}`;
          repartitionAutomatique();
          refreshTable(); 
          renderAll();
        } else {
          refreshTable();
        }
      };
      td2.append(btn);
    });
    tr.append(td2);
  }

  // Expose pour l'import en masse
  window.currentChantiersRefresh = refreshTable;

  // Rendu initial et affichage
  refreshTable();
  document.body.appendChild(overlay);
}

/**
 * Interface d'import en masse de chantiers
 */
function openBulkChantiersInterface() {
  const overlay = document.createElement('div'); 
  overlay.className = 'modal-overlay';
  const dlg = document.createElement('div');     
  dlg.className = 'modal-dialog';
  overlay.appendChild(dlg);

  // Header
  const header = document.createElement('div'); 
  header.className = 'modal-header';
  const title = document.createElement('h3');   
  title.textContent = 'Ajouter des chantiers en masse';
  const close = document.createElement('button'); 
  close.textContent = '✖️';
  close.onclick = () => overlay.remove();
  header.append(title, close);
  dlg.appendChild(header);

  // Sélecteur de préparateur
  const prepInput = document.createElement('input');
  prepInput.setAttribute('list','prep-list');
  prepInput.placeholder = 'Choisissez un préparateur';
  Object.assign(prepInput.style, {
    padding:'0.5rem', width:'100%', margin:'1rem 0',
    border:'1px solid #ccc', borderRadius:'4px'
  });
  
  const dl = document.createElement('datalist'); 
  dl.id = 'prep-list';
  Object.keys(preparateursMeta).forEach(n => {
    const o = document.createElement('option'); 
    o.value = n; 
    dl.append(o);
  });
  dlg.append(prepInput, dl);

  // Zone de saisie
  const ta = document.createElement('textarea');
  Object.assign(ta.style, { width:'100%', height:'200px', fontFamily:'monospace' });
  ta.placeholder = 'Collez 4 lignes par chantier…';
  dlg.appendChild(ta);

  // Boutons
  const btnDiv = document.createElement('div'); 
  btnDiv.style.marginTop = '1rem';
  
  const saveBtn = document.createElement('button'); 
  saveBtn.textContent = 'Importer';
  Object.assign(saveBtn.style, {
    padding:'0.5rem 1rem', marginRight:'0.5rem',
    background:'#007bff', color:'#fff', border:'none',
    borderRadius:'4px', cursor:'pointer'
  });
  
  const cancelBtn = document.createElement('button'); 
  cancelBtn.textContent = 'Annuler';
  Object.assign(cancelBtn.style, {
    padding:'0.5rem 1rem', background:'#6c757d',
    color:'#fff', border:'none', borderRadius:'4px', cursor:'pointer'
  });
  
  btnDiv.append(saveBtn, cancelBtn);
  dlg.appendChild(btnDiv);

  // Logique d'import
  saveBtn.onclick = () => {
    const prep = prepInput.value.trim();
    if (!prep || !preparateursMeta[prep]) {
      return alert('Choisissez un préparateur valide.');
    }
    
    const raw = ta.value.split(/\r?\n/);
    let i = 0;
    
    while (i < raw.length) {
      const idLine = raw[i].trim();
      if (!/^CH-/.test(idLine)) { i++; continue; }
      
      const label = raw[i+1]?.trim() || '';
      const statusC = raw[i+2]?.trim() || '';
      
      // Chercher la date dans les 3 lignes suivantes
      let endDate = '';
      for (let j = i+3; j <= i+6 && j < raw.length; j++) {
        const l = raw[j].trim();
        if (/^\d{2}\/\d{2}\/\d{4}$/.test(l)) {
          endDate = l; 
          break;
        }
      }
      
      const m = statusC.match(/(\d+)/);
      const prepTime = m ? parseInt(m[1],10)*60 : 0;
      const status = statusC.split(/\t+|\s{2,}/)[0] || '';
      
      if (idLine && label) {
        chantiers[idLine] = {
          id: idLine,
          label,
          status,
          prepTime,
          endDate,
          preparateur: prep
        };
      }
      
      // Avancer l'index
      if (endDate) {
        const next = raw.findIndex((_,k) => k>i+2 && raw[k].trim()===endDate);
        i = next >= 0 ? next+1 : i+4;
      } else {
        i += 4;
      }
    }
    
    // Rafraîchissement
    if (window.currentChantiersRefresh) window.currentChantiersRefresh();
    repartitionAutomatique();
    renderAll();
    overlay.remove();
  };

  cancelBtn.onclick = () => overlay.remove();
  document.body.appendChild(overlay);
}

/**
 * Initialise le module des chantiers
 */
function initChantiersModule() {
  const btn = document.getElementById('open-chantier-btn');
  if (btn) {
    btn.addEventListener('click', openChantiersInterface);
  } else {
    console.warn('Bouton open-chantier-btn non trouvé');
  }
}

// Auto-initialisation
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initChantiersModule);
} else {
  initChantiersModule();
}

// Module de planification automatique
// Gère l'algorithme de répartition automatique des chantiers

/**
 * Répartition automatique des chantiers sur les semaines
 * Distribue la charge de travail selon les disponibilités et échéances
 */
function repartitionAutomatique() {
  const now = new Date();
  // ✅ Corrige les erreurs liées au dimanche et fuseau horaire
  const nowUTC = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours(), now.getMinutes()));
  const nowFixed = new Date(nowUTC);
  if (nowFixed.getUTCDay() === 0) nowFixed.setUTCDate(nowFixed.getUTCDate() - 1); // si dimanche, recule d'un jour

  // 3️⃣ Construire un mapping weekKey → { week, idx }
  const weekMap = {};
  weeks.forEach((w, idx) => {
    const weekNo = String(w.start.getWeek()).padStart(2, '0');
    const key = `${w.start.getFullYear()}-W${weekNo}-1`;
    weekMap[key] = { week: w, idx };
  });

  // 4️⃣ Déterminer l'indice et la clé de la semaine courante
  const currentWeekIdx = weeks.findIndex(w => w.start <= nowFixed && w.end >= nowFixed);
  if (currentWeekIdx === -1) {
    console.warn("⚠️ La semaine courante n'a pas été trouvée dans la liste `weeks`. Abandon de la répartition.");
    return;
  }
  const currentWeekKey = Object.keys(weekMap).find(key => weekMap[key].idx === currentWeekIdx);

  // 4.5️⃣ Déprogrammation des planifications pour chantiers hors statut actif
  Object.values(chantiers).forEach(ch => {
    if (!['Nouveau', 'Prépa. en cours'].includes(ch.status) && ch.planification) {
      Object.entries(ch.planification).forEach(([key]) => {
        if (weekMap[key] && weekMap[key].idx >= currentWeekIdx) {
          delete ch.planification[key];
        }
      });
    }
  });

  // 5️⃣ Pour chaque préparateur
  Object.keys(data).forEach((name) => {
    const dispoParSemaine = {};
    Object.keys(weekMap).forEach((key) => {
      const stored = data[name]?.[key];
      dispoParSemaine[key] = stored
        ? (typeof stored === 'object' ? stored.minutes : stored)
        : 0;
    });

    const chantierList = Object.values(chantiers)
      .filter(ch => ch.preparateur === name && ['Nouveau', 'Prépa. en cours'].includes(ch.status))
      .sort((a, b) => parseDateFR(a.endDate) - parseDateFR(b.endDate));
    if (!chantierList.length) return;

    const planWeeks = weeks.slice(currentWeekIdx);

    chantierList.forEach(ch => {
      const oldPlanif = ch.planification || {};
      const pastPlanif = Object.entries(oldPlanif)
        .filter(([key]) => weekMap[key] && weekMap[key].idx < currentWeekIdx)
        .reduce((acc, [key, val]) => ({ ...acc, [key]: val }), {});
      ch.planification = pastPlanif;
      const done = Object.values(pastPlanif).reduce((sum, v) => sum + v, 0);
      ch.ChargeRestante = Math.max(0, ch.prepTime - done);
    });

    chantierList.forEach(ch => {
      let remainingToPlan = ch.prepTime - Object.values(ch.planification).reduce((s, v) => s + v, 0);
      planWeeks.forEach(w => {
        if (remainingToPlan <= 0) return;
        const wkNo = String(w.start.getWeek()).padStart(2, '0');
        const key = `${w.start.getFullYear()}-W${wkNo}-1`;
        const dispo = dispoParSemaine[key] || 0;
        const already = chantierList.reduce((s, c) => s + (c.planification[key] || 0), 0);
        const free = Math.max(0, dispo - already);
        const toPlan = Math.min(remainingToPlan, free);
        if (toPlan > 0) {
          ch.planification[key] = (ch.planification[key] || 0) + toPlan;
          remainingToPlan -= toPlan;
        }
      });
    });
  });

  Object.values(chantiers).forEach(ch => {
    delete ch.tempsRestant;
  });
}

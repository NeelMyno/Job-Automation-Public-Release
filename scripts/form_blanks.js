() => {
  // Owner of the handover sweep: .claude/commands/wave.md stage 7 item 4.
  // Read this file and pass its whole text as the `function` argument of evaluate_script, on every open tab.
  // Returns every visible question on the page that holds no answer, read by its label.
  // `scanned` is how many fields it looked at. `unreadableFrames` counts frames it could not look inside:
  // a form in one of those was NOT swept, so a clean result there proves nothing.
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const skip = el => /recaptcha|hcaptcha|captcha|g-recaptcha/i.test((el.name || '') + (el.id || '') + (typeof el.className === 'string' ? el.className : ''));
  const clean = t => (t || '').replace(/\s+/g, ' ').trim();
  const labelOf = el => {
    const id = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (id) return clean(id.innerText);
    const box = el.closest('[class*=fieldEntry],fieldset,.field,[class*=question],[class*=Field],[data-testid]');
    const l = box && box.querySelector('label,legend,[class*=label]');
    return clean(l ? l.innerText : (el.getAttribute('aria-label') || el.placeholder || el.name || ''));
  };
  // A radio's own <label> is its option ("Yes"), so a group is named by its question.
  const groupLabel = el => {
    const fs = el.closest('fieldset'), lg = fs && fs.querySelector('legend');
    if (lg) return clean(lg.innerText);
    const rg = el.closest('[role=radiogroup]');
    if (rg) {
      const by = rg.getAttribute('aria-labelledby'), n = by && document.getElementById(by);
      if (n) return clean(n.innerText);
      if (rg.getAttribute('aria-label')) return clean(rg.getAttribute('aria-label'));
    }
    const box = el.closest('[class*=fieldEntry],.field,[class*=question],[class*=Field],[data-testid]');
    const l = box && box.querySelector('legend,[class*=label],label:not(:has(input))');
    return clean(l ? l.innerText : (el.name || labelOf(el)));
  };
  const blanks = [];
  let scanned = 0;
  document.querySelectorAll('input[type=text],input[type=email],input[type=tel],input[type=url],input[type=number],input[type=date],input:not([type]),textarea').forEach(el => {
    if (!vis(el) || skip(el) || el.closest('[class*=select__],[class*=Select]') || el.getAttribute('role') === 'combobox') return;
    scanned++;
    if (!el.value.trim()) blanks.push(['text', labelOf(el).slice(0, 160), !!el.required]);
  });
  document.querySelectorAll('select').forEach(el => { if (vis(el)) { scanned++; if (!el.value) blanks.push(['select', labelOf(el).slice(0, 160), !!el.required]); } });
  // radio groups with nothing checked
  const groups = {};
  document.querySelectorAll('input[type=radio]').forEach(r => { const k = r.name || r.id; (groups[k] = groups[k] || []).push(r); });
  Object.values(groups).forEach(g => { if (g.some(vis) || g.some(r => vis(r.parentElement))) { scanned++; if (!g.some(r => r.checked)) blanks.push(['radio', groupLabel(g[0]).slice(0, 160), g.some(r => r.required)]); } });
  // Yes/No button pairs with neither selected
  document.querySelectorAll('[class*=fieldEntry],[role=group],[class*=question]').forEach(f => {
    const bs = [...f.querySelectorAll('button')].filter(b => /^(yes|no)$/i.test(b.innerText.trim()));
    if (bs.length !== 2 || !bs.some(vis)) return;
    scanned++;
    if (!bs.some(b => /active|selected/i.test(b.className) || b.getAttribute('aria-pressed') === 'true')) blanks.push(['yesno', labelOf(bs[0]).slice(0, 160), true]);
  });
  // comboboxes showing only a placeholder. A plain input styled "form-control" is not one.
  document.querySelectorAll('[class*=select__control],[class*=-control]').forEach(c => {
    if (!vis(c) || c.matches('input,select,textarea,button')) return;
    const box = c.querySelector('input[role=combobox],input[aria-autocomplete],[aria-haspopup=listbox]');
    if (!box && !/select__control/.test(c.className)) return;
    scanned++;
    const has = c.querySelector('[class*=single-value],[class*=singleValue],[class*=multi-value],[class*=multiValue]');
    if (!has) blanks.push(['combo', labelOf(c.querySelector('input') || c).slice(0, 160), false]);
  });
  // checkbox groups (fieldset) with nothing checked
  document.querySelectorAll('fieldset').forEach(fs => { const cb = fs.querySelectorAll('input[type=checkbox]'); if (cb.length && vis(fs)) { scanned++; if (![...cb].some(c => c.checked)) blanks.push(['checkbox', clean(fs.querySelector('legend')?.innerText).slice(0, 160), false]); } });
  const files = [...document.querySelectorAll('input[type=file]')].map(f => f.files[0] ? f.files[0].name : 'EMPTY');
  // Some forms remove the file input after an upload and print the file name as text instead.
  const fileNamesOnPage = [...new Set(document.body.innerText.match(/[\w .()-]{1,80}\.(pdf|docx?|rtf)\b/gi) || [])].map(clean).slice(0, 10);
  const unreadableFrames = [...document.querySelectorAll('iframe')].filter(f => { if (!vis(f)) return false; try { return !f.contentDocument; } catch (e) { return true; } }).length;
  const seen = new Set();
  return { url: location.href.slice(0, 90), submitted: /successfully submitted|application (was )?received|thank you for applying/i.test(document.body.innerText), scanned, unreadableFrames, files, fileNamesOnPage, blanks: blanks.filter(b => { const k = b[0] + b[1]; return !seen.has(k) && seen.add(k); }) };
}

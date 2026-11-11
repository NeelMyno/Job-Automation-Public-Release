() => {
  // Owner: .claude/commands/wave.md stage 7 items 4 and 7. Read this file and pass its whole text as the `function`
  // argument of evaluate_script on every open tab, with filePath set to <dir>/<tab number>.json. Then run
  // `python3 scripts/why_check.py --live <dir>` and `python3 scripts/work_history_check.py --live <dir>`.
  // Returns every filled free-text answer on the page with its question AND its help text, read from the live form.
  // Any filled textarea counts; a one-line input counts from 40 characters, so names and emails stay out.
  const out = [];
  const txt = n => (n ? n.innerText : '').replace(/\s+/g, ' ').trim();
  document.querySelectorAll('textarea, input[type=text], input[type=url], input:not([type])').forEach(el => {
    const v = el.value.trim();
    if (!v || (el.tagName !== 'TEXTAREA' && v.length < 40) || /recaptcha|captcha/i.test(el.name + el.id)) return;
    let label = el.id ? txt(document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) : '';
    let box = el.parentElement, help = '';
    for (let i = 0; i < 6 && box; i++, box = box.parentElement) {
      const t = txt(box).replace(el.value.replace(/\s+/g, ' ').trim(), '').trim();
      if (t.length > 3) { if (!label) label = t; help = t; break; }
    }
    const desc = (el.getAttribute('aria-describedby') || '').split(' ').filter(Boolean).map(id => txt(document.getElementById(id))).join(' ');
    out.push({ label: label.slice(0, 200), help: (desc || help).slice(0, 300), value: el.value });
  });
  return { url: location.href, submitted: /successfully submitted|received your submitted|application (was )?received|thank you for applying/i.test(document.body.innerText), fields: out };
}

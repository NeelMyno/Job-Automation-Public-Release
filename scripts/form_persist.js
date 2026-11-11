() => {
  // Owner: .claude/commands/wave.md stage 7 items 4 and 7. Will every answer on this form survive a re-render?
  // Read this file and pass its whole text as the `function` argument of evaluate_script, on every open tab.
  // A value set straight into the DOM shows on screen but never reaches a controlled React field's state, and the
  // first edit anywhere else on the page puts the stored value back. This compares, for every controlled field,
  // what the screen shows with what React holds. Any entry in `mismatched` is a value that will revert or never send.
  // `controlled` is how many React-controlled fields it found. 0 means this form has none this check can read,
  // so a clean result there says nothing: rely on the DOM read-back instead.
  const out = [];
  let controlled = 0;
  document.querySelectorAll('textarea, input:not([type=hidden]):not([type=file]):not([type=checkbox]):not([type=radio])').forEach(el => {
    if (/recaptcha|captcha/i.test(el.name + el.id)) return;
    const k = Object.keys(el).find(x => x.startsWith('__reactProps'));
    if (!k) return;
    const p = el[k];
    if (!p || !('value' in p) || p.value === undefined || p.value === null) return;   // uncontrolled: the DOM is the truth
    controlled++;
    const state = String(p.value), shown = el.value;
    if (state !== shown) {
      let lab = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      lab = (lab ? lab.innerText : (el.getAttribute('aria-label') || el.name || el.closest('div')?.innerText || '')).replace(/\s+/g, ' ').trim();
      out.push({ field: lab.slice(0, 70), shown: shown.slice(0, 45), stored: state.slice(0, 45), shownLen: shown.length, storedLen: state.length });
    }
  });
  return { url: location.href.slice(0, 80), controlled, mismatched: out };
}

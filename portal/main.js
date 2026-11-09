
document.documentElement.classList.add('js');

const line = document.getElementById('scroll-line');
const motionButton = document.getElementById(
  'motion-control'
);
const motionLabel = document.getElementById('motion-label');
const filterButtons = Array.from(
  document.querySelectorAll('[data-filter]')
);
const cardWrappers = Array.from(
  document.querySelectorAll('[data-unit]')
);
const cards = Array.from(document.querySelectorAll('.unit-card'));

function updateScrollLine() {
  if (!line) return;
  const total = document.documentElement.scrollHeight - window.innerHeight;
  const progress =
    total > 0 ? Math.min(100, Math.max(0, (window.scrollY / total) * 100)) : 0;
  line.style.width = String(progress) + '%';
}
window.addEventListener('scroll', updateScrollLine, { passive: true });
window.addEventListener('resize', updateScrollLine);
updateScrollLine();

if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(
    entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.08, rootMargin: '0px 0px -25px 0px' }
  );
  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
} else {
  document
    .querySelectorAll('.reveal')
    .forEach(el => el.classList.add('is-visible'));
}

filterButtons.forEach(button => {
  button.addEventListener('click', () => {
    const filter = button.dataset.filter || 'all';
    filterButtons.forEach(other => {
      const selected = other === button;
      other.classList.toggle('active', selected);
      other.setAttribute('aria-pressed', String(selected));
    });
    cardWrappers.forEach(wrapper => {
      const visible = filter === 'all' || wrapper.dataset.unit === filter;
      wrapper.classList.toggle('filter-hidden', !visible);
      wrapper.setAttribute('aria-hidden', String(!visible));
    });
    updateScrollLine();
  });
});

const systemPrefersReducedMotion = window.matchMedia(
  '(prefers-reduced-motion: reduce)'
).matches;
let paused = systemPrefersReducedMotion;
try {
  const saved = window.localStorage.getItem('ganoh-portal-motion');
  if (saved === 'off') paused = true;
  if (saved === 'on') paused = false;
} catch {
  // Storage may be unavailable in private browsing; the toggle still works.
}
function updateMotion() {
  document.body.classList.toggle('motion-off', paused);
  if (motionButton) {
    motionButton.setAttribute('aria-pressed', String(paused));
    motionButton.setAttribute(
      'aria-label',
      paused ? 'Ativar animações' : 'Pausar animações'
    );
  }
  if (motionLabel)
    motionLabel.textContent = paused ? 'Ativar animações' : 'Pausar animações';
}
if (motionButton) {
  motionButton.addEventListener('click', () => {
    paused = !paused;
    try {
      window.localStorage.setItem('ganoh-portal-motion', paused ? 'off' : 'on');
    } catch {
      // No persistence required for a functional toggle.
    }
    updateMotion();
  });
}
updateMotion();

cards.forEach(card => {
  card.addEventListener('pointermove', (event) => {
    if (paused || event.pointerType === 'touch' || window.innerWidth < 780)
      return;
    const rect = card.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    card.style.setProperty('--ry', String((x - 0.5) * 5) + 'deg');
    card.style.setProperty('--rx', String((0.5 - y) * 5) + 'deg');
    card.style.setProperty('--spot-x', String(x * 100) + '%');
    card.style.setProperty('--spot-y', String(y * 100) + '%');
  });
  card.addEventListener('pointerleave', () => {
    card.style.setProperty('--rx', '0deg');
    card.style.setProperty('--ry', '0deg');
  });
});

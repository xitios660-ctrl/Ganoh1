'use strict';

(function () {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced) return;

  document.documentElement.classList.add('js');
  const reveal = Array.from(document.querySelectorAll('.reveal'));

  if (!('IntersectionObserver' in window)) {
    reveal.forEach(function (element) { element.classList.add('visible'); });
    return;
  }

  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.07, rootMargin: '0px 0px -20px 0px' });

  reveal.forEach(function (element) { observer.observe(element); });
})();

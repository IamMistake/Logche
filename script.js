(function () {
  'use strict';

  var tocRail = document.getElementById('toc-rail');
  var tocToggle = document.getElementById('toc-toggle');
  if (tocRail && tocToggle) {
    tocToggle.addEventListener('click', function () {
      var collapsed = tocRail.classList.toggle('is-collapsed');
      tocToggle.setAttribute('aria-expanded', String(!collapsed));
    });
  }

  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc-link'));
  var sections = tocLinks.map(function (link) {
    return { link: link, section: document.getElementById(link.getAttribute('href').slice(1)) };
  }).filter(function (item) { return item.section; });

  function setActiveSection() {
    var current = sections[0];
    sections.forEach(function (item) {
      if (item.section.getBoundingClientRect().top <= 180) current = item;
    });
    sections.forEach(function (item) { item.link.classList.toggle('is-active', item === current); });
  }
  window.addEventListener('scroll', setActiveSection, { passive: true });
  setActiveSection();

  var worksToggle = document.getElementById('works-toggle');
  var worksClose = document.getElementById('works-close');
  var worksDropdown = document.getElementById('moreWorksDropdown');
  function closeWorks() {
    if (!worksDropdown || !worksToggle) return;
    worksDropdown.hidden = true;
    worksToggle.classList.remove('active');
    worksToggle.setAttribute('aria-expanded', 'false');
  }
  if (worksToggle) worksToggle.addEventListener('click', function () {
    var open = worksDropdown.hidden;
    worksDropdown.hidden = !open;
    worksToggle.classList.toggle('active', open);
    worksToggle.setAttribute('aria-expanded', String(open));
  });
  if (worksClose) worksClose.addEventListener('click', closeWorks);
  document.addEventListener('click', function (event) {
    var container = document.querySelector('.more-works-container');
    if (container && !container.contains(event.target)) closeWorks();
  });
  document.addEventListener('keydown', function (event) { if (event.key === 'Escape') closeWorks(); });
})();

/**
 * Scroll-driven story panel visibility (IntersectionObserver).
 */
(function () {
  const panels = document.querySelectorAll(".story-panel[data-story]");
  if (!panels.length || !("IntersectionObserver" in window)) {
    panels.forEach((el) => el.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
        }
      });
    },
    { root: null, rootMargin: "0px 0px -12% 0px", threshold: 0.15 },
  );

  panels.forEach((panel) => observer.observe(panel));
})();

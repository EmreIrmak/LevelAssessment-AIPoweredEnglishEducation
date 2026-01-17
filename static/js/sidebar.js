(() => {
  const STORAGE_KEY = "english_ai_sidebar_collapsed";

  const shell = document.querySelector(".app-shell");
  if (!shell) return;

  const sidebar = document.getElementById("sidebar");
  const toggleBtn = document.getElementById("sidebarToggle");

  const applyState = (collapsed) => {
    shell.classList.toggle("sidebar-collapsed", collapsed);

    if (toggleBtn) {
      toggleBtn.setAttribute("aria-expanded", (!collapsed).toString());
      toggleBtn.setAttribute("aria-pressed", collapsed.toString());
    }
  };

  let collapsed = false;
  try {
    collapsed = localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    collapsed = false;
  }

  applyState(collapsed);

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const next = !shell.classList.contains("sidebar-collapsed");
      applyState(next);
      try {
        localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        // ignore
      }
    });
  }
})();

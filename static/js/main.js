// Sidebar toggle (mobile) and delete-confirmation modal wiring.
document.addEventListener("DOMContentLoaded", () => {
  const sb = document.getElementById("sidebar");
  const t = document.getElementById("sidebarToggle");
  if (t) t.addEventListener("click", () => sb.classList.toggle("open"));
  const modal = document.getElementById("confirmModal");
  if (modal) modal.addEventListener("show.bs.modal", e => {
    const b = e.relatedTarget;
    document.getElementById("confirmForm").action = b.dataset.action;
    document.getElementById("confirmText").textContent = b.dataset.label || "this item";
  });
});

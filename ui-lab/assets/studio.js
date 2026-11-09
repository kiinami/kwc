document.querySelectorAll("[data-burger]").forEach((button) => {
  button.addEventListener("click", () => {
    const menu = button.closest(".workspace")?.querySelector("[data-menu]");
    if (menu) menu.hidden = !menu.hidden;
  });
});

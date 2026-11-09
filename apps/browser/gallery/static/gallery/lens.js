const image = document.getElementById("lens-image");
if (image) {
  const load = (element) => {
    image.dataset.failed = "";
    image.src = element.dataset.original;
  };
  image.addEventListener("error", () => {
    if (image.dataset.failed) return;
    image.dataset.failed = "1";
    image.src = image.dataset.fallback;
  });
  image.src = image.dataset.original;
  document.querySelectorAll("button.variant").forEach((button) => {
    button.addEventListener("click", () => load(button));
  });
}

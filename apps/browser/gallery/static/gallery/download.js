(function () {
  const formats = {
    jpeg: { mime: "image/jpeg", extension: "jpg" },
    webp: { mime: "image/webp", extension: "webp" },
    png: { mime: "image/png", extension: "png" },
  };

  async function convert(blob, format, maxEdge) {
    const spec = formats[format];
    try {
      const bitmap = await createImageBitmap(blob);
      const scale = maxEdge ? Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height)) : 1;
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const encoded = await new Promise((resolve, reject) => {
        canvas.toBlob(
          (result) => (result ? result.arrayBuffer().then((buffer) => resolve(new Uint8Array(buffer))) : reject(new Error("encode failed"))),
          spec.mime,
          0.92,
        );
      });
      return { bytes: encoded, extension: spec.extension };
    } catch (error) {
      const bytes = new Uint8Array(await blob.arrayBuffer());
      return { bytes, extension: "jxl" };
    }
  }

  async function libraryItems(scope) {
    const response = await fetch(`/downloads.json?curated=${scope === "curated" ? "1" : "0"}`);
    return (await response.json()).images;
  }

  function folderItems() {
    const boxes = [...document.querySelectorAll(".download-pick")];
    const selected = boxes.filter((box) => box.checked);
    return (selected.length ? selected : boxes).map((box) => ({
      name: box.dataset.name,
      url: box.dataset.url,
    }));
  }

  async function run(form) {
    const format = form.querySelector("[name=format]").value;
    const resolution = form.querySelector("[name=resolution]").value;
    const maxEdge = resolution === "original" ? null : Number(resolution);
    const progress = form.querySelector("[data-progress]");
    const cancel = form.querySelector("[data-cancel]");
    let cancelled = false;

    const items =
      form.dataset.download === "library"
        ? await libraryItems(form.querySelector("[name=scope]").value)
        : folderItems();

    if (!items.length) {
      progress.textContent = "Nothing selected.";
      return;
    }
    if (items.length > 100 && !window.confirm(`Convert ${items.length} images? This may be slow on a phone.`)) {
      return;
    }

    cancel.hidden = false;
    cancel.onclick = () => {
      cancelled = true;
    };
    const zip = new ZipWriter();
    let fallback = false;
    try {
      for (let index = 0; index < items.length; index += 1) {
        if (cancelled) break;
        progress.textContent = `${index + 1} / ${items.length}`;
        const item = items[index];
        const response = await fetch(item.url);
        if (!response.ok) throw new Error(`cannot fetch ${item.name}`);
        const converted = await convert(await response.blob(), format, maxEdge);
        fallback = fallback || converted.extension === "jxl";
        zip.add(item.name.replace(/\.jxl$/i, `.${converted.extension}`), converted.bytes);
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    } finally {
      cancel.hidden = true;
    }
    if (cancelled) {
      progress.textContent = "Cancelled.";
      return;
    }
    const blob = zip.finish();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "wallpapers.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 30000);
    progress.textContent = fallback
      ? `Done (${items.length} files; this browser cannot decode JXL, originals were zipped).`
      : `Done (${items.length} files).`;
  }

  document.querySelectorAll("[data-download]").forEach((form) => {
    const selectAll = form.querySelector("[data-select-all]");
    if (selectAll) {
      selectAll.addEventListener("change", () => {
        document.querySelectorAll(".download-pick").forEach((box) => {
          box.checked = selectAll.checked;
        });
      });
    }
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      run(form).catch((error) => {
        const progress = form.querySelector("[data-progress]");
        if (progress) progress.textContent = error.message;
      });
    });
  });
})();

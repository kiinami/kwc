(() => {
  const params = new URLSearchParams(location.search);
  const embedded = params.get("embed") === "1";
  if (embedded) document.documentElement.classList.add("embed");

  const screens = { browser: ["library", "frame"], manager: ["folders", "jobs"] };
  const state = {
    app: screens[params.get("app")] ? params.get("app") : "browser",
    screen: null,
    view: params.get("view") === "mobile" ? "mobile" : "desktop",
  };
  const requested = params.get("screen");
  state.screen = screens[state.app].includes(requested) ? requested : screens[state.app][0];

  const preview = document.querySelector(".preview");
  const deviceWrap = document.querySelector(".device-wrap");
  const iframe = document.querySelector(".device iframe");

  const query = (extra = {}) => {
    const p = new URLSearchParams({ app: state.app, screen: state.screen, view: state.view, ...extra });
    return `${location.pathname}?${p.toString()}`;
  };

  function apply() {
    document.querySelectorAll("[data-app]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.app === state.app));
    });
    document.querySelectorAll("[data-screens]").forEach((group) => {
      group.hidden = group.dataset.screens !== state.app;
    });
    document.querySelectorAll("[data-screen]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.screen === state.screen));
    });
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.view === state.view));
    });
    document.querySelectorAll("[data-app-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.appPanel !== state.app;
    });
    document.querySelectorAll("[data-screen-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.screenPanel !== state.screen;
    });

    if (embedded) return;
    if (state.view === "mobile") {
      preview.hidden = true;
      deviceWrap.hidden = false;
      if (iframe) iframe.src = query({ embed: "1" });
    } else {
      preview.hidden = false;
      deviceWrap.hidden = true;
    }
  }

  document.querySelectorAll("[data-app]").forEach((button) => {
    button.addEventListener("click", () => {
      state.app = button.dataset.app;
      state.screen = screens[state.app][0];
      history.replaceState(null, "", query());
      apply();
    });
  });

  document.querySelectorAll("[data-screen]").forEach((button) => {
    button.addEventListener("click", () => {
      state.screen = button.dataset.screen;
      history.replaceState(null, "", query());
      apply();
    });
  });

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      history.replaceState(null, "", query());
      apply();
    });
  });

  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data || !screens[data.app]) return;
    state.app = data.app;
    state.screen = screens[data.app].includes(data.screen) ? data.screen : screens[data.app][0];
    apply();
  });

  apply();
})();

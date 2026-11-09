# KWC UI lab

Three browsable design directions for the browser and the manager. This is a
throwaway static prototype: once a direction (or a mix) is chosen, the winner is
integrated into the real Django apps and this folder can go away.

## Run

```sh
python -m http.server 8090 -d ui-lab
```

- Desktop: <http://localhost:8090/>
- Phone (same LAN): `http://<your-host-ip>:8090/`

No build step. Framework CSS is vendored under `assets/vendor/` so the lab works
offline.

## Directions

| | Direction | Framework | Idea |
|---|---|---|---|
| 01 | **Noir** | Pico CSS 2 | Dark room. Images dominate; chrome is hairlines and small type. |
| 02 | **Paper** | Bootstrap 5.3 | Print room. Serif display, matte frames, warm ink on cream. |
| 03 | **Studio** | Bulma 1.0 | Working tool. Cool neutrals, one indigo accent, dense but calm. |

Each direction has:

- **Browser** — library and frame view (the public, read-only side).
- **Manager** — folders and jobs (the private, operational side).
- **Desktop / Mobile** — the mobile toggle loads a real 390 × 844 iframe, not a
  screenshot, so media queries and layouts are genuine.

The lab bar is outside the design and will not ship. It is marked by the `LAB`
label in the page title and a separate visual treatment.

## What is shared

The three directions deliberately keep the same product skeleton:

- one header anatomy per audience;
- the same filter, chip, status stamp, progress bar, table, and row language;
- the same responsive intent: two-column mobile grids, collapsed navigation,
  stacked split views, 44 px tap targets;
- the browser never grows write actions; the manager carries stats, destructive
  actions, job progress, and error detail.

What changes is temperament: palette, type, density, and how much the chrome
disappears around the images.

## Choosing

Name a direction, or mix parts, for example:

- “Noir's grid, Paper's type.”
- “Studio's manager, but the browser should feel like Paper.”
- “Keep the Noir frame view and the Paper library.”

Then the integration work is: extract the tokens and components into `libs/ui`,
wire both apps to one base template, and bring the existing download/import/job
behaviour along without changing it.

## Sample content

`data/test-wallpapers` currently holds one imported film. The lab reuses its
frames across mock folders so grids and type can be judged with real imagery.
Titles, years, counts, and jobs are placeholders. Rebuild the images with:

```sh
uv run --group dev python ui-lab/tools/build_images.py
```

## Layout

```
ui-lab/
  index.html             direction chooser + comparison
  noir.html              direction 01
  paper.html             direction 02
  studio.html            direction 03
  assets/
    lab.css, lab.js      lab chrome only (not part of the design)
    noir.css, paper.css, studio.css
    shots/               screenshots used on the index
    vendor/              Pico, Bootstrap, Bulma (MIT, headers preserved)
    images/              WebP derivatives of the imported archive
  tools/build_images.py  regenerates assets/images
```

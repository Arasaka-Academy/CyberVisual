# CyberVisual on GitHub Pages

The site includes the IMX477 HQ assembly figure and the Jetson Nano 3D lesson:

- Site: https://arasaka-academy.github.io/CyberVisual/
- Interactive lesson: https://arasaka-academy.github.io/CyberVisual/lesson/
- Offline lesson: https://arasaka-academy.github.io/CyberVisual/lesson/lesson.html
- Figure: https://arasaka-academy.github.io/CyberVisual/figure/
- Dark theme: https://arasaka-academy.github.io/CyberVisual/figure/index-dark.html
- Print layout: https://arasaka-academy.github.io/CyberVisual/print/IMX477-HQ-print-layout.3mf
- Complete kit: https://arasaka-academy.github.io/CyberVisual/IMX477-HQ-print-kit.zip

The site root offers the lesson, assembly figure and downloads. The published directory preserves the figure's existing paths, including 3MF, SVG, assembly instructions and validation downloads. The lesson runs entirely in the browser; its JavaScript, models and styles are served from this site, and its offline HTML embeds those assets.

## Local preview

With Node.js 22.12 or later and Python 3.9 or later, build the lesson and stage the complete site from the repository root:

```sh
npm ci --prefix viz-jetson-pan-tilt/app
npm test --prefix viz-jetson-pan-tilt/app
npm run build --prefix viz-jetson-pan-tilt/app
python3 scripts/build_figure_pages.py --lesson-dist viz-jetson-pan-tilt/app/dist
python3 -m http.server 8001 --directory _site
```

Open `http://127.0.0.1:8001/`. The staging script validates local HTML links and rejects domain-root paths that would break below `/CyberVisual/`. `_site/` is ignored by Git; to stage another preview, choose a fresh directory with `--output`.

Omit `--lesson-dist` to stage only the original figure and downloads, retaining the original root redirect. A supplied lesson directory must already contain the complete Vite build and offline HTML; staging fails if required files are missing.

For full lesson interaction checks, run `npm run test:browser` from the lesson's `app/` directory. `LESSON_URL` selects the local or published lesson URL; `LESSON_EVIDENCE_DIR` selects a separate report/screenshot directory. See the [lesson run guide](../viz-jetson-pan-tilt/README.md).

If the CAD or figure sources change, regenerate the kit and figure first using the [kit instructions](../models/imx477-hq/README.zh-CN.md#可编辑源码), then commit the generated outputs. Pages publishes those committed artifacts; the workflow does not regenerate CAD or alter the downloadable kit.

## Deployment

The `Deploy CyberVisual to GitHub Pages` workflow runs on pushes to `main` that change the kit, lesson, site homepage, staging script or workflow. It also supports manual runs from the repository's Actions tab.

Repository Settings → Pages uses **GitHub Actions** as its source. The workflow installs locked lesson dependencies, runs state/asset tests, builds the normal and offline lesson, stages and checks the combined site, uploads a Pages artifact, then deploys through the `github-pages` environment. Action versions are pinned to commit SHAs. Only the deploy job receives Pages write and OIDC permissions.

After a successful deployment, verify the live homepage, lesson interactions and original figure/download links. Compare deployed HTML and model bytes against the built assets. No printer configuration or G-code is supplied by the site; the lesson remains a browser simulation with illustrative UART/CSI/power interfaces.

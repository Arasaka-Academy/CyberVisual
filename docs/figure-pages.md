# Figure on GitHub Pages

The IMX477 HQ assembly figure is published at:

- Site: https://arasaka-academy.github.io/CyberVisual/
- Figure: https://arasaka-academy.github.io/CyberVisual/figure/
- Dark theme: https://arasaka-academy.github.io/CyberVisual/figure/index-dark.html
- Print layout: https://arasaka-academy.github.io/CyberVisual/print/IMX477-HQ-print-layout.3mf
- Complete kit: https://arasaka-academy.github.io/CyberVisual/IMX477-HQ-print-kit.zip

The site root redirects to `figure/`. The published directory preserves the relative paths used by the figure, including 3MF, SVG, assembly instructions and validation downloads. The page is standalone and uses no backend or external JavaScript dependencies.

## Local preview

From the repository root, stage the committed HTML, SVG, PNG and print files into a new directory with Python 3.9 or later:

```sh
python3 scripts/build_figure_pages.py
python3 -m http.server 8001 --directory _site
```

Open `http://127.0.0.1:8001/`. The staging script validates local HTML links and rejects domain-root paths that would break below `/CyberVisual/`. `_site/` is ignored by Git; to stage another preview, choose a fresh directory with `--output`.

If the CAD or figure sources change, regenerate the kit and figure first using the [kit instructions](../models/imx477-hq/README.zh-CN.md#可编辑源码), then commit the generated outputs. Pages publishes those committed artifacts; the workflow does not regenerate CAD or alter the downloadable kit.

## Deployment

The `Deploy figure to GitHub Pages` workflow runs on pushes to `main` that change the kit, the staging script or the workflow itself. It also supports manual runs from the repository's Actions tab.

Repository Settings → Pages uses **GitHub Actions** as its source. The workflow stages and checks the site, uploads a Pages artifact, then deploys through the `github-pages` environment. Action versions are pinned to commit SHAs. Only the deploy job receives Pages write and OIDC permissions.

After a successful deployment, verify the live figure and download links. No printer configuration or G-code is supplied by the site.

# Thesis Build Notes

This thesis currently uses **Tectonic** as the normal local build tool.
Do not use TeXstudio as the primary build path for now, because the local TeX Live installation has missing XeLaTeX/pdfLaTeX packages.

## Normal Build

From the project root, run:

```bash
./scripts/build-thesis.sh
```

The script will:

- enter `thesis/`
- run `tectonic main.tex`
- write generated files to `thesis/build/`
- open `thesis/build/main.pdf` with the default PDF viewer through `xdg-open`

## Needed Packages

On Arch Linux, install Tectonic:

```bash
sudo pacman -S tectonic
```

The PDF viewer is opened through `xdg-open`, which is normally already available on desktop Linux.

The thesis uses local Noto fonts for Macedonian Cyrillic text.
If the fonts are missing, install them:

```bash
sudo pacman -S noto-fonts
```

## Manual Tectonic Build

If you want to build without the script:

```bash
cd thesis
mkdir -p build
tectonic --outdir build main.tex
xdg-open build/main.pdf
```

## Cleaning Stale Files

If a stale auxiliary file causes an error, clean generated files and compile again:

```bash
cd thesis
rm -rf build
mkdir -p build
tectonic --outdir build main.tex
xdg-open build/main.pdf
```

## Current LaTeX Setup

The current thesis source is intentionally minimal.
It avoids `biblatex`, `hyperref`, and other heavier packages until the local TeX setup is stable.

References are currently represented with a simple `thebibliography` placeholder.
Later, after the thesis structure stabilizes, references can be moved back to `biblatex` or another bibliography workflow.

## Writing Style

Writing rules are defined in `thesis/WRITING_STYLE.md`.
Use that file as the source of truth for thesis tone, language, structure, development evidence, visual material, Excalidraw/Python visualization workflow, references, and change review.

Important defaults:

- The thesis is project-based, not diary-based.
- Main prose is Macedonian only.
- English is allowed only for technical terms, technologies, model names, APIs, package names, paper titles, and reference metadata.
- Visuals can be created with Excalidraw or Python visualization libraries.
- Subagents and web search can be used to find academic references.

## TeXstudio Note

TeXstudio can still be used as an editor.
For compiling, use the script above instead of TeXstudio's build button.

If you later want TeXstudio compilation, the local TeX Live installation should be fixed with packages such as:

```bash
sudo pacman -S texlive-xetex texlive-langcyrillic texlive-fontsrecommended
```

After that, TeXstudio can be configured to use XeLaTeX.

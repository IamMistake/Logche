# Thesis Writing Style

## Core Direction

This thesis is project-based.
It should present Logche as a software engineering graduation project, not as a raw development diary.

The main thesis should explain the problem, motivation, architecture, implementation, evaluation, design decisions, tradeoffs, and results.
Development history is useful as evidence, but it should be converted into polished academic explanation before it enters the thesis chapters.

## Language

The main thesis text should be written in Macedonian.
There should not be standalone English sections such as an English abstract unless they are explicitly required later.
The style should be formal, technical, and similar to the bachelor thesis examples in `thesis/reference/examples/`.

English should be used only for technical terms, abbreviations, names of technologies, paper titles, package names, APIs, model names, library names, and reference metadata.
Technical terms may stay in English when that is the clearer or standard form, especially for terms such as local-first, parser, inference, embedding, quantization, RAG, LLM, model, dataset, and API.
Important terms should be explained in the glossary appendix.

## Structure

The thesis should follow a standard bachelor thesis structure:

- Macedonian abstract.
- Introduction.
- Related work.
- Methodology.
- System architecture.
- Implementation.
- Evaluation.
- Conclusion.
- Future work.
- Appendices.
- References.

The thesis should not be organized as daily notes.
Daily or commit-level progress belongs in `CHANGES.md` and optional narrative logs.

## Development Evidence

Every meaningful commit should update the development evidence.
The default evidence file is `CHANGES.md`.
Longer entries should be placed in `docs/development-log/` only for important decisions, experiments, architecture changes, failed attempts, or evaluation results.

The polished LaTeX thesis should be updated when a change becomes stable enough to describe academically.
The appendix may summarize the development history, but it should not replace the main technical narrative.

## Visual Material

The thesis should use visual material when it improves explanation.
This includes architecture diagrams, data-flow diagrams, user-flow diagrams, parser flow diagrams, model pipeline diagrams, graphs, charts, and evaluation plots.

Visual material may be created using Excalidraw or Python visualization libraries.
Figures should be treated as thesis artifacts and stored under `thesis/figures/` or a clearly named subdirectory.

## Excalidraw Workflow

When useful, `.excalidraw` files can be created for the paper.
They may be used for architecture diagrams, user flows, data flows, model pipelines, local inference diagrams, storage diagrams, and implementation diagrams.

If needed, the `.excalidraw` file should be exported or screenshotted and inserted into the LaTeX thesis as a figure.
The source `.excalidraw` file should be kept so the diagram can be edited later.

## Python Visualization Workflow

Python visualization libraries may be used for quantitative material.
This includes parser evaluation, statistics, performance measurements, model comparison, quantization experiments, local inference measurements, and usage analysis.

Generated plots should be reproducible where possible.
The code or script that generated a figure should be kept when the figure depends on measured data.

## References

Subagents and web search may be used to find academic papers and references needed for the thesis.
References should support related work, methodology, design decisions, implementation choices, and evaluation methods.

Useful reference topics include:

- Local-first software.
- Personal informatics and self-tracking applications.
- Natural language interfaces and shorthand input.
- Local LLM inference.
- Model quantization.
- Mobile/on-device machine learning.
- Correction memory and personalization.
- Software engineering methodology for bachelor projects.
- Evaluation methods for parsers and intelligent user interfaces.

References should be added to `thesis/references.bib` and cited from the relevant chapter.

## Change Review

After Git is initialized, thesis changes should be reviewed through normal Git diffs.
For larger review points, `git-latexdiff` can be used to generate a tracked-changes PDF between commits or tags.

LaTeX source files should use short lines where practical.
One sentence per line is preferred for prose-heavy sections because it makes Git diffs easier to read.

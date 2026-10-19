# State-of-Health BC

**State-of-Health BC (SoHBC)** is a project that attempts to describe and
predict the state of health in British Columbia, Canada.

**Documentation site:** <https://galenseilis.github.io/state-of-health-bc>

## Disclaimer

*Caveat emptor.* State-of-Health BC is an **independent project**. It is
not officially endorsed by, affiliated with, or produced by any
organisation — including the Government of British Columbia, the
Provincial Health Services Authority (PHSA), the BC Centre for Disease
Control (BCCDC), any regional health authority, the First Nations Health
Authority, or any other body. It has no authority to speak for them, and
any errors or omissions are the project's own. This remains the case
until further notice.

## What it does

The project follows a five-stage journey:

1. **Define** health, and the state of health in BC.
2. **Find and explore** data that describe the state of health in BC over
   time and space — "data" construed broadly, from microdata to published
   summary statistics.
3. **Characterise** the variables that are statistically dependent with
   health.
4. **Characterise** the causal structures that result in changes in the
   state of health.
5. **Recommend** actions that would improve the state of health.

Each stage is broken into milestones with deliverables and acceptance
criteria in [ROADMAP.md](ROADMAP.md).

Two principles frame the work:

- **Health is dynamic and nonstationary.** The state of health is a
  trajectory, not a snapshot, and the relationships behind it change
  over time — so every result is tied to the window it holds in and the
  pipeline is re-run as data refresh.
- **BC is the object of study, not a data boundary.** Explanatory data
  from outside BC (patient flows, migration, external economic or
  environmental shocks) is in scope whenever it bears on BC's health.

## Status

Early stage. The repository currently contains the project definition,
the roadmap, and the documentation site. Analysis code and data land with
milestones M1–M5 (see the [roadmap](ROADMAP.md)).

## Documentation

The docs are built with [Quarto](https://quarto.org) and follow the
[Diátaxis](https://diataxis.fr) framework — four sections, each for a
different kind of question:

| Section | Purpose |
|---------|---------|
| [Tutorials](https://galenseilis.github.io/state-of-health-bc/tutorials/index.html) | Learn by doing, step by step |
| [How-to guides](https://galenseilis.github.io/state-of-health-bc/how-to/index.html) | Accomplish a specific task |
| [Reference](https://galenseilis.github.io/state-of-health-bc/reference/index.html) | Look up facts and structure |
| [Explanation](https://galenseilis.github.io/state-of-health-bc/explanation/index.html) | Understand concepts and context |

To preview the site locally, install Quarto and run:

```bash
quarto preview
```

## Repository structure

```
├── README.md              This file
├── ROADMAP.md             Milestones, deliverables, acceptance criteria
├── LICENSE                GPL-3.0
├── _quarto.yml            Documentation site configuration
├── index.qmd              Documentation landing page
├── references.bib         Bibliography: sources cited in the docs
├── tutorials/             Learning-oriented documentation
├── how-to/                Task-oriented documentation
├── reference/             Information-oriented documentation
├── explanation/           Understanding-oriented documentation
└── .github/workflows/     CI: builds and deploys the docs site
```

## Contributing

See [How to contribute](https://galenseilis.github.io/state-of-health-bc/how-to/contribute.html)
in the docs. Open an issue before starting non-trivial work, and place new
documentation in the correct Diátaxis section. Cite sources for factual
claims: entries live in `references.bib` and are cited inline with
`[@key]` syntax.

## Why BC only?

This is primarily due to capacity. Maybe someday we can expand to Canada,
and then to North America, and then Earth. But for now a scope of BC is
already a great difficulty to face realistically.

"BC only" describes the **object of study** — BC's health — not the
boundary of the data. Explanatory data from outside BC that bears on BC
health (patient flows across borders, migration, economic disturbances
originating elsewhere, cross-border environmental spillovers) is in
scope; what is excluded is describing and predicting *other* places'
health. See [Why BC only?](https://galenseilis.github.io/state-of-health-bc/explanation/why-bc.html)
for the full rationale.

I also hope that it inspires others who live elsewhere to start putting
the pieces together about the state of health where they live.

## Licence

[GPL-3.0](LICENSE)

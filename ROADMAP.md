# Roadmap

This roadmap breaks the project into sequential milestones with explicit
deliverables and acceptance criteria. Status values: `not started`,
`in progress`, `complete`.

Cross-cutting concerns (reproducibility, data governance, documentation)
apply to every milestone.

A guiding assumption throughout: **health is a dynamic, nonstationary
quantity.** Distributions drift, relationships between variables change
over time, and shocks (epidemics, policy changes, demographic transition)
create regime shifts. Every milestone therefore treats "the state of
health" as a trajectory to be tracked — never a fixed snapshot — and
results are always tied to the time window in which they hold.

---

## M0 — Foundation

**Goal:** Establish the repository, documentation site, and contribution
workflow so all later work has a place to live.

**Deliverables:**

- Repository with licence (GPL-3.0), README, and this roadmap.
- Quarto documentation site organised with the Diátaxis framework
  [@procidadiataxis] (tutorials, how-to guides, reference, explanation).
- Automated deployment of the documentation site to GitHub Pages from the
  `gh-pages` branch.

**Acceptance criteria:**

- `quarto render` builds the site without errors.
- A push to `main` publishes the site automatically.
- New contributors can find the project overview, roadmap, and the four
  Diátaxis entry points from the landing page.

**Status:** complete — content committed; enable GitHub Pages (source:
`gh-pages` branch) in repository settings to publish
**Depends on:** nothing

---

## M1 — Defining the state of health

**Goal:** Produce a **provisional, versioned** definition of health and
of the "state of health" in BC that can be operationalised as measurable
indicators, together with the measurement framework that turns it into
candidate indicators. The definition is expected to evolve as the project
learns what is measurable; revisions are recorded, never silent.

**Deliverables:**

- A definition document covering: conceptual basis (WHO, ICF,
  capability-based views), the domains, what is deliberately excluded,
  and a stated revision process.
- **Proxy discipline**: the definition distinguishes the construct (the
  state of health) from proxies (every indicator), so that no proxy is
  confused for the state of health, no proxy is taken to define its
  domain, and composite indices are treated as models rather than
  measurements.
- **Temporal semantics** in the definition: health is specified as a
  time-varying state (a trajectory with levels, slopes, and possible
  discontinuities), not a timeless attribute. The definition states what
  changes over what timescale, and that indicators are re-evaluated as
  the underlying population changes.
- **All resolutions**: the definition commits to using all available
  levels of resolution (individual, neighbourhood/HSDA/LHA, health
  authority, provincial, external/non-BC), recording the resolution of
  every datum and result, and treating any fusion across resolutions as
  a model output with stated assumptions.
- A measurement framework: domains and candidate indicator families for
  each domain (mortality, physical morbidity, mental health, functional
  status, subjective wellbeing, social wellbeing), each with candidate
  sources and stated expected temporal behaviour (gradually trending,
  seasonally varying, shock-prone, or plausibly stable over the analysis
  window).
- Glossary of terms used consistently across the project.

**Acceptance criteria:**

- The definition document is published in the Explanation section of the
  docs and survives review by at least one domain reviewer.
- Every proposed domain maps to at least one candidate indicator with a
  named, obtainable data source.
- The definition explicitly answers: is the state of health a snapshot,
  a trajectory, or both — and how the project will detect when its own
  description of health has gone stale.
- The definition distinguishes constructs from proxies, and states how
  results at different resolutions are recorded and combined.
- The definition carries a version number and a revision process.

**Status:** in progress — v0.1 drafted (definition document, measurement
framework, glossary); fusing across resolutions and domain additions still
to be stress-tested once M2 lands
**Depends on:** M0

---

## M2 — Data landscape

**Goal:** Inventory and characterise the data that describe the state of
health in BC over time and space. "Data" is construed broadly: anything
publicly available that can be appropriately used to advance the
project's goals — from survey and administrative microdata through
published summary statistics.

**Deliverables:**

- Data source catalogue (in the Reference section): coverage period,
  geography, frequency, licence, access route, refresh cadence, quality
  notes. Each entry records its **form** — microdata, indicator table,
  dashboard, or report figure — since a published summary statistic is
  as admissible as a raw dataset.
- Catalogue entries for **external drivers** as well: sources outside BC
  that bear on BC's health (interprovincial and international patient
  flows, migration, national/provincial economic conditions, supply
  chains, cross-border environmental conditions), each tagged with its
  geographic origin and the mechanism by which it reaches BC.
- Acquisition pipeline: scripts that fetch/ingest each source into a
  reproducible local layout.
- Data quality report: known gaps, revisions, suppressions, and
  definitional breaks.

**Acceptance criteria:**

- Every indicator named in the M1 measurement framework has at least one
  catalogue entry.
- A clean checkout plus the documented commands reproduces the ingested
  dataset.
- The catalogue is judged by "best use of all publicly available
  information that can be appropriately used" — not "microdata or
  nothing": an indicator backed only by published summary statistics
  still qualifies when it passes licence and governance checks.

**Status:** in progress — catalogue of 24 sources (all URLs verified),
including determinant/stratifier sources and microdata access routes; a
Python acquisition pipeline and a data-quality register are drafted.
Outstanding: microdata approvals, neighbourhood-level outcomes, and
cross-border patient-flow / supply-chain external drivers
**Depends on:** M1

---

## M3 — Descriptive atlas

**Goal:** Describe the state of health in BC over time and space.

**Deliverables:**

- Reproducible analysis pipeline producing trend and map views for each
  indicator.
- **Trajectory analysis as the default view**: change over time (slopes,
  turning points, change-point detection) is reported alongside levels;
  cross-sectional snapshots are treated as slices of the trajectory, not
  the headline result.
- Regime-aware reporting: identified discontinuities (e.g. pandemic
  years, coding definition changes, health system reforms) are marked on
  every series, with within-regime and across-regime comparisons kept
  separate.
- A published "State of health in BC" descriptive report (trends,
  inequalities across health authorities/regions, demographic breakdowns),
  versioned with its observation window.
- Indicator reference pages with definitions, source, and caveats.

**Acceptance criteria:**

- The report regenerates end-to-end from raw data with one documented
  command.
- Each indicator page states its provenance and known limitations.
- Every indicator's page states whether the series is stationary over
  the covered window; nonstationary series carry their trend/regime
  interpretation, not a single summary value.

**Status:** in progress — the pipeline builds and publishes a first
end-to-end indicator (provincial mortality rates, Statistics Canada
13-10-0710-01) with regenerable charts, a trajectory summary (slope and a
detected change point), and regime annotation on the figure. Outstanding:
the wider indicator set, age-standardisation, formal break-point tests,
sub-provincial (map) views, and the descriptive report
**Depends on:** M2

---

## M4 — Statistical dependence

**Goal:** Characterise which variables are statistically dependent with
health outcomes in BC.

**Deliverables:**

- Analysis of association between candidate variables (social,
  economic, environmental, health-system, behavioural) and health
  indicators.
- **Stability analysis before pooling.** For every headline association,
  estimates across subperiods/rolling windows; a single pooled estimate
  is reported only when the relationship is supported as stable over the
  analysis window — otherwise time-varying estimates are the result.
- Documented methods: variable selection, handling of collinearity,
  spatial and temporal confounding, stationarity/stability checks,
  uncertainty reporting.
- Results published with effect sizes, caveats, and their estimation
  window — not just significance flags.

**Acceptance criteria:**

- Methods are documented in the Reference Section; results are explained
  in plain language in the Explanation section.
- Analyses are reproducible from the M2 pipeline.
- Every reported association states the time window it was estimated on
  and whether the relationship was found stable within that window.

**Status:** not started
**Depends on:** M3

---

## M5 — Causal structures

**Goal:** Characterise the causal structures that produce changes in the
state of health.

**Deliverables:**

- Explicit causal diagrams (DAGs) with stated assumptions for key
  questions.
- **Dynamic causal structures:** time-indexed diagrams capturing lagged
  effects, feedback loops (e.g. health → economic participation →
  resources → health), and time-varying confounding; composition changes
  (mortality selection, migration) are represented where they matter.
- Analyses using appropriate designs (longitudinal, quasi-experimental,
  natural experiments where available).
- An assumptions register: what is assumed, why, and what would refute
  it — including explicit stationarity assumptions (which causal links
  are assumed stable over the analysis window, and what observed change
  would invalidate that assumption).

**Acceptance criteria:**

- Each causal claim links to its DAG, data, and assumptions.
- Sensitivity analyses quantify how strong unmeasured confounding would
  need to be to change conclusions.
- Each causal claim carries a stated validity window and the monitoring
  signal that would indicate drift invalidating it.

**Status:** not started
**Depends on:** M4

---

## M6 — Recommendations

**Goal:** Recommend actions that would improve the state of health, with
explicit evidence grading and uncertainty.

**Deliverables:**

- Recommendation framework: evidence strength, expected magnitude,
  feasibility, equity impact, and uncertainty for each recommendation.
- **Validity conditions:** for each recommendation, the M4/M5 findings
  it rests on, the time window of those findings, and the drift
  indicators that trigger re-evaluation.
- A reviewed set of prioritised recommendations.
- A scheduled revision cycle: re-run the pipeline on refreshed data and
  re-confirm, revise, or withdraw each recommendation.

**Acceptance criteria:**

- Every recommendation traces back to M4/M5 results and its underlying
  data sources.
- Recommendations are published with their confidence level and the
  conditions under which they should be revisited.
- No recommendation is presented as permanently valid; each carries a
  date and the next scheduled review.

**Status:** not started
**Depends on:** M4, M5

---

## Cross-cutting concerns

These run alongside every milestone:

- **Reproducibility.** Every published number regenerates from raw data
  via documented commands; environments are pinned.
- **Nonstationarity vigilance.** Results are versioned with their
  observation window; the pipeline is re-run on refreshed data so drift
  in distributions or relationships is detected rather than assumed
  away; regime shifts (epidemics, policy changes, coding revisions) are
  marked as first-class events in every series.
- **Data governance and ethics.** Respect licences, privacy obligations,
  and Indigenous data sovereignty principles (e.g. OCAP®
  [@fnigcOcap] and First Nations data governance contexts in BC). No
  individual-level data in the repository.
- **Documentation.** New capabilities land with matching documentation in
  the correct Diátaxis section.
- **Engineering conventions.** The top-level framework and interface are
  written in Python; Python may glue around other tools and languages
  (including R) where that has a distinct benefit; performance-critical
  new functionality is implemented in Rust, C, and/or C++ — preferring
  Rust for greenfield code, and allowing C/C++ to interface with existing
  low-level libraries. See [How to contribute](how-to/contribute.qmd).
- **Citations.** Factual claims about the world are cited: sources are
  recorded in `references.bib` and cited inline with Pandoc citation
  syntax (`[@key]`), so each page renders its own reference list from
  the works it cites.
- **Scope control.** The object of study is BC's health — not
  exclusively BC-origin data. Explanatory data that bears on BC health
  but originates elsewhere (interprovincial and international patient
  flows, migration, supply chains, economic or environmental disturbances
  from outside the province) is in scope; what is "BC only" is the
  outcome being explained. Expansion of the object of study beyond BC is
  out of scope until the BC analysis is mature (see README).

# Verifier Tech Stack: Deterministic Static Checking of Machine-Readable Wet-Lab Protocols

Scope note: research conducted 2026-10-01. Code patterns marked "**Pattern (recommended)**" are design
proposals by this researcher, derived from the cited library APIs — they are not quoted from sources.
Everything presented as a fact about a library, API, dataset or paper carries an inline URL.

---

## Q1. Candidate representations for the protocol IR — ranking, and whether a minimal-but-real Lean 4 layer is feasible in 48h

### Takeaway

Pydantic v2 + pint as the IR, with a thin hand-written check pass, is the only option that reliably ships
in 24–48h and produces the error messages an LLM repair loop needs. Lean 4 *does* have real
dimensional-analysis work to build on (ATOMSLab's `LeanDimensionalAnalysis`, the `λs` calculus, PhysLib),
but all three are research artifacts with small commit counts, Mathlib dependencies and known
`noncomputable` edges — making Lean the *demo-impact* layer, not the *coverage* layer. The pragmatic
split is: Python checks everything; Lean proves one or two named theorems about one small sub-slice
(volume conservation in a serial dilution) and is exhibited, not depended upon.

### Cited Findings

**Lean 4 units / dimensional analysis — what actually exists**

- ATOMSLab (Josephson group) published "Formalizing dimensional analysis using the Lean theorem prover"
  (arXiv 2509.13142, submitted 16 Sep 2025; authors Maxwell P. Bobbin, Colin Jones, John Velkey,
  Tyler R. Josephson) — [arXiv abs](https://arxiv.org/abs/2509.13142);
  [preprint PDF](https://atomslab.github.io/static/pdf/publications/bobbin_2025.pdf)
- Their core definition models a dimension as a map from base dimensions to exponents in a commutative
  ring: `def dimension (B : Type u) (E : Type v) [CommRing E] := B → E`, and a quantity as a structure
  indexed by that dimension:
  `structure PhysicalVariable {B : Type u} {V : Type v} [Field V] (dim : dimension B V) where (value : V)`
  — [arXiv HTML v1](https://arxiv.org/html/2509.13142v1)
- Dimensions are proven to form an **Abelian group under multiplication**; the development also covers
  derived dimensions, dimensional homogeneity theorems, SI base units and fundamental constants, and
  the **Buckingham Pi theorem**, validated on a Lennard-Jones potential example —
  [arXiv HTML v1](https://arxiv.org/html/2509.13142v1)
- Homogeneity is discharged by **typeclass inference plus a custom tactic**, not by `decide`. They expose
  a cast with a tactic-defaulted proof argument:
  `protected def cast {d1 d2 : dimension B V} (Q : PhysicalVariable d1) (_ : d1 = d2 := by evalAutoDim) : PhysicalVariable d2`,
  where `evalAutoDim` works by "reflexivity, rewriting, simplification, and ring normalization" —
  [arXiv HTML v1](https://arxiv.org/html/2509.13142v1)
- Addition is constrained to the same dimension **at the type level** —
  [arXiv HTML v1](https://arxiv.org/html/2509.13142v1)
- Stated limitation relevant to a hackathon: definitions involving the epsilon operator are marked
  `noncomputable`, which **prevents direct evaluation via `#eval`** —
  [arXiv HTML v1](https://arxiv.org/html/2509.13142v1). The authors also concede the cast function
  requires explicit up-arrow (`↑`) notation, which "doesn't reduce the usability of the code, just the
  presentation" — [arXiv HTML v1](https://arxiv.org/html/2509.13142v1)
- Repo: `https://github.com/ATOMSLab/LeanDimensionalAnalysis` — Apache-2.0, directories
  `DimensionalAnalysis/` and `PhysicalVariables/`, `lakefile.toml` + `lean-toolchain` + `lake-manifest.json`,
  and as observed: **13 commits on main, 5 stars, 0 forks, 0 open issues** —
  [GitHub](https://github.com/ATOMSLab/LeanDimensionalAnalysis)
- A second, more theory-heavy Lean 4 artifact: `λs` (lambda-s), "a typed lambda calculus in which
  conversion between units of the same dimension is a primitive," with a full mechanization of statics,
  dynamics, denotational semantics, two abstraction theorems, adequacy, erasure, and the Pi theorem,
  updated as recently as 13 Sep 2026 — [GitHub ericeallen/lambda-s](https://github.com/ericeallen/lambda-s)
- A third: **Lean4Physics / PhysLib**, described as "an extensible, community-driven foundation library
  that sets the cornerstone for units, fields, and theorems for formal physics reasoning" —
  [arXiv 2510.26094](https://arxiv.org/html/2510.26094v1)
- Mathlib4 is the Lean 4 math library — [GitHub](https://github.com/leanprover-community/mathlib4).
  No units-of-measure / dimensional-analysis module was found in it by this research; the existence of
  three *separate* standalone projects is the evidence that Mathlib does not cover this.

**Existing protocol languages**

- **LabOP** (Laboratory Open Protocol language) is "an open specification for laboratory protocols, that
  solves common interchange problems stemming from variations in scale, labware, instruments, and
  automation" — [UCSC OSPO project page](https://ucsc-ospo.github.io/project/osre23/ucsd/labop/);
  spec repo [Bioprotocols/labop-specification](https://github.com/Bioprotocols/labop-specification);
  software repo [Bioprotocols/labop](https://github.com/Bioprotocols/labop)
- LabOP is "fully machine-readable and encoded in OWL/SHACL from which documentation and software
  implementations are automatically generated," with documents stored as RDF —
  [labop-specification](https://github.com/Bioprotocols/labop-specification)
- **For automated validation LabOP uses SHACL** (Shapes Constraint Language), "an RDF-based language
  that describes graph patterns to which valid RDF documents must conform," and the `labop` software
  stack "leverages the pySHACL validator tool to check these constraints and ensure that individual
  LabOP protocols are complete, consistent, and valid data structures" —
  [LabOP docs](https://bioprotocols.github.io/labop/)
- The LabOP design paper is Beal et al., "Building an Open Representation for Biological Protocols,"
  ACM JETC — [DOI 10.1145/3604568](https://dx.doi.org/10.1145/3604568);
  [author PDF](https://jakebeal.github.io/Publications/JETC23-LabOP.pdf)
- The `labop` Python library exposes validation as `for issue in doc.validate(): print(issue)`, and its
  modules include core `labop`, `labop_convert` (e.g. to Markdown), `labop_time`, `owl_rdf_utils`, and a
  `uml` module. The repo shows **911 commits on `develop` and 62 open issues** —
  [GitHub Bioprotocols/labop](https://github.com/Bioprotocols/labop)
- **XDL** is "a chemical description language for representing chemical procedures in a machine and
  human-readable way," based on XML, representing syntheses as "sequences of processes taking place in
  abstract vessels with abstract hardware," with three mandatory sections: **Hardware, Reagents, Procedure**
  — [Mehr et al. 2020, Glasgow ePrints PDF](https://eprints.gla.ac.uk/221626/1/221626.pdf);
  [Science paper](https://www.science.org/doi/10.1126/science.abc2986);
  reference implementation fork [GitHub mcrav/xdl](https://github.com/mcrav/xdl)
- Caveat for adoption: **no formal schema is available for XDL 2.0, aside from documentation** —
  [arXiv 2502.02872 (Turing Complete Chemputer)](https://arxiv.org/pdf/2502.02872)

### Inferences

- **Ranking for a 24–48h build** (expressiveness / effort / error-message quality / demo impact):
  1. **Pydantic v2 + pint typed Python DSL** — best effort-to-coverage ratio. Pydantic v2 gives you
     JSON Schema *for free* (so the LLM can be constrained by schema at generation time) plus
     per-field validation errors that already carry a JSON-path location, which is exactly the shape a
     repair loop needs. Expressiveness is unbounded because arbitrary Python runs in validators.
     Error quality: best in class. Demo impact: low on its own.
  2. **Lean 4 as a thin proof layer over the Python IR** — highest demo impact per line, *if* scoped to
     one theorem. Error quality: poor (Lean errors are not LLM-repair-friendly without translation).
  3. **Datalog (clingo/ASP)** — best fit for the *dataflow and ordering* checks (define-before-use,
     control-present, replicate counts) because those are naturally recursive reachability queries over
     a step graph; 20–40 lines of ASP replaces a few hundred lines of imperative graph code.
  4. **Z3py** — only worth it for the arithmetic you cannot evaluate directly, e.g. "does *any* assignment
     of unspecified volumes satisfy all the constraints," or synthesising a repair suggestion. For
     checking a *fully concrete* protocol, Z3 is strictly more machinery than `float` comparison.
  5. **JSON Schema** — ship it, but only as the generation-time guardrail (structure, enums, required
     fields). It cannot express C1V1=C2V2 or capacity checks. Zero marginal cost if derived from Pydantic.
  6. **LinkML** — attractive on paper (generates Pydantic + JSON Schema + SHACL from one YAML schema) but
     adds a toolchain learning curve on day 1 of a 2-day build; recommend as stretch only.
  7. **OWL + SHACL** — this is literally what LabOP does ([LabOP docs](https://bioprotocols.github.io/labop/)),
     so it is the "legitimate" choice, but SHACL diagnostics are validation-report graphs, and pySHACL
     cannot do the arithmetic. Highest friction for the least demo payoff in 48h.
  8. **Adopting LabOP / Autoprotocol / XDL / Opentrons API wholesale** — the right long-run answer and the
     wrong hackathon answer: you inherit a large data model you must learn before you can check anything.
     XDL additionally lacks a formal 2.0 schema
     ([arXiv 2502.02872](https://arxiv.org/pdf/2502.02872)). Better: make your IR *exportable to*
     Opentrons/LabOP and use that export as the end-of-demo payoff.
- **What a minimal-but-real Lean 4 layer looks like, and is it realistic in 48h?** Realistic only in this
  exact shape, and only if one team member owns it for the whole window and nothing else:
  - Do **not** reimplement dimensions as dependent types indexed by exponent vectors from scratch, and do
    **not** try to vendor ATOMSLab's library — it is 13 commits, Mathlib-dependent, and partly
    `noncomputable` ([GitHub](https://github.com/ATOMSLab/LeanDimensionalAnalysis);
    [arXiv HTML](https://arxiv.org/html/2509.13142v1)), so a Mathlib build alone can eat hours.
  - Instead: a **Mathlib-free** Lean 4 package with (a) `structure Vol where µL : Rat` and
    `structure Conc where molPerL : Rat` as *distinct* structures — this gets you
    unit-safety-by-nominal-typing with zero dependent-type machinery and zero build cost;
    (b) one real lemma, e.g. `theorem dilution_conserves (c₁ v₁ c₂ v₂ : Rat) (h : c₁ * v₁ = c₂ * v₂) : ...`
    stated over `Rat` so it is *decidable and computable* (`Rat` has `DecidableEq`, so `decide` works and
    there is no float noise); (c) range predicates as `Bool`-valued functions plus
    `example : inRange 37 tempRange = true := by decide` — `decide` is genuinely cheap here because the
    propositions are closed and arithmetic over `Rat`/`Int`.
  - The deliverable is a Lean file that **exports a checked protocol fragment and fails to compile when
    the fragment is wrong**, shown live. That is a real formal-methods artifact and it is achievable.
  - `native_decide` is the escape hatch if `decide` is too slow, but it adds a trust axiom and compilation
    latency; for `Rat` comparisons on a handful of steps you will not need it.
  - **Honest framing for the demo:** "Lean proves the dilution algebra and the range predicates for the
    exported fragment; Python enforces the other 90% of the rules." Claiming Lean verifies the whole
    protocol would be false.
- Rat (not Float) is the single most important representation decision regardless of language: it makes
  C1V1=C2V2 an *exact* equality check, removes epsilon-tolerance bikeshedding, and is what makes `decide`
  viable on the Lean side. Pydantic v2 supports `Decimal`/`Fraction`-backed fields.

### Gaps

- Could not verify the Lean toolchain version or Mathlib pin in `LeanDimensionalAnalysis` — the GitHub
  landing page fetch did not surface `lean-toolchain` contents or the README body, so build-time risk is
  unquantified.
- Found no evidence of any Lean 4 project aimed at *laboratory protocols* specifically (as opposed to
  physics/dimensions). If the report wants to claim novelty here, that is plausibly supportable, but I
  did not run an exhaustive search.
- **SciLean specifically was not confirmed or refuted.** Searches surfaced ATOMSLab, λs and PhysLib but
  returned no SciLean units module. Treat "SciLean has units support" as unverified.
- Did not verify Autoprotocol's current maintenance status or its JSON schema; it appeared in no search
  result. Recommend the report either drops it or flags it as unassessed.
- LabOP's *specific* SHACL shape files and whether its checkers cover volume/arithmetic (vs. structural
  validity only) was not confirmed. The sources describe SHACL as checking that protocols are "complete,
  consistent, and valid data structures" ([LabOP docs](https://bioprotocols.github.io/labop/)), which
  reads as structural, not quantitative — but I could not read the shapes to confirm.

---

## Q2. Unit handling in Python; patterns for serial dilutions and plate-well limits

### Takeaway

pint is the default choice and its `DimensionalityError` messages are already diagnostic-grade. UCUM is
worth adopting as the *wire format* for units in the IR (strings the LLM emits), with `ucumvert` bridging
UCUM strings into pint — that gives you a closed, validatable vocabulary instead of free-text units.

### Cited Findings

- pint raises `DimensionalityError` on invalid conversion with a message of the form
  "Cannot convert from 'meter' ([length]) to 'joule' ([length] ** 2 * [mass] / [time] ** 2)" — i.e. the
  message names both units *and* both dimensionality expressions —
  [pint docs](https://pint.readthedocs.io/en/stable/)
  (error-message form documented via [pint changelog](https://pint.readthedocs.io/en/stable/changes.html))
- pint has a documented history of **DimensionalityError from floating-point noise in combined fractional
  unit exponents** — a real, named failure mode — [pint changelog](https://pint.readthedocs.io/en/stable/changes.html)
- Known pint sharp edges to avoid in a 48h build: `auto_reduce_dimensions=True` triggers spurious
  `DimensionalityError` ([issue #902](https://github.com/hgrecco/pint/issues/902)); unexpected
  `DimensionalityError` reports ([issue #681](https://github.com/hgrecco/pint/issues/681)); subclassing
  `Quantity` breaks `__setitem__` with no useful error message
  ([issue #826](https://github.com/hgrecco/pint/issues/826))
- **ucumvert** is a pip-installable Python package providing a parser for UCUM unit strings implementing
  the full grammar, a converter creating **pint** units from UCUM strings, and a pint unit-definition file
  extending pint's defaults with UCUM units; created January 2024, release 0.2.0 supports UCUM v2.2
  — [GitHub dalito/ucumvert](https://github.com/dalito/ucumvert);
  [PyPI](https://pypi.org/project/ucumvert/0.2.2/);
  [ucum-org discussion #366](https://github.com/orgs/ucum-org/discussions/366)
- UCUM v2.2 dates from June 2024 — [ucumvert / PyPI](https://pypi.org/project/ucumvert/0.2.2/)
- **pyucum** is an alternative, aimed at CDISC SDTM.LB / ADaM.ADLB verification, using UCUM APIs to
  generate, verify and convert units — [PyPI pyucum](https://pypi.org/project/pyucum)
- A second UCUM Python implementation: [GitHub stomioka/ucum](https://github.com/stomioka/ucum)
  ("Unit conversion, verification with Unified Code for Units of Measure")
- CODATA's DRUM task group maintains a "Digital Unit Representation Inventory" cataloguing unit
  representation systems — [CODATA DRUM](https://codata.org/initiatives/task-groups/drum/the-digital-unit-representation-inventory/)
- Opentrons' own well capacity field is in **microliters** (see Q4), so µL is the natural canonical
  internal unit — [Opentrons labware schema 2](https://raw.githubusercontent.com/Opentrons/opentrons/edge/shared-data/labware/schemas/2.json)

### Inferences

- **Pattern (recommended) — units on the wire, quantities in the checker.** Make every numeric parameter
  in the IR a two-field object `{"value": "350", "unit": "uL", "source": {...}}` where `unit` is validated
  against UCUM via `ucumvert` and `value` is parsed as `Fraction`/`Decimal`, never `float`. Convert to pint
  once, at IR-load time, in a Pydantic `field_validator`. Rationale: the LLM emits strings; a closed UCUM
  vocabulary turns "unit is nonsense" into a *schema* error (cheap, generation-time) rather than a
  *semantic* error (expensive, repair-loop).
- **Pattern (recommended) — serial dilution check.** For a declared series with stock C₀ and a list of
  steps each `(v_transfer, v_diluent)`, compute expected concentration recursively with exact rationals:
  `C_{i+1} = C_i * v_transfer / (v_transfer + v_diluent)`; compare to the protocol's *declared* C_{i+1}
  with exact equality on `Fraction`, and separately assert the declared **fold-factor** matches
  `(v_transfer + v_diluent)/v_transfer`. Report both the computed and declared value in the error. The
  reason to check the declared value rather than just computing it: the LLM's *stated intent* ("10-fold
  serial dilution") is the invariant you want to protect, and a silent recompute lets the LLM "fix" errors
  by changing its intent (see Q7).
- **Pattern (recommended) — C1V1=C2V2 as exact rational equality.** `c1*v1 == c2*v2` over `Fraction` with
  no tolerance. If a tolerance is unavoidable (because the LLM rounds), make the tolerance an explicit,
  named, logged policy (`REL_TOL = Fraction(1,1000)`) rather than a float epsilon, and include the
  tolerance in the error message so the LLM knows how much slack it has.
- **Pattern (recommended) — plate-well volume accounting.** Maintain a dict
  `balance: dict[(labware_id, well_id), Fraction]` and fold over steps in order: dispense adds, aspirate
  subtracts. After each step assert `0 <= balance[w] <= capacity(w)` where `capacity` comes from the
  Opentrons `totalLiquidVolume` for that well (Q4). Check the invariant **after every step**, not at the
  end, so the error can name the step index — this is what makes the message
  "step 4: well A12 receives 350 µL, labware max is 300 µL" possible. Also check the negative bound: it
  catches aspirating from an empty/undefined well, which is a *different* bug class (dataflow, Q5).
- pint's float-noise history argues for doing the *comparisons* on `Fraction` and using pint only for
  dimensionality bookkeeping and conversion — i.e. treat pint as a unit system, not as your arithmetic.
- astropy.units is a viable alternative but carries the whole astropy dependency and is tuned for
  astronomical units; nothing found suggests an advantage for wet-lab work. Recommend pint. (This is an
  inference from the absence of lab-relevant astropy.units material, not a sourced claim.)

### Gaps

- Did not retrieve a canonical pint docs page showing the exact `DimensionalityError` message template
  from the current release's source; the message form is attested via docs/changelog and issue threads
  rather than from `errors.py`. Verify before quoting the exact string in a report.
- Did not assess `ucumvert`'s maintenance status in 2026 or whether UCUM has released a version after
  v2.2. Latest confirmed: UCUM v2.2, June 2024 ([PyPI ucumvert](https://pypi.org/project/ucumvert/0.2.2/)).
- No source found that documents a lab-protocol-specific units library (i.e. something that already knows
  about molarity, fold-dilution, plate wells). Appears not to exist; build it.

---

## Q3. Programmatically queryable reference data for reagent handling and hazard classification

### Takeaway

PubChem PUG-View is the only one of the four with a genuinely usable, unauthenticated JSON API returning
GHS classification — make it the MVP source. CAMEO Chemicals has exactly the right data model for
pairwise reactivity (68 reactive groups + a predicted-hazard matrix) but **no API and no documented bulk
download**, so the reactivity check must be backed by a small hand-curated table extracted once, offline.
ECHA C&L has no documented bulk export; NIOSH NPG has no API.

### Cited Findings

**PubChem PUG-REST / PUG-View**

- PUG-View is "a Representational State Transfer (REST)-style web service interface specialized for
  accessing annotation data contained in PubChem," giving the full structured compound/substance pages as
  hierarchical sections covering names, structures, physical/chemical properties, **safety data**,
  pharmacology, biological activities, toxicology and literature references —
  [Kim et al., J Cheminform 2019, "PUG-View"](https://jcheminf.biomedcentral.com/articles/10.1186/s13321-019-0375-2)
- Base URL `https://pubchem.ncbi.nlm.nih.gov/rest/pug_view`; all structured data for a compound via
  `/data/compound/{cid}/JSON`; **no authentication required** —
  [PubChem PUG-View docs](https://pubchem.ncbi.nlm.nih.gov/docs/pug-view)
- GHS data — **pictograms, signal words, and hazard statements** — is retrievable by requesting the
  PUG-View **"GHS Classification" heading**, returning JSON with the compound info and GHS details —
  [PubChem PUG-View docs](https://pubchem.ncbi.nlm.nih.gov/docs/pug-view);
  heading-based retrieval is also exercised by third-party wrappers, e.g.
  [ToolUniverse `pubchem_tox_tool`](https://zitniklab.hms.harvard.edu/ToolUniverse/_modules/tooluniverse/pubchem_tox_tool.html)
  and [PubChemR `get_pug_view`](https://rdrr.io/cran/PubChemR/man/get_pug_view.html)
- PUG-REST URL structure is four components — Prolog (`https://pubchem.ncbi.nlm.nih.gov/rest/pug`), Input,
  Operation, Output (TXT, CSV, PNG, XML, JSON, SDF), plus optional Options after `?`. Example:
  `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/MolecularFormula/txt` —
  [IUPAC FAIR Chemistry Cookbook](https://iupac.github.io/WFChemCookbook/datasources/pubchem_pugrest1.html)
- **Rate limit: "users should limit their web-requests to no more than five per second."** "Violators of
  usage policies may result in the user being temporarily blocked from accessing PubChem (or NCBI)
  resources." — [IUPAC FAIR Chemistry Cookbook](https://iupac.github.io/WFChemCookbook/datasources/pubchem_pugrest1.html),
  which cites the official
  [Request Volume Limitations](https://pubchem.ncbi.nlm.nih.gov/docs/programmatic-access#section=Request-Volume-Limitations)
  and [Dynamic Request Throttling](https://pubchem.ncbi.nlm.nih.gov/docs/dynamic-request-throttling) pages

**CAMEO Chemicals (NOAA)**

- There are **68 reactive group datasheets** in CAMEO Chemicals; "each chemical in the database has been
  assigned to one or more reactive groups based on its chemistry, and the predictions are based on the
  reactions that might occur between reactive groups" —
  [NOAA CAMEO Chemicals / Chemical Reactivity Worksheet](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/chemical-reactivity-worksheet);
  [Reactive Groups browse page](https://cameochemicals.noaa.gov/browse/react)
- Reactive groups are individually addressable by stable numeric URL path, e.g.
  `/react/70` (Acetals, Ketals, Hemiacetals, and Hemiketals), `/react/3` (Acids, Carboxylic),
  `/react/1` (Acids, Strong Non-oxidizing), `/react/2` (Acids, Strong Oxidizing),
  `/react/100` (Water and Aqueous Solutions); **IDs run 1–100 with gaps** —
  [Reactive Groups browse page](https://cameochemicals.noaa.gov/browse/react)
- "Once you've added two or more substances to MyChemicals, you can see reactivity predictions about what
  might happen if any of those substances were to mix together. The predicted hazards are summarized in
  the **compatibility chart**." — [NOAA](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/chemical-reactivity-worksheet)
- **The compatibility matrix is generated inside the tool, not published as a standalone downloadable
  file**, and the reactive-groups page shows **no API, no data download, no export, no machine-readable
  format** — [Reactive Groups browse page](https://cameochemicals.noaa.gov/browse/react);
  [NOAA](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/chemical-reactivity-worksheet)
- Offline desktop builds exist and are free: CAMEO Chemicals 3.1.0 for Windows (EXE, 182 MB) and Mac
  (DMG, 400 MB), plus a mobile app — [NOAA](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/chemical-reactivity-worksheet)
- Background on data provenance and history —
  [CAMEO Chemicals Development History](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/response-tools/cameo-chemicals-development-history.html);
  practitioner guides: [DCHAS](https://dchas.org/wp-content/uploads/2023/07/CAMEO-Chemicals_FindChemSafetyInfo.pdf),
  [UMCES](https://support.al.umces.edu/cameo-chemicals-a-tool-for-simulating-chemical-incompatibilities/)

**ECHA C&L Inventory**

- The C&L Inventory now lives in **ECHA CHEM**, ECHA's public chemicals database launched in early 2024,
  which also holds REACH registration data and regulatory obligation lists —
  [ECHA CHEM](https://echa.europa.eu/echa-chem); [Search for chemicals](https://echa.europa.eu/information-on-chemicals)
- **ECHA does not publish a documented bulk export**; only specific lists (e.g. the full DWD substance
  list) are downloadable from ECHA CHEM — [ECHA CHEM](https://echa.europa.eu/echa-chem)
- Third-party scrapers exist and should be treated as unofficial: an Apify ECHA scraper returning
  "the same substance data you see on ECHA CHEM as JSON, CSV or Excel" via
  `https://api.apify.com/v2/acts/studio-amba~echa-scraper/run-sync-get-dataset-items`
  — [Apify](https://apify.com/studio-amba/echa-scraper/api); and an api.store C&L endpoint —
  [api.store](https://api.store/eu-institutions-api/european-chemicals-agency-api/echa-classification-and-labelling-inventory-api).
  Note the Apify listing is marked **[DEPRECATED]** — [Apify](https://apify.com/studio-amba/echa-scraper)
- Bulk REACH study-result and IUCLID data are separate products —
  [IUCLID REACH Study Results](https://iuclid6.echa.europa.eu/reach-study-results);
  [Get IUCLID data](https://iuclid6.echa.europa.eu/get-iuclid-data)

**NIOSH Pocket Guide**

- The NPG "contains information about more than 600 chemicals and substance groupings commonly found in
  the work environment," offered in **three versions: online, PDF, and mobile web app**, searchable by
  chemical name, synonym/trade name, DOT number, CAS number and RTECS number —
  [CDC/NIOSH NPG](https://cdc.gov/niosh/npg/default.html);
  [3rd edition record](https://www.cdc.gov/niosh/publications/numbered/2005-149.html);
  [mobile app record](https://stacks.cdc.gov/view/cdc/181882)
- **No REST API or programmatic interface for NPG data was found** in this research —
  searches over [cdc.gov/niosh/npg](https://cdc.gov/niosh/npg/default.html) and related records surfaced
  only online/PDF/app distribution. Full-text PDF mirrors exist, e.g.
  [Pitt mirror](http://ccc.chem.pitt.edu/wipf/Web/NIOSH_PocketGuide.pdf),
  [NRC mirror](https://www.nrc.gov/docs/ml0322/ml032240107.pdf)

### Inferences

- **MVP hazard stack:** PubChem PUG-View only. One function:
  `ghs(cid) -> {pictograms, signal_word, hazard_statements[]}` via the "GHS Classification" heading, cached
  to a local JSON file on first fetch so the demo runs offline and never hits the 5 req/s limit
  ([IUPAC Cookbook](https://iupac.github.io/WFChemCookbook/datasources/pubchem_pugrest1.html)). Resolve
  reagent names → CID once via PUG-REST `/compound/name/{name}/cids/JSON`
  ([PUG-REST structure](https://iupac.github.io/WFChemCookbook/datasources/pubchem_pugrest1.html)).
  **Pre-warm the cache before the demo** — this is the single highest-value 20 minutes of ops work in the
  project, because a live-API dependency is the most likely thing to break on stage.
- **Encoding "this reagent pair's documented reactivity group combination" as a deterministic table check.**
  The CAMEO data model decomposes exactly into three relations, which is what makes a table check possible
  at all ([NOAA](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/chemical-reactivity-worksheet)):
  1. `reagent_group(reagent_id, group_id)` — many-to-many, since a chemical can be in several groups.
  2. `group(group_id, group_name)` — 68 rows, IDs 1–100 with gaps, directly transcribable from
     [the browse page](https://cameochemicals.noaa.gov/browse/react).
  3. `incompatible(group_a, group_b, hazard_code, hazard_text, source_url)` — the pairwise predictions.
  The check is then a join, not a judgment: for every pair of reagents co-present in a container at any
  step, for every pair of their groups, if `incompatible(g_a, g_b, ...)` exists, emit a finding citing
  `source_url`. **Make the relation symmetric by construction** (store both orders, or canonicalise to
  `min,max`) so the check cannot depend on step ordering.
  Crucially: the *table is the authority*, and the checker's output quotes the CAMEO hazard text verbatim
  plus the `/react/{id}` URL. No LLM involvement, and the finding is auditable.
  - **Honest limitation to state in the report:** because there is no CAMEO API or bulk download
    ([browse page](https://cameochemicals.noaa.gov/browse/react)), relation (3) must be curated by hand.
    For a hackathon, curate **10–20 pairs covering the reagents your demo protocols actually use**
    (e.g. strong oxidizing acids × organics, acids × cyanides/sulfides, water-reactives × aqueous
    solutions), each row carrying its `/react/{id}` citation. Present it as a seed table with a documented
    extraction path, not as comprehensive coverage. Claiming full CAMEO coverage would be dishonest.
  - Relation (1) is the real scaling bottleneck, not (3): assigning an arbitrary reagent to CAMEO reactive
    groups is itself a chemistry judgment. For MVP, hard-code group membership for your demo reagent list
    and **fail closed** — if a reagent has no group assignment, emit a distinct code
    (`REACT_UNKNOWN_GROUP`, severity=warning) rather than silently passing. Fail-closed-with-a-distinct-code
    is what keeps the checker honest about its own coverage.
- ECHA and NIOSH are **stretch at best**. Neither has a documented bulk export or API
  ([ECHA CHEM](https://echa.europa.eu/echa-chem); [NIOSH NPG](https://cdc.gov/niosh/npg/default.html)),
  so both imply scraping — which is a licensing and reliability risk and a poor use of 48 hours when
  PubChem already returns GHS. If exposure limits (PELs/RELs) are genuinely needed, note that PubChem's
  safety sections aggregate from many sources including NIOSH-derived content
  ([PUG-View paper](https://jcheminf.biomedcentral.com/articles/10.1186/s13321-019-0375-2)), so query
  PubChem rather than NIOSH directly.

### Gaps

- **Licensing terms are the weakest part of these findings.** PubChem's docs pages are
  JavaScript-rendered and could not be read by fetch; I could not retrieve PubChem's explicit data
  license/terms-of-use text, nor ECHA's or NOAA's reuse terms. The 5 req/s figure is attested by a
  secondary source (IUPAC Cookbook) citing the official pages, not read from the official page itself.
  **Verify all four licenses directly before the report asserts anything about redistribution**, which
  matters if the team ships the cached tables.
- The exact JSON shape of the PUG-View GHS section (field names, nesting, how multiple sources are
  represented) was not retrieved. The heading-based access pattern is confirmed; the response schema is not.
  Plan for one hour of response-shape spelunking.
- CAMEO's **actual pairwise hazard codes** (the vocabulary used in the compatibility chart) were not
  retrieved — only that such a chart exists and is tool-generated. Someone must read a reactive-group
  datasheet to get the real code set.
- Whether the CAMEO desktop download (182 MB EXE / 400 MB DMG) contains an extractable database file is
  **unknown and worth 30 minutes of investigation** — if it ships a SQLite/flat-file database, that single
  finding would convert the hand-curated table into a complete one and is the highest-leverage unknown in
  this whole section.
- No ECHA official API documentation was located; only third-party and partly deprecated wrappers.

---

## Q4. Equipment and labware definitions as data; what dry-run tooling actually catches

### Takeaway

The Opentrons labware JSON schema is the single best free source of machine-readable well geometry and
capacity — `totalLiquidVolume` per well, in µL, with a published schema — and it should be the backing
data for capacity checks. Both Opentrons simulation and PyLabRobot have real volume/tip tracking, but
Opentrons' is the one with a documented Python entry point you can call in-process, making it the right
"second opinion" oracle.

### Cited Findings

**Opentrons labware definitions**

- A JSON file "is the blueprint for Opentrons standard and custom labware," containing and organizing
  labware data "according to the design specifications set by the default schema"; **current schema
  version is 2** — [Opentrons support: What is a labware definition?](https://support.opentrons.com/s/article/What-is-a-labware-definition)
- Required top-level properties of schema 2: `schemaVersion`, `version`, `namespace`, `metadata`, `brand`,
  `parameters`, `cornerOffsetFromSlot`, `ordering`, `dimensions`, `wells`, `groups`. Optional include
  `allowedRoles`, `stackingOffsetWithLabware`, `gripperOffsets`, `gripForce` —
  [labware schema 2.json](https://raw.githubusercontent.com/Opentrons/opentrons/edge/shared-data/labware/schemas/2.json)
- **Well definitions.** Shared required fields: `shape` (`"rectangular"` | `"circular"`), `depth`
  (positive number), **`totalLiquidVolume` (positive number, in microliters)**, `x`/`y`/`z` (center-bottom
  coordinates), `geometryDefinitionId` (string or null). Rectangular wells additionally require
  `xDimension` and `yDimension`; circular wells require `diameter`. For tip racks the schema notes `depth`
  "will be ignored in favor of tipLength, but the values should match" —
  [labware schema 2.json](https://raw.githubusercontent.com/Opentrons/opentrons/edge/shared-data/labware/schemas/2.json)
- Confirming the API-side binding: "The maximum volume property in the well definition is set by the JSON
  labware definition, specifically the **`totalLiquidVolume`** property of the particular well" —
  [Opentrons Python API: Wells and Liquids](https://docs.opentrons.com/python-api/reference/wells-liquids/)
- JSON labware definitions include "spatial dimensions (length, width, height), volumetric capacity
  (µL, mL), and other metrics that define the labware's surface features, their shapes, and locations" —
  [Opentrons Flex: Labware Definitions](https://docs.opentrons.com/flex/labware/definitions/)
- Browsable standard definitions: [Opentrons Labware Library](https://labware.opentrons.com/);
  concepts: [Flex labware concepts](https://docs.opentrons.com/flex/labware/concepts/),
  [OT-2 labware concepts](https://docs.opentrons.com/ot-2/labware/concepts/),
  [Python API labware](https://docs.opentrons.com/v2/new_labware.html)

**Opentrons dry-run / simulation**

- "Protocol analysis transforms a protocol file (JSON or Python) into a series of robot commands" —
  [Opentrons: Importing Protocols](https://docs.opentrons.com/ot-2/opentrons-app/protocol-import/)
- `opentrons.simulate.simulate()` signature:
  `simulate(protocol_file, file_name=None, custom_labware_paths=None, custom_data_paths=None, propagate_logs=False, hardware_simulator_file_path=None, duration_estimator=None, log_level="warning") -> _SimulateResult`
  — documented as simulating a protocol and "either returns (if the simulation has no problems) or raises
  an exception" — [Opentrons: Executing and Simulating](https://docs.opentrons.com/python-api/reference/execute-simulate/)
- `get_protocol_api()` signature:
  `get_protocol_api(version, bundled_labware=None, bundled_data=None, extra_labware=None, hardware_simulator=None, *, robot_type=None, use_virtual_hardware=True) -> protocol_api.ProtocolContext`
  — builds a `ProtocolContext` that simulates robot control; `robot_type` is `"Flex"` or `"OT-2"` —
  [Opentrons: Executing and Simulating](https://docs.opentrons.com/python-api/reference/execute-simulate/)
- Simulation "returns a run log, which is a list of dicts that represent the commands executed by the
  robot" — [Opentrons: Executing and Simulating](https://docs.opentrons.com/python-api/reference/execute-simulate/)
- `custom_labware_paths` "loads valid labware from these paths and makes them available to the protocol
  context" — i.e. you can simulate against your own labware definitions —
  [Opentrons: Executing and Simulating](https://docs.opentrons.com/python-api/reference/execute-simulate/)
- `opentrons_simulate` can be used to simulate protocols in the terminal, and "if there is a problem with
  the protocol, the simulation will stop and the error will be printed" —
  [Opentrons v1 docs: Using Python In Protocols](https://docs.opentrons.com/v1/writing.html)
- `opentrons_execute` runs protocols from the robot's command line
  (`opentrons_execute /data/my_protocol.py`), printing "the same run log shown in the Opentrons App, as
  the protocol executes," plus internal logs at warning level or higher; more options via
  `opentrons_execute --help` — [Opentrons: Command Line](https://docs.opentrons.com/python-api/advanced-control/command-line/)
- **What it catches, from the issue tracker and release notes:**
  - Max-volume enforcement: "Cannot aspirate more than pipette max volume" —
    [opentrons issue #5815](https://github.com/Opentrons/opentrons/issues/5815)
  - Dispense-vs-aspirate accounting: "Error handling when dispensing was added so that API endpoints now
    return an error if you try to dispense more than you've aspirated" —
    [opentrons release-notes.md](https://github.com/Opentrons/opentrons/blob/edge/api/release-notes.md)
  - Over-aspiration from unreset plunger after blowout —
    [opentrons issue #3797](https://github.com/Opentrons/opentrons/issues/3797)
  - Volume/tip precondition checking was an explicit feature request: "aspirate should check volume and
    tip attached before moving to location" — [opentrons issue #13197](https://github.com/Opentrons/opentrons/issues/13197)
  - Tip tracking: "Automatic tip tracking is now available for all nozzle configurations. All API versions
    now properly track tips, including starting at a well other than A1," with motion-planning
    improvements letting the robot "track tip usage more completely and reliably" —
    [opentrons release-notes.md](https://github.com/Opentrons/opentrons/blob/edge/api/release-notes.md)
- `opentrons.cli.analyze` exists as the analysis entry point: the Opentrons `protocol-evaluation`
  repository is "a FastAPI service for evaluating Opentrons protocols with asynchronous analysis plus
  simulation," with `opentrons.cli.analyze` producing analysis results, and an `/evaluate` endpoint
  accepting protocol files with optional custom labware, CSV data and runtime parameters —
  [GitHub Opentrons/protocol-evaluation](https://github.com/Opentrons/protocol-evaluation)
- Protocols declaring an API level above the maximum supported cannot be analyzed or run —
  [Opentrons versioning](https://docs.opentrons.com/v2/versioning.html)

**PyLabRobot**

- PyLabRobot is "an open-source, hardware-agnostic interface for liquid-handling robots and accessories" —
  [Wierenga et al., Device / ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2666998623001709);
  [PMC open version](https://pmc.ncbi.nlm.nih.gov/articles/PMC10369895/)
- Resource model: "In PLR every physical object is a subclass of the `Resource` superclass (except for
  `Tip`), and each subclass adds unique methods or attributes to represent its unique physical
  specifications and behavior"; the **PyLabRobot Resource Library (PLR-RL)** is "PyLabRobot's open-source,
  crowd-sourced collection of pre-made resource definitions" —
  [PyLabRobot Resource Management System docs](https://docs.pylabrobot.org/resources/)
- **Trackers:** "Tip trackers track the presence of tips on the pipetting head and tip spots in a tip rack
  and can distinguish between fixed or disposable tips; volume trackers track the liquids in liquid
  containers such as wells and mounted tips." Tip and volume state operations are gated by global
  `does_tip_tracking()` / `does_volume_tracking()` switches, and trackers "use a transaction pattern when
  validating and saving operations," so state changes are validated before commit —
  [PyLabRobot Resource Management docs](https://docs.pylabrobot.org/resources/);
  [PR #1349 "Tips: what a tip holds is state, and a tracker tells everyone who asked"](https://github.com/PyLabRobot/pylabrobot/pull/1349);
  [forum: volume tracker on mix cycles](https://labautomation.io/t/volume-tracker-on-mix-cycles/3798)
- **The visualizer does not simulate.** "The PyLabRobot visualizer renders the state of a running protocol
  in a browser and is implemented as a lightweight web application served by the `Visualizer` class in
  Python. The visualizer itself **does not perform any simulation logic**; instead it receives messages
  over a websocket from Python and passively updates the drawing." Source layout: `index.html`, `lib.js`
  (helper functions and resource definitions), `vis.js` (websocket setup and event handling), `main.css`,
  `gif.js`/`gif.worker.js`, `visualizer.py` —
  [PyLabRobot Visualizer Architecture](https://docs.pylabrobot.org/contributor_guide/visualizer.html)
- Known gap, recently addressed: "A tip has a volume tracker but was never published in its state, and its
  tracker was not wired to the state callbacks, so anything drawing what a tip holds read a field that
  never arrived and drew every tip empty" — [PR #1349](https://github.com/PyLabRobot/pylabrobot/pull/1349)

**SiLA 2** — not researched; see Gaps.

### Inferences

- **MVP labware data: vendor the Opentrons definitions, don't call Opentrons.** Copy the standard labware
  JSON files from `shared-data/labware/definitions/2/` (schema documented at
  [2.json](https://raw.githubusercontent.com/Opentrons/opentrons/edge/shared-data/labware/schemas/2.json))
  into the repo and load them into a dict keyed by `loadName`. Read `wells[*].totalLiquidVolume` for
  capacity, `ordering` for column-major well order (which is what you need for serial-dilution-across-a-row
  checks), and `parameters` for `isTiprack`/`loadName`. This is a ~30-line loader and it makes capacity
  checks exact and citable, with no network dependency and no Opentrons install.
- **Stretch: use `opentrons.simulate` as an independent oracle.** The value is not that it checks more than
  you do, but that it checks *differently* — and its errors are evidence that your IR is physically
  realisable. The pattern: emit your IR → generate an Opentrons Python protocol → call
  `simulate.simulate(f, custom_labware_paths=[...])` in-process and catch the exception
  ([signature](https://docs.opentrons.com/python-api/reference/execute-simulate/)). It "either returns
  (if the simulation has no problems) or raises an exception," which is a trivially wrappable contract.
  Report any exception as a single checker finding with code `SIM_OPENTRONS` and the exception text.
  A compelling demo line: *"and the same protocol passes Opentrons' own simulator."*
- **What the simulators actually catch, honestly stated:** pipette max volume
  ([#5815](https://github.com/Opentrons/opentrons/issues/5815)), dispense-exceeds-aspirate
  ([release notes](https://github.com/Opentrons/opentrons/blob/edge/api/release-notes.md)), tip
  presence/tracking ([release notes](https://github.com/Opentrons/opentrons/blob/edge/api/release-notes.md),
  [#13197](https://github.com/Opentrons/opentrons/issues/13197)), and API-version compatibility
  ([versioning](https://docs.opentrons.com/v2/versioning.html)). These are *robot-execution* errors.
  They do **not** check experimental design — nothing in the simulator knows what a control condition is,
  whether your dilution series has the right fold factor, or whether a numeric parameter has a citation.
  That gap is precisely the value proposition of the project, and the report should say so plainly.
- **Deck collisions: do not claim this is covered.** Opentrons release notes mention motion-planning
  improvements ([release notes](https://github.com/Opentrons/opentrons/blob/edge/api/release-notes.md))
  but I found no source confirming that simulation detects deck collisions or physical interference.
  Treat as unverified (see Gaps).
- PyLabRobot's transaction-pattern trackers with `does_volume_tracking()` gating
  ([docs](https://docs.pylabrobot.org/resources/)) are a good *design reference* for the volume-accounting
  pass in Q5 — validate-then-commit per operation, with a global switch so the check can be disabled for
  debugging. Worth imitating; not worth adopting PyLabRobot as a dependency in 48h.
- The visualizer's "no simulation logic" design ([docs](https://docs.pylabrobot.org/contributor_guide/visualizer.html))
  is a warning: a PyLabRobot *visual* demo proves nothing about checking. If the team wants visual impact,
  it should come from the checker's own output rendering, not from borrowing a viewer.

### Gaps

- **`opentrons analyze` CLI flags were not confirmed.** Multiple fetches of the Opentrons docs failed to
  surface a documented `opentrons analyze` page; the command-line docs page covers only `opentrons_execute`
  ([command-line docs](https://docs.opentrons.com/python-api/advanced-control/command-line/)). Existence of
  `opentrons.cli.analyze` is attested only indirectly via
  [protocol-evaluation](https://github.com/Opentrons/protocol-evaluation). **Someone must run
  `opentrons analyze --help` locally** — do not cite specific flags (including any `--json-output`) without
  that. Recommend using the Python `simulate.simulate()` API instead, which *is* documented.
- Whether Opentrons simulation detects **deck collisions / labware interference** is unconfirmed. No source
  found either way.
- The `_SimulateResult` return type's fields are undocumented in what I retrieved
  ([execute-simulate](https://docs.opentrons.com/python-api/reference/execute-simulate/)); the run-log
  shape is described loosely as "a list of dicts."
- **SiLA 2 feature definitions were not researched at all** — no searches were spent on them. No findings
  to report; the report should either omit SiLA 2 or flag it as unassessed. Prior expectation (unverified)
  is that SiLA 2 is a device-communication standard, i.e. orthogonal to static protocol checking.
- PyLabRobot's resource docs fetch at `/resources/index.html` returned 404; findings for PyLabRobot
  resources/trackers come from the `/resources/` landing page as surfaced in search plus PR threads and
  forum posts, which is weaker sourcing than I would like for the tracker API details.
- No source found for whether the Opentrons labware definitions carry an explicit license permitting
  vendoring. Check `shared-data`'s LICENSE before copying files into the repo.

---

## Q5. Static analysis patterns for procedures, and how earlier systems did it

### Takeaway

All six requested check families reduce to three classic static-analysis shapes: a reaching-definitions
dataflow pass (define-before-use), an abstract-interpretation-style accumulator over an ordered step list
(volume/resource accounting), and a set of relational queries over the step graph (ordering, controls,
replicates). Prior art is real but thin and mostly in the microfluidic-synthesis community, which solved
the harder *post-synthesis* version of the problem with symbolic constraint solving.

### Cited Findings

- **Microfluidic biochip verification** is the closest published prior art. A framework for automated
  correctness checking of biochemical protocol realizations on digital microfluidic biochips presents
  "a formal correctness checking framework for post-synthesis verification of biochemical mixing protocols
  implemented on digital microfluidic platforms," with a formulation that "allows modeling of several
  possible sources of design and implementation errors that may arise in the design of general-purpose,
  pin-constrained and cyberphysical biochips" — [arXiv 2211.04719](https://arxiv.org/abs/2211.04719);
  [PDF](https://arxiv.org/pdf/2211.04719)
- The method is **symbolic constraint-based**: "a symbolic constraint-based analysis and verification
  framework has been proposed for checking the correctness of synthesized bio-chemical protocols with
  respect to the original design specification, which detects realization errors and **generates
  diagnostic feedback to indicate the possible sources of design rule violations**" —
  [arXiv 2211.04719](https://arxiv.org/abs/2211.04719)
- Validated on **PCR protocols and in-vitro multiplexed bioassays** —
  [arXiv 2211.04719](https://arxiv.org/abs/2211.04719)
- Earlier version of the same line of work: "Correctness Checking of Bio-chemical Protocol Realizations on
  a Digital Microfluidic Biochip" — [IEEE Xplore 6733183](https://ieeexplore.ieee.org/document/6733183/)
- Verification is framed as operating in **two stages, pre- and post-synthesis** —
  [arXiv 2211.04719](https://arxiv.org/abs/2211.04719)
- Related end-to-end work: "A framework for end-to-end verification for digital microfluidics" —
  [Springer, Innov Syst Softw Eng](https://link.springer.com/article/10.1007/s11334-021-00398-3);
  and "A Framework for Translation and Validation of Digital Microfluidic Protocols" —
  [Springer chapter](https://link.springer.com/chapter/10.1007/978-981-16-4294-4_9)
- In-field testing of DMF biochips (a different failure class — hardware faults) —
  [ACM TODAES 10.1145/3123586](https://dl.acm.org/doi/10.1145/3123586)
- **Aquarium** is "an open-source, web-based software application that integrates experimental design,
  inventory management, protocol execution and data capture," containing its own LIMS —
  [Keller et al., Synthetic Biology (Oxford)](https://academic.oup.com/synbio/article/6/1/ysab006/6124325)
- Aquarium's dataflow model is explicit and is the key structural idea to borrow: "within plans, each input
  sample passes through a series of work modules termed **operations** to produce desired output samples and
  data. Operations are **wired together such that the output of one operation is automatically routed to and
  triggers the execution of one or more subsequent operations**" —
  [Aquarium paper](https://academic.oup.com/synbio/article/6/1/ysab006/6124325)
- Aquarium's typing discipline: "**Operation types are instantiated to operations when their input and
  output types are satisfied by items**" — i.e. a protocol step is only schedulable when typed
  preconditions on its inputs hold — [Aquarium paper](https://academic.oup.com/synbio/article/6/1/ysab006/6124325)
- Aquarium exposes a Python API, **Trident**, "that provides a common interface for other applications and
  scripts to interact with Aquarium, for example in planning complex workflows or extracting detailed
  datasets" — [Aquarium paper](https://academic.oup.com/synbio/article/6/1/ysab006/6124325);
  [Trident docs](http://klavinslab.org/trident/index.html)
- A downstream application of Aquarium's workflow model —
  [Plant Methods](https://link.springer.com/article/10.1186/s13007-023-01065-3);
  [PubMed 37653538](https://pubmed.ncbi.nlm.nih.gov/37653538)
- **LabOP's validation approach** (see Q1) is SHACL graph-shape conformance via pySHACL, checking that
  protocols are "complete, consistent, and valid data structures," exposed as `doc.validate()` —
  [LabOP docs](https://bioprotocols.github.io/labop/);
  [GitHub Bioprotocols/labop](https://github.com/Bioprotocols/labop)
- XDL propagates process information structurally: "XDL's internal XML-based representation propagates
  process information from steps to substeps" — [Mehr et al. PDF](https://eprints.gla.ac.uk/221626/1/221626.pdf)

### Inferences

- **Pattern (recommended) — define-before-use as reaching definitions.** Treat each step as a basic block
  in a linear (or DAG, if parallel branches are allowed) CFG. Maintain `defined: set[EntityId]`; seed it
  with the declared reagents/labware manifest. For each step in topological order: every `uses` identifier
  not in `defined` is an error (`DF001_UNDEFINED_REAGENT`) naming the step index and the identifier;
  then add the step's `produces` identifiers to `defined`. This is 25 lines and catches the single most
  common LLM failure mode (referencing a reagent it never declared). Aquarium's "operation types are
  instantiated to operations when their input and output types are satisfied by items"
  ([Aquarium](https://academic.oup.com/synbio/article/6/1/ysab006/6124325)) is exactly this discipline,
  enforced at schedule time rather than check time.
- **Pattern (recommended) — resource/volume accounting as abstract interpretation.** The accumulator from
  Q2 *is* a forward abstract-interpretation pass with the abstract domain being
  `container → exact rational volume` (and optionally `container → multiset[reagent]`, which you need
  anyway for the Q3 reactivity check). Two invariants asserted after every step:
  `0 ≤ volume(c) ≤ capacity(c)` and `volume(c) == sum of component volumes`. The second is the
  "volume conservation" property worth proving in Lean (Q1) precisely because it is a *mass-balance*
  statement rather than a bound.
- **Pattern (recommended) — ordering, controls, replicates as relational queries.** These are not dataflow;
  they are existence and counting queries over the whole protocol, and they are where a declarative engine
  earns its keep (Q6). Examples: "∃ a step with `role=negative_control` for every `assay` group";
  "`count(steps where role=sample and group=g) ≥ required_replicates(g)`"; "`incubate` precedes `read` for
  the same plate." In ASP each is one or two rules. In Python each is a comprehension. Either is fine;
  the important part is that the *required* controls and replicate counts come from a **declared
  experimental-design block in the IR**, not from the checker's imagination — which is also what makes the
  anti-degradation invariants in Q7 enforceable.
- **Pattern (recommended) — source-reference completeness.** Walk the Pydantic model tree; for every field
  whose type is the `Quantity` wrapper, assert `source is not None` and that `source` resolves to an entry
  in the protocol's reference list. This is a generic tree walk over `model_fields`, ~15 lines, and gives
  you the "every numeric parameter carries a citation" check essentially for free — one of the highest
  ratio of demo-credibility to implementation cost in the entire project.
- The microfluidic literature's division into **pre-synthesis and post-synthesis** verification
  ([arXiv 2211.04719](https://arxiv.org/abs/2211.04719)) maps directly onto this project: the checker
  described in this assignment is *pre-synthesis* (does the protocol-as-specified make sense), while
  `opentrons.simulate` (Q4) is *post-synthesis* (does the compiled command sequence execute). Framing the
  two layers with this established vocabulary is a cheap credibility win, and it is honest.
- The fact that the biochip work needed **symbolic constraint solving** for post-synthesis checking, while
  pre-synthesis checking of a *fully concrete* protocol needs only evaluation, is the strongest argument
  for skipping Z3 in the MVP: the hard solving problem in that literature arises from unknowns introduced
  by synthesis (placement, routing, scheduling), which this project does not have.

### Gaps

- **BioCoder was not successfully researched.** It appeared in no search result in this session. I have no
  sourced findings on it; the report should omit it or mark it unassessed rather than describe it from
  memory.
- The microfluidic papers' *specific* error taxonomies and constraint encodings were not read in full
  (abstract-level sourcing only). If the report wants to borrow their error classification, someone should
  read [arXiv 2211.04719](https://arxiv.org/pdf/2211.04719) properly.
- Aquarium's checks are described at the level of its typed input/output model
  ([Aquarium paper](https://academic.oup.com/synbio/article/6/1/ysab006/6124325)); I found no evidence
  Aquarium performs volume or unit checking, so do not claim it does.
- No prior system was found that checks "every numeric parameter carries a source reference." This may be
  genuinely novel; stated as an absence-of-evidence finding, not a proof of novelty.

---

## Q6. Rule engines callable from Python, judged on diagnostic quality

### Takeaway

For a 48h build with LLM-consumable diagnostics, a plain Python rule registry wins on message quality and
clingo wins on expressiveness-per-line for the relational checks; Z3's unsat cores and clingo's cores both
require extra work to become readable, and clingo's cores are documented as **not minimal**, which is a
real trap. Recommend: Python registry for MVP, clingo for the ordering/controls/replicates rules as the
stretch, and Z3 only if the project needs repair *synthesis* rather than checking.

### Cited Findings

- **clingo** exposes unsat cores through `SolveHandle.core()`, "the subset of assumptions that made the
  problem unsatisfiable," returning a list of integers (solver literals); `Control.solve()` accepts an
  `on_core` callback "called with the assumptions that made a problem unsatisfiable" —
  [clingo.solving API docs](https://potassco.org/clingo/python-api/5.7/clingo/solving.html);
  [clingo.control API docs](https://potassco.org/clingo/python-api/5.7/clingo/control.html)
- **Two documented traps.** `SolveHandle.core()` "returns solver literals whose signs do not map naively
  onto assumption symbols," and **the core is also not minimal** — demonstrated by a case where "for a
  program with three facts where exactly two conflict and the third appears in no rule at all, the core
  named all three" — [clingo.solving docs](https://potassco.org/clingo/python-api/5.7/clingo/solving.html);
  [SmartMDAO PR #18](https://github.com/wghami/SmartMDAO/pull/18)
- Remedy exists: **clingo-explaid**, "Tools to aid the development of explanation systems using clingo,"
  providing an `AssumptionPreprocessor` and `CoreComputer` for computing **Minimal Unsatisfiable Subsets
  (MUS)**, with `shrink()` to refine cores and `mus_to_string()` to format results —
  [GitHub potassco/clingo-explaid](https://github.com/potassco/clingo-explaid)
- **clorm** provides an ORM-style Python↔clingo mapping, reducing the boilerplate of moving typed Python
  objects into ASP facts — [clorm docs](https://clorm.readthedocs.io/_/downloads/en/v1.6.1/pdf/)
- Older clingo Python API versions are separately documented —
  [clingo Python API 5.4](https://potassco.org/clingo/python-api/5.4/);
  [clingo preview API](https://potassco.org/clingo-preview/python-api/clingo/solve.html)
- clingo has had correctness issues in auxiliary-variable introduction —
  [clingo issue #673](https://github.com/potassco/clingo/issues/673)
- Background on the concept — [Unsatisfiable core (Wikipedia)](https://en.wikipedia.org/wiki/Unsatisfiable_core)
- Research evidence that engine *message quality* is the binding constraint for LLM loops, not engine
  power: "Compiler-level feedback is identified as the critical bottleneck in dependently typed languages
  compared to execution-based feedback" — [arXiv 2602.11481, Compiler-Guided Inference-Time Adaptation (Idris)](https://arxiv.org/pdf/2602.11481)
- Converse evidence that good messages work: "Rust compiler error messages are often helpful for LLMs to
  fix mistakes" — [arXiv 2512.02567, Feedback Loops and Code Perturbations in LLM-based SE](https://arxiv.org/html/2512.02567v1)

### Inferences

- **MVP: a plain Python rule registry.** A decorator-registered list of pure functions
  `(protocol) -> Iterable[Finding]`, where `Finding` is a frozen dataclass. Advantages that matter at
  hour 30: every message is hand-written, so every message is precise; findings are trivially sortable and
  deduplicable; the whole thing is debuggable with a breakpoint; and it adds **zero** install risk.
  **Pattern (recommended):**
  ```python
  @rule("VOL002", severity="error")
  def well_capacity(p: Protocol) -> Iterable[Finding]:
      for step, well, vol, cap in volume_balance(p):
          if vol > cap:
              yield Finding(
                  code="VOL002",
                  loc=f"steps[{step.index}].transfers[{...}]",   # JSON pointer into the IR
                  message=f"well {well.name} receives {vol} uL, labware max is {cap} uL",
                  observed=str(vol), limit=str(cap),
                  fix_hint=f"split across wells or reduce transfer to <= {cap} uL",
                  evidence=well.definition_uri,
              )
  ```
  This yields exactly the target message from the assignment: *"step 4: well A12 receives 350 µL, labware
  max is 300 µL"* — because the rule author wrote it, not because an engine rendered it.
- **Stretch: clingo for the relational layer.** Ordering, control-presence and replicate-count rules are
  where ASP's declarative form is genuinely shorter and less bug-prone than imperative graph code. But do
  **not** rely on `core()` for diagnostics: it is non-minimal and its literal signs don't map naively to
  assumption symbols ([clingo docs](https://potassco.org/clingo/python-api/5.7/clingo/solving.html)).
  Instead, invert the formulation — **don't make the program UNSAT at all.** Write the rules so violations
  are *derived atoms*:
  ```prolog
  violation("CTRL001", G, "missing negative control") :- assay_group(G),
      not step(_, G, negative_control).
  violation("REP001", G, "replicates below declared minimum") :- required_replicates(G, N),
      #count{ S : step(S, G, sample) } < N.
  ```
  Then enumerate the `violation/3` atoms from the single answer set. You get precise, per-violation
  diagnostics with no core machinery, no MUS shrinking, and no need for clingo-explaid. **This is the
  single most important practical recommendation in this section.** If MUS really is needed later,
  clingo-explaid's `CoreComputer`/`shrink()`/`mus_to_string()` is the documented route
  ([clingo-explaid](https://github.com/potassco/clingo-explaid)), and clorm removes the fact-marshalling
  boilerplate ([clorm](https://clorm.readthedocs.io/_/downloads/en/v1.6.1/pdf/)).
- **Z3py: skip for MVP.** Checking a fully concrete protocol is evaluation, not solving (see Q5
  inference). Z3's genuine uses here are (a) *suggesting* a repair — ask for a model of
  "all constraints ∧ volumes within ±20% of declared" to propose concrete corrected numbers, and
  (b) checking a *parameterised* protocol template over a range of inputs. Both are stretch. Z3's unsat
  cores have the same readability problem as clingo's, so the same inversion trick applies: assert
  violations as named boolean indicators rather than relying on core extraction.
- **Soufflé: not recommended for this build.** It is a compiled Datalog targeting large-scale program
  analysis; the C++ compile step and the lack of an in-process Python API make it a poor fit for a
  48-hour deliverable where the fact base is a few hundred atoms. (Inference; no source consulted on
  Soufflé this session — see Gaps.)
- **OPA/Rego: not recommended.** It is built for authorization policy; findings would require a separate
  process or wasm host, and Rego's error reporting is oriented to allow/deny decisions, not to rich
  diagnostics. (Inference; unsourced this session — see Gaps.)
- The Idris finding — that compiler feedback quality is "the critical bottleneck in dependently typed
  languages" ([arXiv 2602.11481](https://arxiv.org/pdf/2602.11481)) — is **directly relevant to the Lean
  question in Q1** and should be cited there too: it is published evidence that raw Lean type errors will
  *not* drive an LLM repair loop well. If Lean is in the pipeline, its failures must be translated into
  the same `Finding` schema as everything else.

### Gaps

- **Soufflé, OPA/Rego and Z3py were not researched with dedicated searches** in this session. The
  recommendations above are reasoned inferences from their design goals, not sourced findings. The report
  should either mark them as such or spend searches on them. In particular I have **no citation** for Z3py's
  unsat-core API or `assert_and_track`, despite referencing the technique.
- No head-to-head benchmark of diagnostic quality across these engines was found; the ranking is
  reasoned, not measured.
- clingo version currency: API docs consulted are 5.7
  ([link](https://potassco.org/clingo/python-api/5.7/clingo/solving.html)). Whether a newer release exists
  as of Oct 2026 was not checked.

---

## Q7. Structuring checker output for a convergent LLM repair loop, and preventing degradation-by-repair

### Takeaway

There is now published work modelling LLM self-correction as a control system with explicit stability
thresholds, which gives a principled reason to cap iterations and to require monotone progress. The
anti-degradation problem — the LLM deleting steps or dropping controls to satisfy the checker — is best
solved structurally: make the experimental design a *separate, immutable* section of the IR, diff it
across repair rounds, and treat any reduction as a hard failure rather than a repair.

### Cited Findings

- Self-correction can be modelled "as a two-state Markov chain parameterized by **Error Introduction Rate
  (EIR)** and **Error Correction Rate (ECR)**. When both rates are low (typical for strong models),
  convergence is slow; when rates are high, convergence is fast but the **steady-state may be poor**" —
  [arXiv 2604.22273, Self-Correction as Feedback Control: Error Dynamics, Stability Thresholds, and Prompt Interventions in LLMs](https://arxiv.org/html/2604.22273v2)
- "**Error-aware repair loops retain erroneous code, error messages, and references from the previous
  context**, enabling the LLM to reason about failures and propose corrected versions" —
  [arXiv 2601.00509, Improving LLM-Assisted Secure Code Generation](https://www.arxiv.org/pdf/2601.00509)
- Multi-tool repair workflows combine several deterministic oracles rather than one: "retrieval-augmented,
  multi-tool repair workflows where LLMs iteratively refine code outputs using **compiler diagnostics,
  CodeQL security scanning, and KLEE symbolic execution**" —
  [arXiv 2601.00509](https://www.arxiv.org/pdf/2601.00509)
- Compiler feedback quality is the binding constraint, and it is worse for dependently typed languages:
  "Compiler-level feedback is identified as the critical bottleneck in dependently typed languages
  compared to execution-based feedback" —
  [arXiv 2602.11481, Compiler-Guided Inference-Time Adaptation (GPT-5 / Idris)](https://arxiv.org/pdf/2602.11481)
- Message quality demonstrably transfers: "Rust compiler error messages are often helpful for LLMs to fix
  mistakes" — [arXiv 2512.02567, Feedback Loops and Code Perturbations in LLM-based Software Engineering (C-to-Rust)](https://arxiv.org/html/2512.02567v1)
- Iterative refinement with combined compiler errors and testcase feedback is the standard evaluated
  setup — [arXiv 2606.17514, Unlocking LLM Code Correction with Iterative Feedback Loops](https://arxiv.org/html/2606.17514);
  [ACL Findings 2024, Prompting the Coding Ability of LLMs](https://aclanthology.org/2024.findings-acl.124.pdf)
- Analogous work on feeding *localized* reasoning errors rather than global failure signals —
  [arXiv 2605.17914, Guiding LLM-based Loop Invariant Synthesis via Feedback on Local Reasoning Errors](https://arxiv.org/pdf/2605.17914)
- The microfluidic verification framework likewise emphasises "diagnostic feedback to indicate the
  **possible sources** of design rule violations" rather than a bare pass/fail —
  [arXiv 2211.04719](https://arxiv.org/abs/2211.04719)

### Inferences

- **Pattern (recommended) — the `Finding` schema.** Emit JSON, one object per violation, with these fields,
  all of which are cheap and each of which does a job:
  ```json
  {
    "code": "VOL002",
    "severity": "error",
    "loc": "/steps/4/transfers/0/volume",
    "message": "well A12 receives 350 uL, labware max is 300 uL",
    "observed": "350 uL",
    "limit": "300 uL",
    "evidence": "https://labware.opentrons.com/...  (totalLiquidVolume)",
    "fix_hint": "reduce transfer to <= 300 uL, or split across A12 and B12",
    "invariant_guard": ["replicate_count", "control_set"]
  }
  ```
  - **`code` must be stable and never reused.** It is what lets you detect oscillation (same code set
    across rounds *n* and *n+2*) and what lets you build a per-code fix-hint table. Namespace by family:
    `UNIT*`, `ARITH*`, `VOL*`, `RANGE*`, `DF*` (dataflow), `DESIGN*`, `CITE*`, `REACT*`, `SIM*`.
  - **`loc` must be a JSON Pointer into the IR**, not a line number — the LLM edits a JSON document, so a
    pointer is directly actionable and survives reformatting. Pydantic v2 validation errors already carry
    a `loc` tuple, so native and custom findings share one location convention for free.
  - **`observed` and `limit` separately from `message`.** The prose message is for humans; the structured
    pair is what lets the LLM compute a correct new value rather than guess. This is the localized-feedback
    principle from [arXiv 2605.17914](https://arxiv.org/pdf/2605.17914) applied to numbers.
  - **`evidence` (a URL) is the anti-hallucination field**: it lets the LLM — and a human reviewer — see
    that the limit came from a labware definition or a CAMEO datasheet, not from the checker's opinion.
- **Pattern (recommended) — loop control derived from the EIR/ECR result.** Because strong models converge
  slowly and high-rate regimes reach poor steady states
  ([arXiv 2604.22273](https://arxiv.org/html/2604.22273v2)), do not let the loop run free:
  1. Hard cap at 3–5 rounds. On exhaustion, **fail and surface findings to a human** rather than shipping.
  2. **Require monotone progress on a lexicographic key** `(n_errors, n_warnings)`. If round *n+1* is not
     strictly better, abort — this directly detects the non-convergent regime.
  3. **Detect oscillation** by hashing the sorted `(code, loc)` multiset each round; a repeat means the
     loop is cycling, so stop and escalate.
  4. **Keep the full history in context** — prior protocol, prior findings, and what was changed — per the
     error-aware repair-loop finding ([arXiv 2601.00509](https://www.arxiv.org/pdf/2601.00509)).
  5. **Send all findings at once, not one at a time**: repairing one at a time invites the LLM to make
     changes that break a rule it can't see.
- **Pattern (recommended) — anti-degradation invariants.** This is the part that cannot be solved by better
  error messages, because a *correct* repair and a *degrading* repair can both satisfy the checker. Make it
  structural:
  1. **Split the IR into a `design` block and an `execution` block.** `design` holds: replicate counts per
     group, the required control set, the declared endpoints/readouts, and the declared sample size.
     `execution` holds the steps.
  2. **The repair prompt is only allowed to return a new `execution` block.** The `design` block is
     re-attached by the orchestrator from the *original* protocol, not from the model's output. The LLM
     cannot delete a control condition it is not permitted to rewrite. This is the strongest single control
     available and it costs almost nothing to implement.
  3. **Add a `DESIGN*` rule family that checks `execution` against `design`**, so dropping a control or a
     replicate in the steps now *creates* an error instead of removing one:
     `DESIGN001` controls declared in `design` but absent from `execution`;
     `DESIGN002` replicate count in `execution` below `design.required_replicates`;
     `DESIGN003` a declared readout never produced by any step.
  4. **Diff-based monotonicity gate, run before the checker.** Reject any candidate where, relative to the
     *original*, `len(steps)` decreased, a step with `role in {positive_control, negative_control, blank}`
     disappeared, any replicate count decreased, or a declared readout vanished. Report these as
     `GUARD*` findings so the LLM learns the boundary. Note the asymmetry: a *legitimate* repair almost
     never needs to delete a control, so a strict gate has a low false-positive cost.
  5. **Anchor numeric parameters to their citations.** Since every numeric parameter already carries a
     `source` (Q5), make it an error to *change* a cited value while keeping the citation
     (`CITE002_VALUE_DIVERGES_FROM_SOURCE`). This blocks the laziest degradation path of all: silently
     retuning a literature-derived concentration until the arithmetic closes.
  6. **Distinguish `error` from `warning` and never let the loop "fix" a warning by deletion** — require
     that the count of `design`-block entities is non-decreasing across every round.
- **Pattern (recommended) — multi-oracle, following [arXiv 2601.00509](https://www.arxiv.org/pdf/2601.00509).**
  Run the Python rule registry, the Opentrons simulation (Q4) and (stretch) the Lean export as three
  independent oracles, normalising all three into the same `Finding` schema. For Lean specifically, the
  Idris finding ([arXiv 2602.11481](https://arxiv.org/pdf/2602.11481)) means a raw Lean error must be
  *translated* — map each expected failure to a `code` and a hand-written message rather than piping
  Lean's output to the model.

### Gaps

- All the repair-loop papers cited are about **code** repair (Rust, Idris, C-to-Rust, general program
  repair). **No study was found on LLM repair loops over scientific-protocol or experimental-design
  artifacts**, so the transfer of the EIR/ECR convergence model and the message-quality findings to this
  domain is an inference, not a demonstrated result. The report should say so.
- Likewise, **no published work was found on the specific degradation failure mode** (an LLM satisfying a
  validator by weakening the experiment). The invariant-preservation design above is this researcher's
  proposal, not a documented technique. This is a notable gap and arguably the most interesting
  contribution the hackathon project could claim — but it must be presented as untested.
- The EIR/ECR paper's quantitative stability thresholds were read at summary level only
  ([arXiv 2604.22273](https://arxiv.org/html/2604.22273v2)); do not cite specific threshold numbers
  without reading it.
- Several cited arXiv preprints (2601.00509, 2602.11481, 2604.22273, 2605.17914, 2606.17514) are recent
  preprints, likely unpeer-reviewed. Weight accordingly.

---

## Cross-cutting: MVP vs stretch summary

(Synthesis of the above; individual claims sourced in their sections.)

**MVP — hours 0–24, must all land**
1. IR: Pydantic v2 models, `Quantity{value: Fraction, unit: UCUM-string, source: Ref}`; JSON Schema
   auto-exported for generation-time constraint
   ([ucumvert](https://github.com/dalito/ucumvert), [pint](https://pint.readthedocs.io/en/stable/)).
2. Vendored Opentrons labware JSON; `totalLiquidVolume` as the capacity oracle
   ([schema 2](https://raw.githubusercontent.com/Opentrons/opentrons/edge/shared-data/labware/schemas/2.json)).
3. Rule registry with ~12 rules covering: dimensional consistency, C1V1=C2V2, serial-dilution fold factor,
   well capacity (per-step, both bounds), equipment range predicates, define-before-use, controls present,
   replicate counts, citation presence.
4. `Finding` JSON schema with stable codes, JSON-Pointer `loc`, `observed`/`limit`, `evidence`, `fix_hint`.
5. Static hazard table for the demo's reagent set: CAMEO reactive groups + pairwise incompatibilities,
   hand-curated with `/react/{id}` citations, failing closed on unknown reagents
   ([CAMEO reactive groups](https://cameochemicals.noaa.gov/browse/react)).
6. Repair loop with 3-round cap, monotone-progress gate, oscillation detection, and the
   `design`-block-is-immutable rule.

**Stretch — hours 24–48, in this priority order**
1. `design` vs `execution` split plus the `DESIGN*`/`GUARD*` rule families (highest value per hour; this is
   the project's differentiator).
2. PubChem PUG-View GHS lookup with on-disk cache, pre-warmed
   ([PUG-View](https://pubchem.ncbi.nlm.nih.gov/docs/pug-view); 5 req/s limit per
   [IUPAC Cookbook](https://iupac.github.io/WFChemCookbook/datasources/pubchem_pugrest1.html)).
3. Opentrons export + in-process `simulate.simulate()` as a second oracle
   ([execute-simulate](https://docs.opentrons.com/python-api/reference/execute-simulate/)).
4. Mathlib-free Lean 4 package: `Vol`/`Conc` structures over `Rat`, one volume-conservation theorem,
   `decide`-discharged range predicates, failing to compile on a bad fragment.
5. clingo layer for ordering/controls/replicates using derived `violation/3` atoms (not unsat cores)
   ([clingo docs](https://potassco.org/clingo/python-api/5.7/clingo/solving.html)).

**Explicitly out of scope for 48h:** adopting LabOP/XDL/Autoprotocol as the IR; OWL+SHACL; LinkML;
Soufflé; OPA/Rego; vendoring ATOMSLab's Lean library; ECHA or NIOSH scraping; SiLA 2.

**What cannot be checked deterministically — state this honestly in the demo**
- Whether the experiment answers the scientific question; whether controls are the *right* controls as
  opposed to merely present; whether replicate counts are adequately *powered* (that requires an effect-size
  assumption the checker does not have).
- Whether a cited source actually supports the cited number (the checker verifies a citation *exists* and
  is *unchanged*, not that it is *apt*).
- Biological/chemical plausibility beyond tabulated incompatibilities: enzyme-buffer compatibility,
  inhibitor carryover, incubation sufficiency, reagent stability and order-of-addition chemistry. CAMEO
  covers bulk-hazard reactivity, not assay performance
  ([CAMEO](https://response.restoration.noaa.gov/oil-and-chemical-spills/chemical-spills/chemical-reactivity-worksheet)).
- Any reagent with no reactive-group assignment — hence the fail-closed `REACT_UNKNOWN_GROUP` warning.
- Physical feasibility beyond what the simulator models: deck collisions are **unverified** as covered
  (see Q4 Gaps); dead volumes, meniscus/tip-geometry effects and evaporation are not modelled.
- Timing/temporal correctness beyond declared ordering: real-time constraints, hands-on-time feasibility,
  and whether two steps can actually be executed in parallel by one operator.

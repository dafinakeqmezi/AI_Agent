# Responsible AI and ethics

Relevant requirements: **DOC-003, DATA-005, DATA-001**.
Key sources: `gebru2021datasheets`, `mitchell2019modelcards`, `bender2021parrots`.

## What a good student ethics section covers (scaled to the project)

- **Data**: consent, personal data and privacy (GDPR where applicable), license, representativeness, known biases (Datasheets for Datasets).
- **Model**: intended use and out-of-scope use, performance across relevant subgroups where data allows, failure modes (Model Cards).
- **Impact**: who could be harmed by errors (false positives vs false negatives), potential misuse.
- **Generative AI / LLM projects**: hallucination, harmful content, training-data provenance, cost and environmental footprint (Bender et al. 2021).
- **AI usage disclosure**: how AI assistants were used in producing the project (see `policies/integrity-policy.json` ai_usage_policy).

## Grading guidance

- Generic boilerplate ("AI can be biased") with no link to the project counts as PARTIAL.
- Absence is MISSING. It is non-mandatory by default; check the course rubric, which may make it mandatory.

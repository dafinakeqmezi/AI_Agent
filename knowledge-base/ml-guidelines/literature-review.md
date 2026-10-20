# Literature review and citation verification

Relevant requirements: **LIT-001 to LIT-004**; integrity indicators **INT-001, INT-002, INT-009**.

## Source credibility (highest first)

1. Peer-reviewed journals and major conferences (NeurIPS, ICML, ICLR, ACL, EMNLP, CVPR, KDD, AAAI, IJCAI, FAccT, ...)
2. Official documentation / standards bodies (scikit-learn docs, ISO, NIST, EU AI Act text)
3. arXiv preprints from identifiable authors (acceptable for recent work; note they are not peer reviewed)
4. Technical reports from recognized labs
5. Blogs, Medium, tutorial sites, Wikipedia: **not acceptable as sole support for scientific claims**. Recommend replacing them with 1-3.

## Verification procedure

1. Run `python -m grader cite <project> --out <dir>`. It extracts DOIs and arXiv IDs, queries Crossref/arXiv, and compares titles.
2. For references without an identifier, verify by title: `python -m grader cite --title "<title>"` (Crossref bibliographic search), or WebSearch the exact title.
3. Status per reference:
   - `VERIFIED`: exists; title/authors/year correspond
   - `MISMATCH`: identifier resolves to a different paper (possible fabrication, INT-009)
   - `NOT_FOUND`: no record found by identifier or title (INT-001, needs human review)
   - `UNVERIFIED`: could not check (network error, book without DOI); not an integrity indicator by itself
4. Spot-check claim support: for the 3-5 most important citations, check that the abstract supports the claim (INT-002).

## Quality of the review (LIT-001, LIT-004)

- Synthesis: groups prior work by approach, compares results, and states limitations. A plain list of papers is PARTIAL at best.
- Includes baseline/methodology references for the chosen methods and metrics.
- Identifies a gap that the project addresses.
- Recency (LIT-002): for fast-moving topics (LLMs, generative models), at least some references from the last 2-3 years.

## Recommending literature

Agents may recommend only references that are in `literature/references.json` or that they have verified in this session (DOI resolves and the title matches). **Never invent papers.** If unsure, recommend a search strategy (venues, keywords) instead of specific papers.

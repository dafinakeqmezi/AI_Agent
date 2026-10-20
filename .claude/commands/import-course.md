---
description: Convert the professor's course documents into requirements.json, rubric.json, dod.json and the AI-usage policy
---

Convert the documents in `knowledge-base/course/` (and any university policies in `knowledge-base/policies/`) into the machine-readable academic contract.

1. Read every document in `knowledge-base/course/` and any PDF/DOCX policies in `knowledge-base/policies/`. If there are none, say so and stop.
2. Draft updated versions of:
   - `knowledge-base/rubric/rubric.json`: criteria, weights, grade scale exactly as the professor defines them
   - `knowledge-base/requirements/requirements.json`: requirements mapped to criteria. Points per criterion must sum to the criterion weight. Mark `mandatory` only when the documents say so
   - `knowledge-base/requirements/dod.json`: required deliverables and must-pass items
   - the `ai_usage_policy` section of `knowledge-base/policies/integrity-policy.json`
3. **Never invent** criteria, weights, requirements or grade bands that are not in the documents. Where the documents are silent, either keep the existing placeholder entry and mark it `"source": "PLACEHOLDER (not in course documents)"`, or list it as an open question.
4. Give each requirement a `"source"` field quoting where it comes from (document + page/section).
5. Show the user a summary of the changes and the open questions, and get confirmation before writing.
6. After writing, set `"status": "OFFICIAL"` only on files fully derived from course documents. Bump `version` in each changed file and in `knowledge-base/manifest.json` (with a changelog entry).
7. Run `python -m grader versions`, and run `python -c "from grader.score import check_config; from grader.common import *; print(check_config(load_json(RUBRIC_FILE), load_json(REQUIREMENTS_FILE)['requirements']))"`. The second command must print `[]`.
8. Warn that any earlier evaluations were made under the old rubric version, which is recorded in their final.json.

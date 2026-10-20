# Detyra 1 guidelines: uninformed search (for Agent 1 and Agent 2)

Authority level 4 (established literature), below `knowledge-base/course/ai-2026-27/Detyra1.md` and this assignment's `requirements.json`. Use it to judge evidence. Never deduct for anything that is not a requirement.

Course literature (README-lenda.md): AIMA ch. 3 (uninformed search), Michalewicz & Fogel, *How to Solve It: Modern Heuristics* ch. 1-3 (representation, objective/evaluation function, search space), the TU Wien slides "Basic Concepts" and "Uninformed Search" (Musliu). AIMA 4th ed. is indexed in `knowledge-base/literature/books/aima4/` (ch. 3: §3.4 uninformed search, §3.4.3 DFS, §3.4.4 IDDFS; ch. 6 CSP and backtracking).

## What the four parts of every problem mean

| Requirement | What must be present | Typical weak answer (PARTIAL) | MISSING |
|---|---|---|---|
| Modelling (-001) | Inputs, what is sought, all hard constraints, the question being answered | Constraints incomplete (e.g. Sudoku without the 3x3 boxes) | Only the code |
| Representation (-002) | Variables, domains, constraints, and how a (partial) solution is stored | Names a data structure but not the domains or constraints | Absent |
| Objective function (-003) | A function of a candidate solution with the goal value (usually: number of violated constraints, goal 0) | "Find a valid solution" with no function | Absent |
| Landscape (-004) | Size of the search space derived from *their* representation, with the arithmetic | Correct order of magnitude but no derivation, or a formula inconsistent with their representation | Absent |
| Algorithm (-005) | The *named* algorithm with backtracking, running and producing outputs that satisfy all constraints | Correct algorithm but fails on some instances / no evidence that output was checked | Wrong algorithm under the right name, or code that does not run |

Documentation may be in any language (Albanian is expected), in README, PDF, DOCX, notebooks or code comments.

## Recognising the algorithms in code

- **DFS**: recursion (`def solve(...): ... solve(...)`) or an explicit stack (`list.append` + `list.pop()`). Explores one branch to the bottom before siblings.
- **BFS**: an explicit FIFO frontier: `collections.deque` with `popleft()`, `queue.Queue`, or a list processed level by level (`for node in level: next_level.append(...)`). **Recursion alone is not BFS**, whatever the function is called.
- **IDDFS**: an outer loop `for limit in range(...)` (or `while`) calling a **depth-limited** DFS that stops at `depth == limit`. A single unbounded DFS is not IDDFS, even if a variable is called `depth`.
- **Backtracking**: before extending a partial solution the constraints are checked (`is_valid`, `is_safe`), and the change is undone when returning (`grid[r][c] = 0`, `pop()`), or the state is copied per node. For BFS, "backtracking" means inconsistent partial states are pruned and never enqueued.
- Check what the code *does*, not what it is named. Quote the lines (file + L-range) that prove the algorithm.

## Problem-specific facts

### Social Golfers (8 groups x 4 players = 32, w weeks)
- Each player meets 3 others per week and there are 31 others, so **w <= floor(31/3) = 10**. Ten weeks is the upper bound; plain DFS with backtracking typically schedules far fewer weeks in reasonable time. Reporting the number of weeks reached within a stated time limit is acceptable; claiming 10 weeks requires showing the schedule and checking it.
- Landscape, one week, 8 unlabelled groups of 4: 32!/((4!)^8 * 8!) = **59,287,247,761,257,140,625 (about 5.93e19)**. Labelled groups: 32!/(4!)^8 (about 2.39e24). Permutation representation: 32! (about 2.63e35). For w weeks: that number to the power w. Symmetry breaking (fix week 1, fix player 0 in group 1) legitimately reduces it; accept it if explained.
- Verify an output schedule: every week is a partition of 0..31 into groups of 4; no pair appears together twice.
- Literature: Dotú & Van Hentenryck (2005), *Scheduling Social Golfers Locally*, CPAIOR, LNCS, doi:10.1007/11493853_13 (verified 2026-10-20).

### Sudoku (BFS with backtracking, Easy / Medium / Hard)
- Landscape: 9^81 (about 1.97e77) for a blank grid; for a puzzle with k empty cells, **9^k**; row-permutation representation (9!)^9 (about 1.09e50).
- BFS on Sudoku has a large frontier; Hard puzzles may be slow or run out of memory. That is a property of BFS and is acceptable if the student reports it honestly. Do not deduct for slowness unless the program does not finish within a reasonable timeout on the student's own puzzles.
- SUD-006 needs all three levels demonstrated (puzzles or a level choice, plus outputs).
- Verify: rows, columns and 3x3 boxes are permutations of 1..9 and the givens are unchanged.

### Latin Square (IDDFS with backtracking)
- Landscape: n^(n^2) per-cell (n = 5: about 2.98e17) or (n!)^n with rows as permutations (n = 5: about 2.49e10).
- The cyclic construction (shift each row by one, the example output in Detyra1.md) is **not a search algorithm**. If the program only prints the cyclic pattern, LAT-005 is MISSING even though the output is a valid Latin square.
- Verify: each row and each column is a permutation of 1..n.

### Search trees (8-Puzzle, Missionaries and Cannibals, Rotating Workforce Scheduling)
- 8-Puzzle: state = 3x3 board; actions move the blank (2-4 children); 9!/2 = 181,440 reachable states; show several levels and mark repeated states.
- Missionaries and Cannibals (3, 3): state (M, C, boat) on the start bank; 5 loads; prune states where cannibals outnumber missionaries on either bank; the shortest solution has 11 crossings.
- Rotating Workforce Scheduling (Musliu et al.): a cyclic schedule of n weeks x 7 days with shift types (e.g. D, A, N, -); a node is a partial schedule; branching assigns a shift to the next slot; prune on daily workforce requirements, min/max lengths of work blocks and days-off blocks, and forbidden shift sequences. A small instance is fine. Literature: Musliu, Gärtner & Slany (2002), *Efficient generation of rotating workforce schedules*, Discrete Applied Mathematics 118(1-2), doi:10.1016/S0166-218X(01)00258-X (verified 2026-10-20).
- Trees may be drawings, images, text trees or program output. Judge correctness of states and transitions, not drawing quality.

## Running student code safely
Copy the submission to the scratchpad before running anything; never run inside `submissions/`. Use a timeout (e.g. 60 s per program). Write an independent checker for the outputs (the checks above). Record what you ran and what happened as evidence.

## Integrity notes specific to this assignment
- Short backtracking solvers for Sudoku, N-Queens and Latin squares are widely published (GeeksforGeeks, Rosetta Code, aima-python, textbook pseudocode). Identical structure to textbook pseudocode is expected and is **not** an indicator. Verbatim or near-verbatim copies of a public solution without attribution are INT-004 indicators (human review).
- The Latin-square example output in Detyra1.md is itself the cyclic pattern, so many students will print the same matrix. Identical output is not evidence of copying.
- **Cross-student similarity**: the professor's similarity report (`python -m grader similarity`) compares all submissions. Code that is common to many submissions (typical helper functions, the course's example) is filtered out. A high similarity between two students is a risk indicator that the professor reviews with the matched regions and the commit timeline. It never changes a score automatically and is never stated as proof of copying.

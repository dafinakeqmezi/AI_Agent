"""Latin Square me Iterative Deepening Depth First Search (IDDFS) dhe backtracking.

Modeli: një nivel i pemës = një rresht i plotë. Fëmijët e një nyjeje janë të gjitha rreshtat
(permutacionet e 1..n) që nuk përsërisin asnjë vlerë në kolona me rreshtat e mëparshëm.
Rreshtat gjenerohen qelizë pas qelize me backtracking.
Thyerja e simetrisë: rreshti i parë fiksohet 1..n (çdo katror latin mund të riemërtohet në këtë formë).
IDDFS: kufiri i thellësisë rritet 1, 2, ..., n; zgjidhja gjendet kur kufiri arrin n rreshta.
Përdorimi: python latin.py [n]
"""
import sys


def compatible_rows(rows, n):
    """Gjeneron me backtracking çdo rresht që respekton kolonat e rreshtave ekzistues."""
    row, used = [], set()

    def extend(col):
        if col == n:
            yield list(row)
            return
        for value in range(1, n + 1):
            if value not in used and all(r[col] != value for r in rows):
                row.append(value)
                used.add(value)
                yield from extend(col + 1)
                row.pop()  # backtracking
                used.discard(value)

    yield from extend(0)


def depth_limited(rows, limit, n, stats):
    stats["nodes"] += 1
    if len(rows) == n:
        return rows
    if len(rows) == limit:
        return None
    for row in compatible_rows(rows, n):
        found = depth_limited(rows + [row], limit, n, stats)
        if found:
            return found
    return None


def iddfs(n):
    stats = {"nodes": 0, "iterations": 0}
    start = [list(range(1, n + 1))]
    for limit in range(1, n + 1):
        stats["iterations"] += 1
        found = depth_limited(start, limit, n, stats)
        if found:
            return found, stats
    return None, stats


def objective(grid):
    """Numri i simboleve të dyfishta në rreshta dhe kolona; zgjidhja ka f = 0."""
    n = len(grid)
    rows = sum(n - len(set(r)) for r in grid)
    cols = sum(n - len({grid[r][c] for r in range(n)}) for c in range(n))
    return rows + cols


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    grid, stats = iddfs(n)
    for row in grid:
        print(" ".join(map(str, row)))
    print(f"n = {n}, iterime IDDFS: {stats['iterations']}, nyje: {stats['nodes']}, objective f = {objective(grid)}")

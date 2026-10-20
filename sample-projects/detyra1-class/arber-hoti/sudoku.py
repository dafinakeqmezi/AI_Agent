"""Sudoku Solver me Breadth First Search (BFS) dhe backtracking.

Gjendja = tabelë e plotësuar pjesërisht. Çdo nivel i BFS plotëson një qelizë më shumë.
Backtracking: fëmija krijohet vetëm nëse vlera e re nuk shkel rreshtin, kolonën ose kutinë 3x3;
gjendjet e pavlefshme hidhen dhe nuk futen kurrë në radhë.
Përdorimi: python sudoku.py [easy|medium|hard]
"""
import sys
import time
from collections import deque

PUZZLES = {
    "easy": "530070000600195000098000060800060003400803001700020006060000280000419005000080079",
    "medium": "000260701680070090190004500820100040004602900050003028009300074040050036703018000",
    "hard": "000000907000420180000705026100904000050000040000507009920108000034059000507000000",
}


def parse(text):
    return [[int(text[r * 9 + c]) for c in range(9)] for r in range(9)]


def candidates(grid, row, col):
    used = set(grid[row]) | {grid[r][col] for r in range(9)}
    br, bc = 3 * (row // 3), 3 * (col // 3)
    used |= {grid[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3)}
    return [v for v in range(1, 10) if v not in used]


def choose_cell(grid):
    """Qeliza bosh me më pak kandidatë (renditje dinamike); None kur tabela është plot."""
    best = None
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                cand = candidates(grid, r, c)
                if best is None or len(cand) < len(best[2]):
                    best = (r, c, cand)
    return best


def solve_bfs(start):
    frontier = deque([start])
    expanded = 0
    while frontier:
        grid = frontier.popleft()  # FIFO: nyjet zgjerohen nivel pas niveli
        expanded += 1
        cell = choose_cell(grid)
        if cell is None:
            return grid, expanded
        row, col, values = cell
        for value in values:  # vetëm vlera të vlefshme (backtracking / pruning)
            child = [line[:] for line in grid]
            child[row][col] = value
            frontier.append(child)
    return None, expanded


def objective(grid):
    """Numri i shkeljeve: dyfishime në rreshta, kolona dhe kuti. Zgjidhja ka f = 0."""
    f = 0
    units = [grid[r] for r in range(9)] + [[grid[r][c] for r in range(9)] for c in range(9)]
    units += [[grid[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3)] for br in (0, 3, 6) for bc in (0, 3, 6)]
    for unit in units:
        values = [v for v in unit if v]
        f += len(values) - len(set(values))
    return f


if __name__ == "__main__":
    levels = sys.argv[1:] or list(PUZZLES)
    for level in levels:
        start = parse(PUZZLES[level])
        empty = sum(row.count(0) for row in start)
        t0 = time.time()
        solution, expanded = solve_bfs(start)
        print(f"[{level}] qeliza bosh: {empty}, landscape 9^{empty} = {9 ** empty:.2e}, nyje: {expanded}, koha: {time.time() - t0:.2f}s")
        for row in solution:
            print(" ".join(map(str, row)))
        print(f"objective f = {objective(solution)}")

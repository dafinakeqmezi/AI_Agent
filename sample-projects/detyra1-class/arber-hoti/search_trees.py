"""Search Trees për 8-Puzzle, Missionaries and Cannibals dhe Rotating Workforce Scheduling.

Pema ndërtohet nivel pas niveli (zgjerim në gjerësi) deri në thellësinë e dhënë.
Gjendjet e përsëritura shënohen me (përsëritje) dhe nuk zgjerohen më tej;
gjendjet e paligjshme shënohen me ✗ dhe krasiten.
Përdorimi: python search_trees.py [puzzle|mc|rws]
"""
import sys

# ---------------------------------------------------------------- pema e përgjithshme


def build_tree(start, successors, is_goal, max_depth, show):
    """Kthen pemën si listë rreshtash tekstuale. successors(s) -> [(veprimi, gjendja, e_ligjshme)]."""
    lines = [show(start)]
    seen = {start}
    stats = {"nodes": 1, "pruned": 0, "repeated": 0, "goals": 0}

    def expand(state, depth, prefix):
        if depth == max_depth or is_goal(state):
            return
        children = successors(state)
        for i, (action, child, legal) in enumerate(children):
            last = i == len(children) - 1
            branch = "└─ " if last else "├─ "
            if not legal:
                stats["pruned"] += 1
                lines.append(f"{prefix}{branch}{action} → {show(child)} ✗")
                continue
            if child in seen:
                stats["repeated"] += 1
                lines.append(f"{prefix}{branch}{action} → {show(child)} (përsëritje)")
                continue
            seen.add(child)
            stats["nodes"] += 1
            goal = is_goal(child)
            stats["goals"] += goal
            lines.append(f"{prefix}{branch}{action} → {show(child)}{' ✓ QËLLIMI' if goal else ''}")
            expand(child, depth + 1, prefix + ("   " if last else "│  "))

    expand(start, 0, "")
    return lines, stats


# ---------------------------------------------------------------- 8-Puzzle

PUZZLE_START = (1, 2, 3, 4, 0, 6, 7, 5, 8)
PUZZLE_GOAL = (1, 2, 3, 4, 5, 6, 7, 8, 0)
MOVES = {"Lart": -3, "Poshtë": 3, "Majtas": -1, "Djathtas": 1}


def puzzle_successors(s):
    i = s.index(0)
    out = []
    for name, d in MOVES.items():
        j = i + d
        if j < 0 or j > 8 or (d == -1 and i % 3 == 0) or (d == 1 and i % 3 == 2):
            continue  # lëvizje jashtë tabelës: operatori nuk aplikohet
        t = list(s)
        t[i], t[j] = t[j], t[i]
        out.append((name, tuple(t), True))
    return out


def puzzle_show(s):
    return " / ".join(" ".join(str(x) for x in s[r * 3:r * 3 + 3]) for r in range(3))


# ---------------------------------------------------------------- Missionaries and Cannibals

LOADS = [("2M", 2, 0), ("2C", 0, 2), ("1M1C", 1, 1), ("1M", 1, 0), ("1C", 0, 1)]


def mc_legal(m, c):
    left_ok = m == 0 or m >= c
    right_ok = (3 - m) == 0 or (3 - m) >= (3 - c)
    return 0 <= m <= 3 and 0 <= c <= 3 and left_ok and right_ok


def mc_successors(s):
    m, c, boat = s
    sign = -1 if boat == "L" else 1
    out = []
    for name, dm, dc in LOADS:
        nm, nc = m + sign * dm, c + sign * dc
        if not (0 <= nm <= 3 and 0 <= nc <= 3):
            continue  # nuk ka aq persona në breg
        child = (nm, nc, "R" if boat == "L" else "L")
        out.append((name, child, mc_legal(nm, nc)))
    return out


def mc_show(s):
    return f"({s[0]},{s[1]},{s[2]})"


# ---------------------------------------------------------------- Rotating Workforce Scheduling
# Instanca: 2 punëtorë, orar ciklik 2 javë × 7 ditë (14 slote), ndërrimet D (ditë), N (natë), - (pushim).
# Punëtori 1 fillon në slotin 0, punëtori 2 në slotin 7. Kërkesa: çdo ditë 1 D dhe 1 N
# vetëm nga e hëna te e premtja; fundjavë nuk punohet. N → D e ndaluar; blloqet e punës 2-5 ditë.
DAYS = 7
SLOTS = 2 * DAYS
DEMAND = {d: ({"D": 1, "N": 1} if d < 5 else {"D": 0, "N": 0}) for d in range(DAYS)}
SHIFTS = ["D", "N", "-"]


def rws_violation(schedule):
    """Arsyeja e krasitjes për orarin e pjesshëm, ose None."""
    k = len(schedule) - 1
    if k >= 1 and schedule[k - 1] == "N" and schedule[k] == "D":
        return "N→D"
    run = 0
    for x in reversed(schedule):
        if x == "-":
            break
        run += 1
    if run > 5:
        return "bllok > 5"
    if k >= 1 and schedule[k] == "-" and schedule[k - 1] != "-":
        start = k - 1
        while start > 0 and schedule[start - 1] != "-":
            start -= 1
        if start > 0 and (k - start) < 2:
            return "bllok < 2"
    if k >= DAYS:  # dita (k - 7) tani ka të dy punëtorët
        d = k - DAYS
        day = [schedule[d], schedule[k]]
        for shift, need in DEMAND[d].items():
            if day.count(shift) != need:
                return f"kërkesa e ditës {d + 1}"
    return None


def rws_successors(s):
    return [(x, s + (x,), rws_violation(s + (x,)) is None) for x in SHIFTS]


def rws_show(s):
    return "[" + " ".join(s) + "]" if s else "[ ]"


def rws_solve():
    """DFS me backtracking mbi të njëjtat degëzime: kthen orarin e plotë ciklik."""
    def dfs(s):
        if len(s) == SLOTS:
            wrap = s + s[:1]  # kontroll ciklik N→D në kalimin java 2 → java 1
            return s if not (wrap[-2] == "N" and wrap[-1] == "D") else None
        for _, child, legal in rws_successors(s):
            if legal:
                found = dfs(child)
                if found:
                    return found
        return None
    return dfs(())


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    which = sys.argv[1:] or ["puzzle", "mc", "rws"]
    if "puzzle" in which:
        lines, st = build_tree(PUZZLE_START, puzzle_successors, lambda s: s == PUZZLE_GOAL, 3, puzzle_show)
        print("== 8-Puzzle (thellësia 3)\n" + "\n".join(lines))
        print(f"nyje: {st['nodes']}, përsëritje: {st['repeated']}, qëllime: {st['goals']}\n")
    if "mc" in which:
        lines, st = build_tree((3, 3, "L"), mc_successors, lambda s: s == (0, 0, "R"), 11, mc_show)
        print("== Missionaries and Cannibals (deri te qëllimi)\n" + "\n".join(lines))
        print(f"nyje: {st['nodes']}, të krasitura (✗): {st['pruned']}, përsëritje: {st['repeated']}, qëllime: {st['goals']}\n")
    if "rws" in which:
        lines, st = build_tree((), rws_successors, lambda s: len(s) == SLOTS, 3, rws_show)
        print("== Rotating Workforce Scheduling (3 nivelet e para)\n" + "\n".join(lines))
        sol = rws_solve()
        print(f"nyje: {st['nodes']}, të krasitura (✗): {st['pruned']}")
        print("Orari i gjetur (punëtori 1 | punëtori 2):", " ".join(sol[:DAYS]), "|", " ".join(sol[DAYS:]))

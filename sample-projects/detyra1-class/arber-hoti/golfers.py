"""Social Golfers Problem: 32 lojtarë, 8 grupe me nga 4, sa më shumë javë.

Algoritmi: Depth First Search (rekursiv) me backtracking.
Përdorimi: python golfers.py [koha_maksimale_ne_sekonda]
"""
import sys
import time

PLAYERS, GROUPS, SIZE = 32, 8, 4


class Timeout(Exception):
    pass


def can_join(player, group, met):
    """A mund të hyjë lojtari në grup pa u takuar dy herë me dikë?"""
    return all(not met[player][other] for other in group)


def dfs(schedule, week, met, deadline, stats):
    """Plotëson javën `week` slot pas sloti; kthen True kur java plotësohet."""
    if time.time() > deadline:
        raise Timeout
    stats["nodes"] += 1
    groups = schedule[week]
    used = {p for g in groups for p in g}
    if len(used) == PLAYERS:
        return True
    # grupi i parë që nuk është plot
    gi = next(i for i, g in enumerate(groups) if len(g) < SIZE)
    group = groups[gi]
    candidates = [p for p in range(PLAYERS) if p not in used]
    if not group:
        # thyerja e simetrisë: grupi i ri fillon me lojtarin më të vogël të lirë
        candidates = candidates[:1]
    else:
        candidates = [p for p in candidates if p > group[-1]]
    for p in candidates:
        if can_join(p, group, met):
            group.append(p)
            for other in group[:-1]:
                met[p][other] = met[other][p] = True
            if dfs(schedule, week, met, deadline, stats):
                return True
            # backtracking: zhbëjmë vendosjen
            group.pop()
            for other in group:
                met[p][other] = met[other][p] = False
    return False


def solve(time_limit=20.0):
    met = [[False] * PLAYERS for _ in range(PLAYERS)]
    schedule = []
    stats = {"nodes": 0}
    deadline = time.time() + time_limit
    try:
        while len(schedule) < 10:  # kufiri i sipërm: floor(31 / 3) = 10
            schedule.append([[] for _ in range(GROUPS)])
            if not dfs(schedule, len(schedule) - 1, met, deadline, stats):
                schedule.pop()
                break
    except Timeout:
        schedule.pop()
    return schedule, stats["nodes"]


def check(schedule):
    """Kontroll i pavarur: çdo javë është ndarje e 0..31, asnjë çift nuk takohet dy herë."""
    seen = set()
    for week in schedule:
        players = sorted(p for g in week for p in g)
        assert players == list(range(PLAYERS)), "lojtarët nuk janë ndarje e plotë"
        for g in week:
            for i in range(len(g)):
                for j in range(i + 1, len(g)):
                    pair = (min(g[i], g[j]), max(g[i], g[j]))
                    assert pair not in seen, f"çifti {pair} takohet dy herë"
                    seen.add(pair)
    return True


if __name__ == "__main__":
    limit = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    schedule, nodes = solve(limit)
    for w, week in enumerate(schedule, start=1):
        print(f"Java {w}: " + " | ".join(",".join(map(str, g)) for g in week))
    print(f"Javë të planifikuara: {len(schedule)} (nyje të vizituara: {nodes}); kontrolli: {check(schedule)}")

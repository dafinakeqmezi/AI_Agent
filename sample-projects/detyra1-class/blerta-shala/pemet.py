"""Pemët e kërkimit."""
import sys


def nderto_pemen(start, pasardhesit, eshte_qellim, thellesia_max, shfaq):
    """Kthen pemën si listë rreshtash tekstuale. pasardhesit(s) -> [(veprimi, gjendja, e_ligjshme)]."""
    rreshtat = [shfaq(start)]
    pare = {start}
    stat = {"nodes": 1, "pruned": 0, "repeated": 0, "goals": 0}

    def zgjero(gjendja, thellesia, para):
        if thellesia == thellesia_max or eshte_qellim(gjendja):
            return
        femijet = pasardhesit(gjendja)
        for i, (veprimi, femija, ligjshme) in enumerate(femijet):
            fundit = i == len(femijet) - 1
            dega = "└─ " if fundit else "├─ "
            if not ligjshme:
                stat["pruned"] += 1
                rreshtat.append(f"{para}{dega}{veprimi} → {shfaq(femija)} ✗")
                continue
            if femija in pare:
                stat["repeated"] += 1
                rreshtat.append(f"{para}{dega}{veprimi} → {shfaq(femija)} (përsëritje)")
                continue
            pare.add(femija)
            stat["nodes"] += 1
            qellim = eshte_qellim(femija)
            stat["goals"] += qellim
            rreshtat.append(f"{para}{dega}{veprimi} → {shfaq(femija)}{' ✓ QËLLIMI' if qellim else ''}")
            zgjero(femija, thellesia + 1, para + ("   " if fundit else "│  "))

    zgjero(start, 0, "")
    return rreshtat, stat


FILLIMI = (1, 2, 3, 4, 0, 6, 7, 5, 8)
QELLIMI = (1, 2, 3, 4, 5, 6, 7, 8, 0)
LEVIZJET = {"Lart": -3, "Poshtë": 3, "Majtas": -1, "Djathtas": 1}


def pasardhesit_puzzle(s):
    i = s.index(0)
    out = []
    for name, d in LEVIZJET.items():
        j = i + d
        if j < 0 or j > 8 or (d == -1 and i % 3 == 0) or (d == 1 and i % 3 == 2):
            continue
        t = list(s)
        t[i], t[j] = t[j], t[i]
        out.append((name, tuple(t), True))
    return out


def shfaq_puzzle(s):
    return " / ".join(" ".join(str(x) for x in s[r * 3:r * 3 + 3]) for r in range(3))


NGARKESAT = [("2M", 2, 0), ("2C", 0, 2), ("1M1C", 1, 1), ("1M", 1, 0), ("1C", 0, 1)]


def mk_ligjshme(m, c):
    left_ok = m == 0 or m >= c
    right_ok = (3 - m) == 0 or (3 - m) >= (3 - c)
    return 0 <= m <= 3 and 0 <= c <= 3 and left_ok and right_ok


def pasardhesit_mk(s):
    m, c, barka = s
    shenja = -1 if barka == "L" else 1
    out = []
    for name, dm, dc in NGARKESAT:
        nm, nc = m + shenja * dm, c + shenja * dc
        if not (0 <= nm <= 3 and 0 <= nc <= 3):
            continue
        femija = (nm, nc, "R" if barka == "L" else "L")
        out.append((name, femija, mk_ligjshme(nm, nc)))
    return out


def shfaq_mk(s):
    return f"({s[0]},{s[1]},{s[2]})"


if __name__ == "__main__":
    cilat = sys.argv[1:] or ["puzzle", "mc"]
    if "puzzle" in cilat:
        rreshtat, st = nderto_pemen(FILLIMI, pasardhesit_puzzle, lambda s: s == QELLIMI, 3, shfaq_puzzle)
        print("== 8-Puzzle (thellësia 3)\n" + "\n".join(rreshtat))
        print(f"nyje: {st['nodes']}, përsëritje: {st['repeated']}, qëllime: {st['goals']}\n")
    if "mc" in cilat:
        rreshtat, st = nderto_pemen((3, 3, "L"), pasardhesit_mk, lambda s: s == (0, 0, "R"), 11, shfaq_mk)
        print("== Missionaries and Cannibals (deri te qëllimi)\n" + "\n".join(rreshtat))
        print(f"nyje: {st['nodes']}, të krasitura (✗): {st['pruned']}, përsëritje: {st['repeated']}, qëllime: {st['goals']}\n")

"""Katrori latin me IDDFS."""
import sys


def rreshtat_e_lejuar(rreshtat, n):
    """Gjeneron me backtracking çdo rresht që respekton kolonat e rreshtave ekzistues."""
    rreshti, perdorur = [], set()

    def zgjero(kolona):
        if kolona == n:
            yield list(rreshti)
            return
        for vlera in range(1, n + 1):
            if vlera not in perdorur and all(r[kolona] != vlera for r in rreshtat):
                rreshti.append(vlera)
                perdorur.add(vlera)
                yield from zgjero(kolona + 1)
                rreshti.pop()
                perdorur.discard(vlera)

    yield from zgjero(0)


def dfs_i_kufizuar(rreshtat, kufiri, n, stat):
    stat["nyje"] += 1
    if len(rreshtat) == n:
        return rreshtat
    if len(rreshtat) == kufiri:
        return None
    for rreshti in rreshtat_e_lejuar(rreshtat, n):
        gjetur = dfs_i_kufizuar(rreshtat + [rreshti], kufiri, n, stat)
        if gjetur:
            return gjetur
    return None


def kerkimi_iddfs(n):
    stat = {"nyje": 0, "iterime": 0}
    fillimi = [list(range(1, n + 1))]
    for kufiri in range(1, n + 1):
        stat["iterime"] += 1
        gjetur = dfs_i_kufizuar(fillimi, kufiri, n, stat)
        if gjetur:
            return gjetur, stat
    return None, stat


def objektivi(katrori):
    """Numri i simboleve të dyfishta në rreshta dhe kolona; zgjidhja ka f = 0."""
    n = len(katrori)
    rreshtat = sum(n - len(set(r)) for r in katrori)
    kolonat = sum(n - len({katrori[r][c] for r in range(n)}) for c in range(n))
    return rreshtat + kolonat


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    katrori, stat = kerkimi_iddfs(n)
    for rreshti in katrori:
        print(" ".join(map(str, rreshti)))
    print(f"n = {n}, iterime IDDFS: {stat['iterime']}, nyje: {stat['nyje']}, objektivi f = {objektivi(katrori)}")

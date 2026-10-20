"""Zgjidhja e Sudoku me kërkim në gjerësi (BFS)."""
import sys
import time
from collections import deque

TABELAT = {
    "easy": "530070000600195000098000060800060003400803001700020006060000280000419005000080079",
    "medium": "000260701680070090190004500820100040004602900050003028009300074040050036703018000",
    "hard": "000000907000420180000705026100904000050000040000507009920108000034059000507000000",
}


def lexo(teksti):
    return [[int(teksti[r * 9 + c]) for c in range(9)] for r in range(9)]


def vlerat_e_mundshme(tabela, rr, kk):
    perdorura = set(tabela[rr]) | {tabela[r][kk] for r in range(9)}
    kr, kc = 3 * (rr // 3), 3 * (kk // 3)
    perdorura |= {tabela[r][c] for r in range(kr, kr + 3) for c in range(kc, kc + 3)}
    return [v for v in range(1, 10) if v not in perdorura]


def zgjedh_qelizen(tabela):
    """Qeliza bosh me më pak kandidatë (renditje dinamike); None kur tabela është plot."""
    me_e_mira = None
    for r in range(9):
        for c in range(9):
            if tabela[r][c] == 0:
                kand = vlerat_e_mundshme(tabela, r, c)
                if me_e_mira is None or len(kand) < len(me_e_mira[2]):
                    me_e_mira = (r, c, kand)
    return me_e_mira


def zgjidh_bfs(fillimi):
    radha = deque([fillimi])
    zgjeruar = 0
    while radha:
        tabela = radha.popleft()
        zgjeruar += 1
        qeliza = zgjedh_qelizen(tabela)
        if qeliza is None:
            return tabela, zgjeruar
        rr, kk, vlerat = qeliza
        for vlera in vlerat:
            femija = [rresht[:] for rresht in tabela]
            femija[rr][kk] = vlera
            radha.append(femija)
    return None, zgjeruar


def funksioni_objektiv(tabela):
    """Numri i shkeljeve: dyfishime në rreshta, kolona dhe kuti. Zgjidhja ka f = 0."""
    f = 0
    njesite = [tabela[r] for r in range(9)] + [[tabela[r][c] for r in range(9)] for c in range(9)]
    njesite += [[tabela[r][c] for r in range(kr, kr + 3) for c in range(kc, kc + 3)] for kr in (0, 3, 6) for kc in (0, 3, 6)]
    for njesia in njesite:
        vlerat = [v for v in njesia if v]
        f += len(vlerat) - len(set(vlerat))
    return f


if __name__ == "__main__":
    nivelet = sys.argv[1:] or list(TABELAT)
    for niveli in nivelet:
        fillimi = lexo(TABELAT[niveli])
        bosh = sum(rr.count(0) for rr in fillimi)
        fillimi_kohes = time.time()
        zgjidhja, zgjeruar = zgjidh_bfs(fillimi)
        print(f"[{niveli}] qeliza bosh: {bosh}, landscape 9^{bosh} = {9 ** bosh:.2e}, nyje: {zgjeruar}, koha: {time.time() - fillimi_kohes:.2f}s")
        for rr in zgjidhja:
            print(" ".join(map(str, rr)))
        print(f"funksioni_objektiv f = {funksioni_objektiv(zgjidhja)}")

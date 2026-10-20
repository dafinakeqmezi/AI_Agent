"""Problemi i golferëve: kërkim në thellësi (DFS) me kthim prapa."""
import sys
import time

NR_LOJTAREVE, NR_GRUPEVE, MADHESIA = 32, 8, 4


class KohaMbaroi(Exception):
    pass


def mund_te_hyje(lojtari, grupi, takuar):
    """A mund të hyjë lojtari në grup pa u takuar dy herë me dikë?"""
    return all(not takuar[lojtari][tjetri] for tjetri in grupi)


def kerko_dfs(orari, java, takuar, afati, statistika):
    """Plotëson javën `java` slot pas sloti; kthen True kur java plotësohet."""
    if time.time() > afati:
        raise KohaMbaroi
    statistika["nyjet"] += 1
    grupet = orari[java]
    te_perdorur = {p for g in grupet for p in g}
    if len(te_perdorur) == NR_LOJTAREVE:
        return True
    idx = next(i for i, g in enumerate(grupet) if len(g) < MADHESIA)
    grupi = grupet[idx]
    kandidatet = [p for p in range(NR_LOJTAREVE) if p not in te_perdorur]
    if not grupi:
        kandidatet = kandidatet[:1]
    else:
        kandidatet = [p for p in kandidatet if p > grupi[-1]]
    for p in kandidatet:
        if mund_te_hyje(p, grupi, takuar):
            grupi.append(p)
            for tjetri in grupi[:-1]:
                takuar[p][tjetri] = takuar[tjetri][p] = True
            if kerko_dfs(orari, java, takuar, afati, statistika):
                return True
            grupi.pop()
            for tjetri in grupi:
                takuar[p][tjetri] = takuar[tjetri][p] = False
    return False


def zgjidh(limiti=20.0):
    takuar = [[False] * NR_LOJTAREVE for _ in range(NR_LOJTAREVE)]
    orari = []
    statistika = {"nyjet": 0}
    afati = time.time() + limiti
    try:
        while len(orari) < 10:
            orari.append([[] for _ in range(NR_GRUPEVE)])
            if not kerko_dfs(orari, len(orari) - 1, takuar, afati, statistika):
                orari.pop()
                break
    except KohaMbaroi:
        orari.pop()
    return orari, statistika["nyjet"]


def verifiko(orari):
    """Kontroll i pavarur: çdo javë është ndarje e 0..31, asnjë çift nuk takohet dy herë."""
    pare = set()
    for java in orari:
        lojtaret = sorted(p for g in java for p in g)
        assert lojtaret == list(range(NR_LOJTAREVE)), "lojtarët nuk janë ndarje e plotë"
        for g in java:
            for i in range(len(g)):
                for j in range(i + 1, len(g)):
                    cifti = (min(g[i], g[j]), max(g[i], g[j]))
                    assert cifti not in pare, f"çifti {cifti} takohet dy herë"
                    pare.add(cifti)
    return True


if __name__ == "__main__":
    kufiri = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    orari, nyjet = zgjidh(kufiri)
    for w, java in enumerate(orari, start=1):
        print(f"Java {w}: " + " | ".join(",".join(map(str, g)) for g in java))
    print(f"Javë të planifikuara: {len(orari)} (nyje të vizituara: {nyjet}); kontrolli: {verifiko(orari)}")

# Detyra e parë – Kërkimi i painformuar

Studentja: Blerta Shala

Programet: `golf_dfs.py`, `sudoku_bfs.py`, `katrori_latin.py`, `pemet.py` (pemët e kërkimit).

## 1. Problemi i golferëve (Social Golfers)

**Modelimi.** Kemi n = g × p = 8 × 4 = 32 lojtarë. Çdo javë çdo lojtar luan saktësisht një herë, në saktësisht një grup me 4 lojtarë. Dy lojtarë nuk guxojnë të jenë në të njëjtin grup më shumë se një herë gjatë gjithë javëve. Pyetja: sa javë w mund të planifikohen? Çdo lojtar takon 3 lojtarë në javë dhe ka 31 lojtarë të tjerë, prandaj w ≤ ⌊31/3⌋ = 10.

**Reprezentimi.** Orari ruhet si listë javësh, çdo javë si listë grupesh me lojtarë 0-31. Kufizimet janë që lojtari të jetë një herë në javë dhe që çiftet të mos përsëriten.

**Funksioni objektiv.** f(S) = Σ_{i<j} max(0, takime(i, j) − 1), numri i takimeve të përsëritura. Zgjidhje e vlefshme ka f = 0; qëllimi është w maksimal me f = 0.

**Landscape.** Një javë = ndarje e 32 lojtarëve në 8 grupe të paetiketuara me nga 4:
32! / ((4!)^8 · 8!) = 59 287 247 761 257 140 625 ≈ 5.93 · 10^19.

**Rezultati:** 5 javë me DFS.

## 2. Sudoku

Tabela 9×9, duhet të plotësohen qelizat bosh me numra 1-9 pa përsëritje në rresht, kolonë dhe kuti. Variablat janë qelizat bosh, domeni {1..9}. Funksioni objektiv numëron përsëritjet (0 = zgjidhje). Landscape: 9^k ku k është numri i qelizave bosh.

Algoritmi BFS përdor radhë (deque) dhe nuk fut në radhë tabela të pavlefshme. Nivelet: easy, medium, hard (të gjitha zgjidhen).

## 3. Katrori latin

Matrica n×n ku çdo numër 1..n del një herë në çdo rresht e kolonë. Kërkimi IDDFS shton nga një rresht në çdo nivel. Funksioni objektiv: numri i përsëritjeve. Landscape: (n!)^n.

## 4. Pemët e kërkimit

### 8-Puzzle

```
            1 2 3
            4 0 6     (fillimi)
            7 5 8
     ┌────────┬───┴────┬────────┐
     L        P        M        D
   1 0 3    1 2 3    1 2 3    1 2 3
   4 2 6    4 5 6    0 4 6    4 6 0
   7 5 8    7 0 8    7 5 8    7 5 8
```

### Misionarët dhe kanibalët

Gjendja (M, C, B). Fillimi (3,3,L), qëllimi (0,0,R).

```
(3,3,L) → 2C → (3,1,R) → 1C → (3,2,L) → 2C → (3,0,R) → …
```

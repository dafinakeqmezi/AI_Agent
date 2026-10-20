# Detyra 1: Teknikat e painformuara të kërkimit

Arbër Hoti · Inteligjenca Artificiale 2026/27

Ekzekutimi (Python 3.10+, pa librari të jashtme):

```
python golfers.py 20        # Social Golfers, DFS me backtracking, kufiri i kohës 20 s
python sudoku.py            # Sudoku, BFS me backtracking, nivelet easy / medium / hard
python sudoku.py hard       # vetëm një nivel
python latin.py 5           # Latin Square, IDDFS me backtracking
python search_trees.py      # Search trees: 8-Puzzle, Missionaries & Cannibals, Rotating Workforce
```

Çdo program e kontrollon vetë zgjidhjen (funksioni `check` / `objective` duhet të japë 0 shkelje).

---

## 1. Social Golfers Problem

**Modelimi.** Kemi n = g × p = 8 × 4 = 32 lojtarë. Çdo javë çdo lojtar luan saktësisht një herë, në saktësisht një grup me 4 lojtarë. Dy lojtarë nuk guxojnë të jenë në të njëjtin grup më shumë se një herë gjatë gjithë javëve. Pyetja: sa javë w mund të planifikohen? Çdo lojtar takon 3 lojtarë në javë dhe ka 31 lojtarë të tjerë, prandaj w ≤ ⌊31/3⌋ = 10.

**Reprezentimi.** Variablat: `schedule[w][g][k]`, lojtari në vendin k (0..3) të grupit g (0..7) në javën w. Domeni: {0, …, 31}. Kufizimet (hard):
1. në çdo javë secili lojtar paraqitet saktësisht një herë;
2. çdo çift lojtarësh takohet më së shumti një herë (matrica `met[i][j]`).

Thyerja e simetrisë: brenda grupit lojtarët janë në rend rritës, dhe çdo grup i ri fillon me lojtarin më të vogël të lirë (grupet dhe renditja brenda grupit nuk kanë rëndësi).

**Objective function.** f(S) = Σ_{i<j} max(0, takime(i, j) − 1), numri i takimeve të përsëritura. Zgjidhje e vlefshme ka f = 0; qëllimi është w maksimal me f = 0.

**Landscape.** Një javë = ndarje e 32 lojtarëve në 8 grupe të paetiketuara me nga 4:
32! / ((4!)^8 · 8!) = 59 287 247 761 257 140 625 ≈ 5.93 · 10^19.
Për w javë: (5.93 · 10^19)^w, p.sh. për 10 javë ≈ 5.4 · 10^197.

**Algoritmi.** `golfers.py`: DFS rekursiv. Java plotësohet slot pas sloti; lojtari vendoset vetëm nëse nuk është takuar me asnjë anëtar të grupit (kontrolli para zbritjes në pemë), përndryshe bëhet backtracking (hiqet nga grupi dhe zhbëhen takimet).

**Rezultati.** Brenda 20 sekondave DFS planifikon **5 javë** (183 nyje), të verifikuara nga `check()`. Java e 6-të nuk gjendet me këtë qasje javë-pas-jave, sepse javët e mëparshme nuk rishikohen. Kufiri teorik është 10 javë.

---

## 2. Sudoku Solver

**Modelimi.** Jepet një tabelë 9×9 e plotësuar pjesërisht. Duhet të plotësohen qelizat bosh me 1..9 ashtu që çdo rresht, kolonë dhe kuti 3×3 të përmbajë çdo shifër saktësisht një herë. Vlerat e dhëna nuk ndryshohen.

**Reprezentimi.** Variablat: qelizat bosh x_{r,c}. Domeni: {1, …, 9}. Kufizimet: all-different në 9 rreshta, 9 kolona, 9 kuti.

**Objective function.** f = numri i dyfishimeve në rreshta + kolona + kuti (`objective()` në kod). Zgjidhja ka f = 0.

**Landscape.** Për një puzzle me k qeliza bosh: 9^k. Easy: k = 51 → 9^51 ≈ 4.64 · 10^48; Medium: k = 45 → 8.73 · 10^42; Hard: k = 53 → 3.76 · 10^50. (Tabela e zbrazët: 9^81 ≈ 1.97 · 10^77.)

**Algoritmi.** `sudoku.py`: BFS me radhë FIFO (`deque.popleft`). Çdo nivel plotëson një qelizë më shumë; zgjidhet qeliza me më pak kandidatë. Backtracking/pruning: fëmija krijohet vetëm me vlera që nuk shkelin kufizimet, gjendjet e pavlefshme nuk futen në radhë.

**Tri nivelet.**

| Niveli | Qeliza bosh | Nyje të zgjeruara | Koha |
|---|---|---|---|
| Easy | 51 | 52 | < 0.01 s |
| Medium | 45 | 46 | < 0.01 s |
| Hard | 53 | 162 | 0.01 s |

---

## 3. Latin Square

**Modelimi.** Për n të dhënë, ndërtojmë matricë n×n me numrat 1..n, ku secili paraqitet saktësisht një herë në çdo rresht dhe në çdo kolonë.

**Reprezentimi.** Variablat: x_{i,j}, domeni {1..n}; kufizimet all-different në rreshta dhe kolona. Në kërkim, një nivel i pemës = një rresht i plotë (permutacion i 1..n që respekton kolonat). Rreshti i parë fiksohet 1..n (thyerje simetrie).

**Objective function.** f = numri i simboleve të dyfishta në rreshta + kolona. Zgjidhja ka f = 0.

**Landscape.** Me qeliza: n^(n²), për n = 5: 5^25 ≈ 2.98 · 10^17. Me rreshta si permutacione: (n!)^n = 120^5 ≈ 2.49 · 10^10; me rreshtin e parë të fiksuar: (n!)^(n−1) = 120^4 ≈ 2.07 · 10^8.

**Algoritmi.** `latin.py`: IDDFS. Kufiri i thellësisë rritet 1, 2, …, n; në çdo iterim bëhet DFS i kufizuar. Rreshtat gjenerohen qelizë pas qelize me backtracking (vendoset vetëm vlerë që nuk është në rresht e kolonë, pastaj zhbëhet).

**Rezultati.** n = 5: zgjidhje pas 5 iterimeve, 2 589 nyje, f = 0. Kufizim: meqë zgjidhjet janë vetëm në thellësinë n, iterimet e mëparshme përsërisin punë; për n ≥ 6 koha rritet shumë.

---

## 4. Search Trees

Pemët më poshtë gjenerohen nga programi `search_trees.py` (zgjerim nivel pas niveli; ✗ = gjendje e paligjshme e krasitur, (përsëritje) = gjendje e vizituar më parë). Ekzekuto `python search_trees.py mc` për pemën e plotë deri te qëllimi.

### 8-Puzzle
Gjendja: tabela 3×3 (0 = vendi bosh). Operatorët: lëvizja e vendit bosh Lart / Poshtë / Majtas / Djathtas (2-4 fëmijë). Gjendje të arritshme: 9!/2 = 181 440.

```
            1 2 3
            4 0 6     (fillimi)
            7 5 8
     ┌────────┬───┴────┬────────┐
     L        P        M        D
   1 0 3    1 2 3    1 2 3    1 2 3
   4 2 6    4 5 6    0 4 6    4 6 0
   7 5 8    7 0 8    7 5 8    7 5 8
              │
         ┌────┼────┐
         M    D    L (= fillimi, përsëritje, krasitet)
       1 2 3  1 2 3
       4 5 6  4 5 6
       0 7 8  7 8 0   ← qëllimi
```

### Missionaries and Cannibals
Gjendja (M, C, B): misionarët dhe kanibalët në bregun e majtë, B = anija (L/R). Fillimi (3,3,L), qëllimi (0,0,R). Veprimet: 1M, 2M, 1C, 2C, 1M1C. Krasiten gjendjet ku kanibalët janë më shumë se misionarët në një breg me misionarë, dhe gjendjet e përsëritura.

```
(3,3,L)
 ├─ 2C → (3,1,R)
 │        └─ 1C ← (3,2,L)
 │                 └─ 2C → (3,0,R)
 │                          └─ 1C ← (3,1,L)
 │                                   └─ 2M → (1,1,R)
 │                                            └─ 1M1C ← (2,2,L)
 │                                                     └─ 2M → (0,2,R)
 │                                                              └─ 1C ← (0,3,L)
 │                                                                       └─ 2C → (0,1,R)
 │                                                                                └─ 1C ← (0,2,L)
 │                                                                                         └─ 2C → (0,0,R) ✓
 ├─ 1M1C → (2,2,R)
 │          └─ 1M ← (3,2,L) (e njëjtë si më lart)
 ├─ 1C → (3,2,R)
 │        └─ 1C ← (3,3,L) (përsëritje, krasitet)
 ├─ 2M → (1,3,R) ✗ (1 misionar me 3 kanibalë, krasitet)
 └─ 1M → (2,3,R) ✗ (krasitet)
```
Zgjidhja më e shkurtër: 11 kalime.

### Rotating Workforce Scheduling
Instanca e vogël: 2 punëtorë, cikël 2 javë × 7 ditë, ndërrime D (ditë), N (natë), – (pushim). Kërkesat: çdo ditë 1 D; pas N nuk lejohet D; blloqet e punës 2-5 ditë.

Nyja = orar ciklik i plotësuar pjesërisht (slot pas sloti: java 1 dita 1, dita 2, …). Degëzimi: {D, N, –} për slotin e radhës. Krasitja: (a) N pas të cilit vjen D; (b) blloku i punës > 5 ose < 2 ditë; (c) dita nuk mund ta arrijë kërkesën.

```
[ ]
 ├─ D → [D]
 │       ├─ D → [D D]
 │       │       ├─ D → [D D D] …
 │       │       ├─ N → [D D N]
 │       │       │       └─ D → [D D N D] ✗ (N → D e ndaluar)
 │       │       └─ – → [D D –] …
 │       ├─ N → [D N] …
 │       └─ – → [D –] ✗ (blloku i punës 1 ditë < 2)
 ├─ N → [N]
 │       └─ D → [N D] ✗
 └─ – → [–] …
```

---

Literatura: Russell & Norvig, *AIMA*, kap. 3; Michalewicz & Fogel, *How to Solve It: Modern Heuristics*, kap. 1-3; Musliu, Gärtner & Slany (2002), *Efficient generation of rotating workforce schedules*, Discrete Applied Mathematics 118(1-2), doi:10.1016/S0166-218X(01)00258-X.

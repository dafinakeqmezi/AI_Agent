# Detyra 1 - AI

Driton Morina

Ekzekutimi: `python detyra1.py` (ose `golf`, `sudoku`, `latin`).

## Social Golfers

32 lojtarë, 8 grupe me 4 lojtarë. Çdo javë të gjithë luajnë, dhe dy lojtarë nuk duhet të luajnë bashkë dy herë. Variablat janë grupet e çdo jave, domeni janë lojtarët 0-31. Kufizimi: çifti (a, b) nuk përsëritet.

Objective function: numri i çifteve që përsëriten, duhet të jetë 0.

Algoritmi është DFS: për çdo javë marrim lojtarin e parë të lirë dhe provojmë treshet e tjera, nëse nuk ka zgjidhje kthehemi mbrapa. Programi gjen 5 javë.

## Sudoku

Tabela 9x9 me numra 1-9, pa përsëritje në rresht, kolonë dhe kuti 3x3. Variablat janë qelizat bosh, domeni 1-9.

Landscape: 9^81.

Algoritmi BFS me backtracking (funksioni `bfs`).

## Latin Square

Matricë n x n ku çdo numër shfaqet një herë në rresht dhe kolonë. Përdoret IDDFS (funksioni `iddfs_latin`).

## Search tree 8-Puzzle

```
1 2 3
4 0 6
7 5 8
 |- lart:    1 0 3 / 4 2 6 / 7 5 8
 |- poshte:  1 2 3 / 4 5 6 / 7 0 8
 |- majtas:  1 2 3 / 0 4 6 / 7 5 8
 |- djathtas:1 2 3 / 4 6 0 / 7 5 8
```

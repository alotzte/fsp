"""Компетенция «Алгоритмы и структуры данных». Ответы вычисляются кодом."""

import heapq
import itertools
import math
from collections import deque
from random import Random

from app.services.assessment.bank.base import Item, choice, family, text

COMPETENCY = "algorithms"
_COMPLEXITIES = ["O(log n)", "O(n)", "O(n log n)", "O(n²)"]


@family("algo.complexity", competency=COMPETENCY, a=1.2, b=-0.9)
def _complexity(rng: Random) -> Item:
    var = rng.choice(["i", "k", "idx"])
    snippets = {
        "O(n)": f"total = 0\nfor {var} in range(n):\n    total += a[{var}]",
        "O(n²)": (
            f"pairs = 0\nfor {var} in range(n):\n    for j in range({var} + 1, n):\n"
            f"        if a[{var}] == a[j]:\n            pairs += 1"
        ),
        "O(log n)": "steps = 0\nwhile n > 1:\n    n //= 2\n    steps += 1",
        "O(n log n)": f"for {var} in range(n):\n    m = n\n    while m > 1:\n        m //= 2",
    }
    correct = rng.choice(list(snippets))
    return choice(
        rng,
        "Какова асимптотическая сложность фрагмента по времени?",
        correct,
        [c for c in _COMPLEXITIES if c != correct],
        code=snippets[correct],
    )


@family("algo.binary_search", competency=COMPETENCY, a=1.3, b=-0.2)
def _binary_search(rng: Random) -> Item:
    n = rng.choice([100, 500, 1000, 5000, 10_000, 100_000, 1_000_000])
    answer = math.floor(math.log2(n)) + 1
    return text(
        f"Отсортированный массив из {n} элементов. Какое наибольшее число сравнений с искомым "
        "значением может понадобиться бинарному поиску (каждый шаг: одно сравнение)?",
        answer,
    )


@family("algo.stack", competency=COMPETENCY, a=1.2, b=0.2)
def _stack(rng: Random) -> Item:
    structure = rng.choice(["стек", "очередь"])
    put, take = ("push", "pop") if structure == "стек" else ("enqueue", "dequeue")
    items: deque[int] = deque()
    taken: list[int] = []
    ops: list[str] = []
    for value in range(1, rng.randint(7, 10)):
        if items and rng.random() < 0.4:
            taken.append(items.pop() if structure == "стек" else items.popleft())
            ops.append(f"{take}()")
        else:
            items.append(value)
            ops.append(f"{put}({value})")
    if not taken:
        taken.append(items.pop() if structure == "стек" else items.popleft())
        ops.append(f"{take}()")
    return text(
        f"Над пустой структурой «{structure}» выполнены операции. Перечислите извлечённые "
        "значения по порядку через пробел.",
        " ".join(map(str, taken)),
        code="\n".join(ops),
    )


def _bfs(n: int, edges: list[tuple[int, int]], start: int, goal: int) -> int:
    graph: dict[int, list[int]] = {v: [] for v in range(1, n + 1)}
    for u, v in edges:
        graph[u].append(v)
        graph[v].append(u)
    dist = {start: 0}
    queue = deque([start])
    while queue:
        u = queue.popleft()
        for v in graph[u]:
            if v not in dist:
                dist[v] = dist[u] + 1
                queue.append(v)
    return dist.get(goal, -1)


@family("algo.bfs", competency=COMPETENCY, a=1.4, b=0.8)
def _bfs_family(rng: Random) -> Item:
    n = rng.randint(7, 9)
    # Остов-цепочка гарантирует связность, лишние рёбра создают короткие пути.
    order = list(range(1, n + 1))
    rng.shuffle(order)
    edges = {tuple(sorted(pair)) for pair in itertools.pairwise(order)}
    while len(edges) < n + 2:
        u, v = rng.sample(range(1, n + 1), 2)
        edges.add(tuple(sorted((u, v))))
    edge_list = sorted((int(u), int(v)) for u, v in edges)
    start, goal = order[0], order[-1]
    answer = _bfs(n, edge_list, start, goal)
    return text(
        f"Неориентированный граф задан списком рёбер. Какова длина кратчайшего пути (в рёбрах) "
        f"от вершины {start} до вершины {goal}?",
        answer,
        code="\n".join(f"{u} - {v}" for u, v in edge_list),
    )


def _min_coins(coins: list[int], amount: int) -> int:
    best = [0] + [math.inf] * amount
    for value in range(1, amount + 1):
        for coin in coins:
            if coin <= value and best[value - coin] + 1 < best[value]:
                best[value] = best[value - coin] + 1
    return int(best[amount])


def _greedy_coins(coins: list[int], amount: int) -> int:
    count = 0
    for coin in sorted(coins, reverse=True):
        count += amount // coin
        amount %= coin
    return count if amount == 0 else -1


@family("algo.coins_dp", competency=COMPETENCY, a=1.5, b=1.6)
def _coins_dp(rng: Random) -> Item:
    # Подбираем набор, где жадный алгоритм ошибается: проверяет понимание, а не заучивание.
    while True:
        coins = sorted(rng.sample([1, 3, 4, 5, 6, 7, 9, 10], 3))
        if 1 not in coins:
            coins = [1, *coins[1:]]
        amount = rng.randint(12, 30)
        optimal = _min_coins(coins, amount)
        if _greedy_coins(coins, amount) != optimal:
            break
    return text(
        f"Монеты номиналов {', '.join(map(str, coins))} (каждого номинала сколько угодно). "
        f"Какое минимальное число монет даёт сумму {amount}?",
        optimal,
    )


_AMORTIZED = {
    "O(1) амортизированно": "при переполнении увеличивает ёмкость в 2 раза; выполняют n добавлений",
    "O(n) амортизированно": (
        "при переполнении увеличивает ёмкость на 16 элементов; выполняют n добавлений"
    ),
    "O(n) на операцию в худшем случае": (
        "удваивается при переполнении и сразу уменьшается вдвое, как только заполнен меньше "
        "чем наполовину; на границе чередуют добавление и удаление"
    ),
}


@family("algo.amortized", competency=COMPETENCY, a=1.3, b=2.0)
def _amortized(rng: Random) -> Item:
    correct = rng.choice(list(_AMORTIZED))
    return choice(
        rng,
        f"Динамический массив копирует элементы в новый буфер, когда меняет ёмкость. Он "
        f"{_AMORTIZED[correct]}. Какова стоимость операции?",
        correct,
        [*[c for c in _AMORTIZED if c != correct], "O(log n) амортизированно"],
    )


def _shortest(
    n: int, edges: list[tuple[int, int, int]], start: int, *, by_hops: bool
) -> dict[int, tuple[int, int]]:
    """Дейкстра по паре (число рёбер, вес) до каждой вершины. by_hops: сначала меньше рёбер,
    потом меньший вес (так рассуждает тот, кто ищет путь как BFS); иначе сначала меньший вес."""

    def key(cost: tuple[int, int]) -> tuple[int, int]:
        return cost if by_hops else (cost[1], cost[0])

    graph: dict[int, list[tuple[int, int]]] = {v: [] for v in range(1, n + 1)}
    for u, v, w in edges:
        graph[u].append((v, w))
        graph[v].append((u, w))
    best = {start: (0, 0)}
    heap = [(key((0, 0)), start)]
    while heap:
        cost, u = heapq.heappop(heap)
        if cost != key(best[u]):
            continue
        hops, weight = best[u]
        for v, w in graph[u]:
            candidate = (hops + 1, weight + w)
            if v not in best or key(candidate) < key(best[v]):
                best[v] = candidate
                heapq.heappush(heap, (key(candidate), v))
    return best


@family("algo.dijkstra", competency=COMPETENCY, a=1.4, b=1.9)
def _dijkstra(rng: Random) -> Item:
    while True:
        n = rng.randint(6, 7)
        order = list(range(1, n + 1))
        rng.shuffle(order)
        weights = {
            tuple(sorted(pair)): rng.randint(1, 9) for pair in itertools.pairwise(order)
        }
        while len(weights) < n + 3:
            u, v = sorted(rng.sample(range(1, n + 1), 2))
            weights.setdefault((u, v), rng.randint(1, 9))
        edges = sorted((u, v, w) for (u, v), w in weights.items())
        start, goal = order[0], order[-1]
        lightest = _shortest(n, edges, start, by_hops=False)[goal][1]
        # Путь с наименьшим числом рёбер тяжелее: задача проверяет Дейкстру, а не BFS.
        if _shortest(n, edges, start, by_hops=True)[goal][1] > lightest:
            break
    return text(
        f"Неориентированный граф с весами рёбер. Какова длина кратчайшего пути (сумма весов) "
        f"от вершины {start} до вершины {goal}?",
        lightest,
        code="\n".join(f"{u} - {v}: {w}" for u, v, w in edges),
    )


_GOODS = ["ноутбук", "камера", "дрон", "планшет", "колонка", "часы"]


@family("algo.knapsack", competency=COMPETENCY, a=1.4, b=2.3)
def _knapsack(rng: Random) -> Item:
    while True:
        names = rng.sample(_GOODS, 5)
        goods = [(name, rng.randint(2, 9), rng.randrange(10, 100, 5)) for name in names]
        capacity = rng.randint(10, 16)
        best = max(
            sum(value for _, _, value in subset)
            for size in range(len(goods) + 1)
            for subset in itertools.combinations(goods, size)
            if sum(weight for _, weight, _ in subset) <= capacity
        )
        # Жадный выбор по ценности на килограмм ошибается: нужен перебор или ДП.
        greedy, room = 0, capacity
        for _, weight, value in sorted(goods, key=lambda g: g[2] / g[1], reverse=True):
            if weight <= room:
                greedy, room = greedy + value, room - weight
        if greedy < best:
            break
    return text(
        f"В рюкзак помещается не больше {capacity} кг. Каждый предмет можно взять целиком "
        "или не брать. Какую наибольшую суммарную ценность можно унести?",
        best,
        code="\n".join(
            f"{name}: {weight} кг, ценность {value}" for name, weight, value in goods
        ),
    )

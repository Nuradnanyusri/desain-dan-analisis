from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Gerak 4 arah (atas, kanan, bawah, kiri)
DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]


def in_bounds(r, c, rows, cols):
    return 0 <= r < rows and 0 <= c < cols


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def backtracking_collect_paths(grid_walkable, start, goal, cap=1500, max_depth=None):
    """
    Kumpulkan banyak jalur sederhana (tanpa mengulang sel dalam 1 jalur),
    lalu nanti diranking di luar.
    grid_walkable: 2D list, 0=jalan, 1=tembok (blocked)
    cap: batas jumlah path yang dikumpul (biar aman performa)
    """
    rows, cols = len(grid_walkable), len(grid_walkable[0])
    sr, sc = start
    gr, gc = goal

    if not in_bounds(sr, sc, rows, cols) or not in_bounds(gr, gc, rows, cols):
        return []
    if grid_walkable[sr][sc] == 1 or grid_walkable[gr][gc] == 1:
        return []

    if max_depth is None:
        max_depth = rows * cols * 2

    visited = [[False] * cols for _ in range(rows)]
    path = []
    paths = []

    def dfs(r, c, depth):
        nonlocal paths
        if len(paths) >= cap:
            return
        if depth > max_depth:
            return

        visited[r][c] = True
        path.append([r, c])

        if r == gr and c == gc:
            paths.append(path.copy())
        else:
            for dr, dc in DIRS:
                nr, nc = r + dr, c + dc
                if in_bounds(nr, nc, rows, cols) and not visited[nr][nc] and grid_walkable[nr][nc] == 0:
                    dfs(nr, nc, depth + 1)

        path.pop()
        visited[r][c] = False

    dfs(sr, sc, 0)
    return paths


def risk_score_for_path(path, hazards, radius=2):
    """
    Risk dihitung dari kedekatan tiap langkah ke titik bahaya.
    - d = jarak Manhattan terdekat ke hazard
    - kalau d <= radius, kontribusi risiko = (radius - d + 1)/(radius + 1)
    """
    if not hazards or radius <= 0:
        return 0.0

    rsum = 0.0
    R = radius
    denom = (R + 1)

    for (r, c) in path:
        best = None
        for hz in hazards:
            d = abs(r - hz[0]) + abs(c - hz[1])
            if best is None or d < best:
                best = d
                if best == 0:
                    break
        if best is not None and best <= R:
            rsum += (R - best + 1) / denom

    return float(rsum)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/solve", methods=["POST"])
def solve():
    data = request.get_json(force=True)

    grid = data.get("grid")          # 0 empty, 1 wall, 2 hazard
    start = data.get("start")
    goal = data.get("goal")

    k = int(data.get("k", 10))
    cap = int(data.get("cap", 1500))               # jumlah path kandidat dikumpul
    max_depth = data.get("max_depth", None)
    max_depth = int(max_depth) if max_depth is not None else None

    radius = int(data.get("radius", 2))            # radius risiko
    risk_weight = float(data.get("risk_weight", 8))# bobot risiko
    strict_hazard = bool(data.get("strict_hazard", False))  # kalau True, hazard dianggap tembok

    if not grid or not start or not goal:
        return jsonify({"ok": False, "error": "Input tidak lengkap"}), 400

    # Validasi & normalisasi grid
    try:
        rows = len(grid)
        cols = len(grid[0])
        norm = [[0] * cols for _ in range(rows)]
        hazards = []
        walls = 0
        for r in range(rows):
            for c in range(cols):
                v = int(grid[r][c])
                if v == 1:
                    norm[r][c] = 1
                    walls += 1
                elif v == 2:
                    norm[r][c] = 2
                    hazards.append([r, c])
                else:
                    norm[r][c] = 0
    except Exception:
        return jsonify({"ok": False, "error": "Format grid invalid"}), 400

    # grid untuk pathfinding (walkable / blocked)
    # - wall always blocked
    # - hazard: blocked kalau strict_hazard=True, kalau tidak, tetap bisa dilewati tapi dihukum di scoring
    grid_walkable = [[0] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if norm[r][c] == 1:
                grid_walkable[r][c] = 1
            elif norm[r][c] == 2 and strict_hazard:
                grid_walkable[r][c] = 1
            else:
                grid_walkable[r][c] = 0

    # Collect candidate paths via backtracking
    candidates = backtracking_collect_paths(
        grid_walkable=grid_walkable,
        start=start,
        goal=goal,
        cap=cap,
        max_depth=max_depth
    )

    # Rank with AI scoring
    scored = []
    for p in candidates:
        steps = len(p)
        rsum = risk_score_for_path(p, hazards, radius=radius)
        score = float(steps) + (risk_weight * rsum)
        scored.append({
            "path": p,
            "steps": steps,
            "risk_sum": rsum,
            "score": score
        })

    scored.sort(key=lambda x: (x["score"], x["steps"]))  # score kecil = lebih aman

    top = scored[:k]

    return jsonify({
        "ok": True,
        "requested": k,
        "found_candidates": len(candidates),
        "returned": len(top),
        "params": {
            "radius": radius,
            "risk_weight": risk_weight,
            "strict_hazard": strict_hazard,
            "cap": cap,
            "max_depth": max_depth
        },
        "stats": {
            "rows": rows,
            "cols": cols,
            "walls": walls,
            "hazards": len(hazards)
        },
        "solutions": top
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

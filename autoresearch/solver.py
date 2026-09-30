"""solver：用半透明三角形逐个贪心拟合目标图，输出满足字节预算的 SVG。

算法同 ../fit.py（primitive 式：随机候选 + 爬山，颜色最小二乘；阶段 1 半分辨率全局铺大形，
阶段 2 分轮切块并行、相邻轮错开半块），内核用 C 实现（core.c），块之间用线程并行。

用法: python3 solver.py target.png outdir --time 60 --budgets 16000,160000 --seed 0
"""
import argparse
import ctypes
import gzip
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
A = 0.5
LW = 8.0  # 亮度误差的额外权重（评分用的 SSIM 只看亮度）
GEOM_PASSES = 2  # 几何回拟合扫几遍
PRUNE_TAU = 0.8  # 删除代价低于"最后一轮形状平均收益 × PRUNE_TAU"的形状删掉，用省下的字节补新形状
FP, DP, IP = ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int)


class Img(ctypes.Structure):
    _fields_ = [("W", ctypes.c_int), ("H", ctypes.c_int), ("T", FP), ("C", FP), ("E", FP)]


def load_core():
    src, so = os.path.join(HERE, "core.c"), os.path.join(HERE, "core.so")
    if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
        subprocess.run(["cc", "-O3", "-shared", "-fPIC", "-o", so, src], check=True)
    L = ctypes.CDLL(so)
    L.eval_tri.restype = ctypes.c_double
    L.eval_tri.argtypes = [ctypes.POINTER(Img), ctypes.c_int, ctypes.c_int, DP, ctypes.c_double, FP,
                           ctypes.POINTER(ctypes.c_long)]
    L.apply_tri.restype = None
    L.apply_tri.argtypes = [ctypes.POINTER(Img), ctypes.c_int, ctypes.c_int, DP, ctypes.c_double, FP]
    L.fit_region.restype = ctypes.c_int
    L.fit_region.argtypes = [ctypes.POINTER(Img), ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                             ctypes.c_double, ctypes.c_double, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_double, ctypes.c_double, IP, IP, DP]
    L.render_seq.restype = None
    L.render_seq.argtypes = [ctypes.POINTER(Img), FP, ctypes.c_int, DP, FP, ctypes.c_double]
    L.backfit_colors.restype = None
    L.backfit_colors.argtypes = [ctypes.POINTER(Img), ctypes.c_int, DP, FP, ctypes.c_double, ctypes.c_int]
    L.set_lweight.restype = None
    L.set_lweight.argtypes = [ctypes.c_double]
    L.set_lweight(LW)
    L.bf_init.restype = ctypes.c_void_p
    L.bf_init.argtypes = [ctypes.POINTER(Img), FP, ctypes.c_int, DP, FP, ctypes.c_double]
    L.bf_range.restype = None
    L.bf_range.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                           ctypes.c_uint64]
    L.bf_finish.restype = None
    L.bf_finish.argtypes = [ctypes.c_void_p]
    L.build_cdf.restype = ctypes.c_double
    L.build_cdf.argtypes = [ctypes.POINTER(Img), ctypes.c_int, ctypes.c_int, DP]
    L.search_one.restype = ctypes.c_double
    L.search_one.argtypes = [ctypes.POINTER(Img), ctypes.c_void_p, ctypes.c_int, ctypes.c_int, DP, ctypes.c_double,
                             ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, ctypes.c_double, DP, FP]
    L.pref_new.restype = ctypes.c_void_p
    L.pref_new.argtypes = [ctypes.POINTER(Img), ctypes.c_int, ctypes.c_int, ctypes.c_double]
    L.pref_update_tri.restype = None
    L.pref_update_tri.argtypes = [ctypes.c_void_p, ctypes.POINTER(Img), DP]
    L.removal_costs.restype = None
    L.removal_costs.argtypes = [ctypes.POINTER(Img), FP, ctypes.c_int, DP, FP, ctypes.c_double, DP]
    L.pref_free.restype = None
    L.pref_free.argtypes = [ctypes.c_void_p]
    return L


class Canvas:
    """目标 T、画布 C、逐像素误差 E（float32），以及传给 C 的结构体。"""

    def __init__(self, T, bg):
        self.T = np.ascontiguousarray(T, np.float32)
        self.C = np.empty_like(self.T)
        self.C[:] = bg
        d = self.T - self.C
        self.E = np.ascontiguousarray((d ** 2).sum(-1) + LW * (d @ np.array([0.299, 0.587, 0.114], np.float32)) ** 2,
                                      np.float32)
        H, W = self.T.shape[:2]
        self.img = Img(W, H, self.T.ctypes.data_as(FP), self.C.ctypes.data_as(FP), self.E.ctypes.data_as(FP))


def fit(L, cv, xlo, xhi, n, seed, smin, smax, K, age, maxit, reps, deadline):
    tri = np.zeros(max(n, 1) * 6, np.int32)
    col = np.zeros(max(n, 1) * 3, np.int32)
    gain = np.zeros(max(n, 1), np.float64)
    cnt = L.fit_region(ctypes.byref(cv.img), xlo, xhi, n, seed, smin, smax, K, age, maxit, reps, A, deadline,
                       tri.ctypes.data_as(IP), col.ctypes.data_as(IP), gain.ctypes.data_as(DP))
    return [(tri[6 * k:6 * k + 6].tolist(), col[3 * k:3 * k + 3].tolist(), float(gain[k])) for k in range(cnt)]


def fit_parallel(L, cv, n, seed, smin, smax, K, age, maxit, reps, deadline, pool, workers):
    """全图贪心加形状；每个形状由 workers 个线程各自搜索（不同种子），取最好的落笔。"""
    H, W = cv.T.shape[:2]
    cdf = np.empty(H * W, np.float64)
    cdf_p = cdf.ctypes.data_as(DP)
    outs = [(np.zeros(6, np.float64), np.zeros(3, np.float32)) for _ in range(workers)]
    rng = np.random.default_rng(seed)
    shapes, exts, misses = [], [], 0
    pf = L.pref_new(ctypes.byref(cv.img), 0, W, A)  # 行前缀和，所有线程共享只读
    while len(shapes) < n and misses < 30 and time.time() < deadline:
        acc = L.build_cdf(ctypes.byref(cv.img), 0, W, cdf_p)
        top = smax
        if len(exts) >= 20 and rng.random() < 0.85:
            top = min(smax, max(3 * smin, 0.8 * float(np.median(exts[-30:]))))
        base = int(rng.integers(1 << 40))

        def job(w):
            return L.search_one(ctypes.byref(cv.img), pf, 0, W, cdf_p, acc, base + w, smin, top, K, age, maxit, reps,
                                A, outs[w][0].ctypes.data_as(DP), outs[w][1].ctypes.data_as(FP))

        bds = list(pool.map(job, range(workers)))
        w = int(np.argmin(bds))
        if bds[w] >= 0:
            misses += 1
            continue
        misses = 0
        p, col = outs[w]
        L.apply_tri(ctypes.byref(cv.img), 0, W, p.ctypes.data_as(DP), A, col.ctypes.data_as(FP))
        L.pref_update_tri(pf, ctypes.byref(cv.img), p.ctypes.data_as(DP))
        exts.append(max(np.ptp(p[0::2]), np.ptp(p[1::2])) / 2.5)
        shapes.append((p.astype(int).tolist(), [int(round(c * 255)) for c in col], -bds[w]))
    L.pref_free(pf)
    return shapes


def path_d(t):
    """第一个点用绝对坐标，后两个点用相对坐标（小三角形只要一两位数）；负号本身就能当分隔符。"""
    out = f"M{t[0]} {t[1]}l"
    for k, v in enumerate((t[2] - t[0], t[3] - t[1], t[4] - t[2], t[5] - t[3])):
        out += str(v) if (k == 0 or v < 0) else " " + str(v)
    return out  # 填充时未闭合的路径会自动闭合，末尾的 z 可以省掉


def svg_order(seq):
    """同一轮里不同块的形状互不重叠，按块从左到右排不改变画面，但能让相邻坐标更接近、压缩更好。"""
    return sorted(range(len(seq)), key=lambda k: (seq[k][2], seq[k][3], k))


def to_svg(W, H, bg, seq):
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
             f'<rect width="{W}" height="{H}" fill="#%02x%02x%02x"/>' % tuple(bg),
             f'<g fill-opacity="{A:g}">']
    for k in svg_order(seq):
        tri, col = seq[k][0], seq[k][1]
        lines.append('<path fill="#%02x%02x%02x" d="%s"/>' % (*col, path_d(tri)))
    lines.append("</g></svg>")
    return ("\n".join(lines) + "\n").encode()


def fit_budget(W, H, bg, seq, budget):
    """二分找最长的前缀，使 gzip 后不超过预算。"""
    lo, hi = 0, len(seq)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(gzip.compress(to_svg(W, H, bg, seq[:mid]), 9)) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return lo, to_svg(W, H, bg, seq[:lo])


def backfit_geom(L, cv, bgf, pre, tris, cols, iters, seed, pool):
    """几何回拟合：阶段 1 的形状互相重叠，顺序处理；阶段 2 每一轮里按块并行（各块限制在自己的列范围内）。"""
    n = len(pre)
    h = L.bf_init(ctypes.byref(cv.img), bgf.ctypes.data_as(FP), n, tris.ctypes.data_as(DP), cols.ctypes.data_as(FP), A)
    k = 0
    while k < n:
        rd = pre[k][2]
        e = k
        while e < n and pre[e][2] == rd:
            e += 1
        if rd < 0:
            L.bf_range(h, k, e, 0, cv.T.shape[1], iters, seed)
        else:
            groups, g0 = [], k
            for j in range(k + 1, e + 1):
                if j == e or pre[j][3] != pre[g0][3]:
                    groups.append((g0, j, pre[g0][4], pre[g0][5]))
                    g0 = j
            list(pool.map(lambda g: L.bf_range(h, g[0], g[1], g[2], g[3], iters, seed * 7919 + g[0]), groups))
        k = e
    L.bf_finish(h)


PROF = {}


def tick(name, t0):
    """PROFILE=1 时打印各步骤耗时（累计）。"""
    PROF[name] = PROF.get(name, 0.0) + time.time() - t0
    return time.time()


def cpu_mark(name, wall0, cpu0):
    """记录某阶段的墙钟时间和所有线程合计的 CPU 时间，用来看并行利用率。"""
    PROF[name + ":wall"] = round(time.time() - wall0, 2)
    PROF[name + ":cpu"] = round(time.process_time() - cpu0, 2)


def refill(L, cv, n_add, rd, K, reps, deadline, pool, seed, tiles=48, age=150, maxit=2000):
    """在当前画布上用分块贪心补 n_add 个新形状（两轮，第二轮错开半块），返回新形状（seq 格式）。"""
    H, W = cv.T.shape[:2]
    tw, out = W / tiles, []
    for r in range(2):
        n_r = n_add // 2 if r == 0 else n_add - n_add // 2
        if n_r <= 0:
            continue
        off = tw / 2 if r % 2 else 0.0
        cuts = [0] + [int(round(off + k * tw)) for k in range(tiles)] + [W] if off else \
            [int(round(k * tw)) for k in range(tiles + 1)]
        err = np.array([cv.E[:, cuts[i]:cuts[i + 1]].sum() for i in range(len(cuts) - 1)], np.float64)
        share = 0.3 * np.diff(cuts) / W + 0.7 * err / err.sum()
        caps = np.floor(n_r * share).astype(int)
        caps[np.argsort(-(n_r * share - caps))[:n_r - caps.sum()]] += 1
        jobs = [(cuts[i], cuts[i + 1], int(caps[i]), seed * 7777 + r * 1000 + i + 1)
                for i in range(len(cuts) - 1) if caps[i] > 0]
        res = list(pool.map(lambda j: fit(L, cv, j[0], j[1], j[2], j[3], 1.2, H // 2, K, age, maxit, reps, deadline),
                            jobs))
        for ti, shapes in enumerate(res):
            out += [(sh[0], sh[1], rd + r, ti, jobs[ti][0], jobs[ti][1]) for sh in shapes]
    return out


def finalize(L, T, bg, seq, budget, pool, sweeps=3, geom_iters=200, K=300, reps=8, deadline=0.0, age=150, maxit=2000):
    """取满足预算的前缀，按这个前缀重新渲染，再做颜色回拟合；改色后若超预算就从尾部少取几个。"""
    H, W = T.shape[:2]
    bgi = np.round(bg * 255).astype(int).tolist()
    tp = time.time()
    n, _ = fit_budget(W, H, bgi, seq, budget)
    tp = tick(f"fin{budget}:fit_budget", tp)
    pre = [seq[k] for k in svg_order(seq[:n])]
    tris = np.ascontiguousarray(np.array([sh[0] for sh in pre], np.float64).reshape(-1))
    cols = np.ascontiguousarray(np.array([sh[1] for sh in pre], np.float32).reshape(-1) / 255)
    cv = Canvas(T, bg)
    bgf = np.ascontiguousarray(bg, np.float32)
    L.render_seq(ctypes.byref(cv.img), bgf.ctypes.data_as(FP), n, tris.ctypes.data_as(DP), cols.ctypes.data_as(FP), A)
    if sweeps > 0 and n > 0:
        L.backfit_colors(ctypes.byref(cv.img), n, tris.ctypes.data_as(DP), cols.ctypes.data_as(FP), A, sweeps)
    tp = tick(f"fin{budget}:render+color", tp)
    for rep in range(GEOM_PASSES if geom_iters > 0 and n > 0 else 0):
        backfit_geom(L, cv, bgf, pre, tris, cols, geom_iters, budget + 1000 * rep, pool)
        tp = tick(f"fin{budget}:geom", tp)
        L.backfit_colors(ctypes.byref(cv.img), n, tris.ctypes.data_as(DP), cols.ctypes.data_as(FP), A, 1)
        tp = tick(f"fin{budget}:color2", tp)
    if PRUNE_TAU > 0 and n > 50:
        # 删减：算每个形状的删除代价，删掉不值它所占字节的；再用同样数量的新形状补上
        cost = np.zeros(n)
        L.removal_costs(ctypes.byref(cv.img), bgf.ctypes.data_as(FP), n, tris.ctypes.data_as(DP),
                        cols.ctypes.data_as(FP), A, cost.ctypes.data_as(DP))
        last_rd = max(sh[2] for sh in pre)
        last = [k for k in range(n) if pre[k][2] == last_rd]
        marg = float(np.mean(cost[last])) if last else 0.0
        keep = [k for k in range(n) if cost[k] >= PRUNE_TAU * marg]
        n_drop = n - len(keep)
        PROF[f"fin{budget}:pruned"] = n_drop
        if n_drop > 0:
            kept = [([int(v) for v in tris[6 * k:6 * k + 6]], [int(round(c * 255)) for c in cols[3 * k:3 * k + 3]],
                     pre[k][2], pre[k][3], pre[k][4], pre[k][5]) for k in keep]
            cv = Canvas(T, bg)
            kt = np.ascontiguousarray(np.array([sh[0] for sh in kept], np.float64).reshape(-1))
            kc = np.ascontiguousarray(np.array([sh[1] for sh in kept], np.float32).reshape(-1) / 255)
            L.render_seq(ctypes.byref(cv.img), bgf.ctypes.data_as(FP), len(kept), kt.ctypes.data_as(DP),
                         kc.ctypes.data_as(FP), A)
            new_shapes = refill(L, cv, n_drop, last_rd + 1, K, reps, deadline, pool, budget, age=age, maxit=maxit)
            pre = kept + [new_shapes[k] for k in svg_order(new_shapes)]
            n = len(pre)
            tris = np.ascontiguousarray(np.array([sh[0] for sh in pre], np.float64).reshape(-1))
            cols = np.ascontiguousarray(np.array([sh[1] for sh in pre], np.float32).reshape(-1) / 255)
            L.render_seq(ctypes.byref(cv.img), bgf.ctypes.data_as(FP), n, tris.ctypes.data_as(DP),
                         cols.ctypes.data_as(FP), A)
            L.backfit_colors(ctypes.byref(cv.img), n, tris.ctypes.data_as(DP), cols.ctypes.data_as(FP), A, 1)
            backfit_geom(L, cv, bgf, pre, tris, cols, geom_iters, budget + 5000, pool)
            L.backfit_colors(ctypes.byref(cv.img), n, tris.ctypes.data_as(DP), cols.ctypes.data_as(FP), A, 1)
        tp = tick(f"fin{budget}:prune+refill", tp)
    if os.environ.get("SOLVER_CHECK"):  # 调试：并行回拟合后的画布必须和从头重新渲染的一致
        chk = Canvas(T, bg)
        L.render_seq(ctypes.byref(chk.img), bgf.ctypes.data_as(FP), n, tris.ctypes.data_as(DP),
                     cols.ctypes.data_as(FP), A)
        print(f"CHECK budget={budget} max|diff|={np.abs(chk.C - cv.C).max():.2e} err={cv.E.sum():.1f}/{chk.E.sum():.1f}")
    new = [([int(v) for v in tris[6 * k:6 * k + 6]], [int(round(c * 255)) for c in cols[3 * k:3 * k + 3]], -1, 0, 0, W)
           for k in range(n)]
    svg = to_svg(W, H, bgi, new)
    while n > 0 and len(gzip.compress(svg, 9)) > budget:
        n -= max(1, n // 200)
        svg = to_svg(W, H, bgi, new[:n])
    return n, svg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("outdir")
    ap.add_argument("--time", type=float, default=60)
    ap.add_argument("--budgets", default="16000,160000")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--effort", type=float, default=1.0, help="搜索力度倍数：越小越快，越大越细")
    ap.add_argument("--tiles", type=int, default=48, help="阶段 2 的竖条数（长卷用 48；普通照片按宽度约 100 像素一条）")
    a = ap.parse_args()
    K, reps2, giters = max(30, int(300 * a.effort)), max(1, round(8 * a.effort)), max(10, int(200 * a.effort))
    age, maxit = max(30, int(150 * min(1.0, a.effort))), max(300, int(2000 * min(1.0, a.effort)))  # 爬山耐心：低力度时也缩小
    t0 = time.time()
    deadline = t0 + a.time - 6  # 留时间写文件
    budgets = sorted(int(b) for b in a.budgets.split(","))
    L = load_core()

    img = Image.open(a.target).convert("RGB")
    T = np.asarray(img, dtype=np.float32) / 255
    H, W = T.shape[:2]
    bg = np.round(T.reshape(-1, 3).mean(0) * 255) / 255
    need = 10 ** 9  # 还需要多少个形状：每轮结束按实测的每形状字节数重新估

    # 阶段 1：半分辨率全局铺大形，每个形状 12 线程并行搜索
    f, n0 = 1, 1000
    tiles, workers = a.tiles, 12
    pool = ThreadPoolExecutor(workers)
    w0, c0 = time.time(), time.process_time()
    Tl = np.asarray(img.resize((W // f, H // f), Image.BOX), dtype=np.float32) / 255
    s1 = fit_parallel(L, Canvas(Tl, bg), n0, a.seed, 1.2, H // f, K, age, maxit, 1, t0 + 0.45 * a.time, pool,
                      workers)
    cv = Canvas(T, bg)
    seq = []
    colbuf, npix = (ctypes.c_float * 3)(), ctypes.c_long()
    for tri, _, _ in s1:
        p = (ctypes.c_double * 6)(*[v * f for v in tri])
        d = L.eval_tri(ctypes.byref(cv.img), 0, W, p, A, colbuf, ctypes.byref(npix))
        if npix.value == 0 or d >= 0:
            continue
        L.apply_tri(ctypes.byref(cv.img), 0, W, p, A, colbuf)
        seq.append(([int(v) for v in p], [int(round(c * 255)) for c in colbuf], -1, 0, 0, W))
    t1 = time.time()
    cpu_mark("stage1", w0, c0)
    w0, c0 = time.time(), time.process_time()

    # 阶段 2：分轮切块，线程并行（C 内核调用时释放 GIL，各块列范围互不重叠）
    tw = W / tiles
    rd, step_n, last = 0, 300, None
    with pool:
        while need > 0:
            n_r = min(step_n, need)
            if last is not None and time.time() + last[1] * n_r / last[0] * 1.2 > deadline:
                break
            ts = time.time()
            off = tw / 2 if rd % 2 else 0.0
            cuts = [0] + [int(round(off + k * tw)) for k in range(tiles)] + [W] if off else \
                [int(round(k * tw)) for k in range(tiles + 1)]
            err = np.array([cv.E[:, cuts[i]:cuts[i + 1]].sum() for i in range(len(cuts) - 1)], np.float64)
            share = 0.3 * np.diff(cuts) / W + 0.7 * err / err.sum()
            caps = np.floor(n_r * share).astype(int)
            caps[np.argsort(-(n_r * share - caps))[:n_r - caps.sum()]] += 1
            jobs = [(cuts[i], cuts[i + 1], int(caps[i]), a.seed * 100000 + rd * 1000 + i + 1)
                    for i in range(len(cuts) - 1) if caps[i] > 0]
            res = list(pool.map(lambda j: fit(L, cv, j[0], j[1], j[2], j[3], 1.2, H // 2, K, age, maxit, reps2,
                                              deadline), jobs))
            res = [[(sh[0], sh[1], sh[2], ti, jobs[ti][0], jobs[ti][1]) for sh in shapes] for ti, shapes in enumerate(res)]
            items = []
            for ti, shapes in enumerate(res):
                g = np.minimum.accumulate([sh[2] for sh in shapes]) if shapes else []
                for k, sh in enumerate(shapes):
                    items.append((-float(g[k]), ti, k, sh))
            items.sort(key=lambda z: (z[0], z[1], z[2]))
            if not items:  # 这一轮没有任何形状能降低误差（比如纯色图），再加也没用
                break
            seq += [(sh[0], sh[1], rd, sh[3], sh[4], sh[5]) for _, _, _, sh in items]
            last = (max(1, len(items)), time.time() - ts)
            rd += 1
            gz = len(gzip.compress(to_svg(W, H, np.round(bg * 255).astype(int).tolist(), seq), 9))
            need = 0 if gz > budgets[-1] else int((budgets[-1] - gz) / (gz / len(seq)) * 1.1) + 50
            if rd % 2 == 0:
                step_n *= 2

    cpu_mark("stage2", w0, c0)
    w0, c0 = time.time(), time.process_time()
    os.makedirs(a.outdir, exist_ok=True)
    counts = {}
    fin_pool = ThreadPoolExecutor(workers)
    with ThreadPoolExecutor(len(budgets)) as bp:
        outs = list(bp.map(lambda b: finalize(L, T, bg, seq, b, fin_pool, geom_iters=giters, K=K, reps=reps2,
                                              deadline=deadline, age=age, maxit=maxit), budgets))
    for b, (n, svg) in zip(budgets, outs):
        open(os.path.join(a.outdir, f"b{b}.svg"), "wb").write(svg)
        counts[b] = n
    cpu_mark("finalize", w0, c0)
    if os.environ.get("PROFILE"):
        print("PROFILE " + json.dumps({k: round(v, 2) for k, v in PROF.items()}, ensure_ascii=False))
    print("RESULT " + json.dumps({"shapes": counts, "total": len(seq), "stage1_s": round(t1 - t0, 1),
                                  "total_s": round(time.time() - t0, 1)}))


if __name__ == "__main__":
    main()

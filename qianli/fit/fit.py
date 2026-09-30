"""用半透明三角形逐个贪心拟合目标图，结果就是一份 SVG 代码。

做法同 Fogleman 的 primitive：每一步随机撒一批候选三角形，挑误差下降最多的，
再对它做爬山微调；三角形颜色按最小二乘直接算出。透明度固定 0.5。
先在低分辨率上铺大块形状（阶段 1），再分轮把长卷切块并行补细节（阶段 2）。
相邻两轮的切块位置错开半块，形状可以跨过上一轮的块边界，避免固定接缝。
每轮内部按形状带来的误差下降量把各块的形状合并成一条顺序：
取前 N 个，就是"N 个形状的程序"。

用法: python3 fit.py target.png out.json --total 20000
"""
import argparse
import json
import time
from multiprocessing import Pool

import numpy as np
from PIL import Image

A = 0.5


def raster(tri, xlo, xhi, H):
    """三角形覆盖的像素（按像素中心采样），裁到 [xlo, xhi) × [0, H)。"""
    x = tri[0::2].astype(np.float64)
    y = tri[1::2].astype(np.float64)
    area = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0])
    if area == 0:
        return None
    j0 = max(xlo, int(np.ceil(x.min() - 0.5)))
    j1 = min(xhi - 1, int(np.floor(x.max() - 0.5)))
    i0 = max(0, int(np.ceil(y.min() - 0.5)))
    i1 = min(H - 1, int(np.floor(y.max() - 0.5)))
    if j1 < j0 or i1 < i0:
        return None
    px = np.arange(j0, j1 + 1, dtype=np.float64) + 0.5
    py = np.arange(i0, i1 + 1, dtype=np.float64)[:, None] + 0.5
    s = 1.0 if area > 0 else -1.0
    m = np.ones((i1 - i0 + 1, j1 - j0 + 1), bool)
    for k in range(3):
        xa, ya, xb, yb = x[k], y[k], x[(k + 1) % 3], y[(k + 1) % 3]
        m &= ((xb - xa) * (py - ya) - (yb - ya) * (px - xa)) * s >= 0
    if not m.any():
        return None
    return i0, i1 + 1, j0, j1 + 1, m


def evaluate(tri, T, C, E, xlo, xhi):
    """返回 (误差变化量, 最优颜色, 覆盖区域)。误差变化量为负表示变好。"""
    r = raster(tri, xlo, xhi, T.shape[0])
    if r is None:
        return 0.0, None, None
    i0, i1, j0, j1, m = r
    t = T[i0:i1, j0:j1][m]
    c = C[i0:i1, j0:j1][m]
    col = np.clip(((t - (1 - A) * c) / A).mean(0), 0, 1)
    col = np.round(col * 255) / 255
    new = (1 - A) * c + A * col
    d = float(((t - new) ** 2).sum() - E[i0:i1, j0:j1][m].sum())
    return d, col, r


def apply(col, r, T, C, E):
    i0, i1, j0, j1, m = r
    sub = C[i0:i1, j0:j1]
    sub[m] = (1 - A) * sub[m] + A * col
    E[i0:i1, j0:j1] = ((T[i0:i1, j0:j1] - C[i0:i1, j0:j1]) ** 2).sum(-1)


def fit_region(T, C, xlo, xhi, n, seed, smin, smax, K=40, age=60, maxit=300):
    """在 [xlo, xhi) 这一段里贪心加 n 个三角形，原地修改 C。"""
    rng = np.random.default_rng(seed)
    H = T.shape[0]
    w = xhi - xlo
    E = ((T - C) ** 2).sum(-1)
    shapes, exts, misses = [], [], 0

    def clamp(p):
        p = np.round(p)
        p[0::2] = np.clip(p[0::2], xlo, xhi)
        p[1::2] = np.clip(p[1::2], 0, H)
        return p

    while len(shapes) < n and misses < 30:
        cdf = np.cumsum(E[:, xlo:xhi].ravel())
        top = smax
        if len(exts) >= 20 and rng.random() < 0.85:  # 后期形状变小，大候选少撒一些
            top = min(smax, max(3 * smin, 0.8 * float(np.median(exts[-30:]))))
        best, bd, bc, br = None, 0.0, None, None
        for _ in range(K):
            if rng.random() < 0.7:  # 按当前误差分布选中心
                cy, cx = divmod(int(np.searchsorted(cdf, rng.random() * cdf[-1])), w)
                cx += xlo + rng.random()
                cy += rng.random()
            else:
                cx, cy = rng.uniform(xlo, xhi), rng.uniform(0, H)
            s = np.exp(rng.uniform(np.log(smin), np.log(top)))
            ax = np.exp(rng.uniform(np.log(0.5), np.log(3.0)))  # 山水多横向，允许拉长
            p = np.empty(6)
            p[0::2] = cx + rng.normal(0, s * ax, 3)
            p[1::2] = cy + rng.normal(0, s / ax, 3)
            p = clamp(p)
            d, col, r = evaluate(p, T, C, E, xlo, xhi)
            if r is not None and d < bd:
                best, bd, bc, br = p, d, col, r
        if best is None:
            misses += 1
            continue
        fails = it = 0
        while fails < age and it < maxit:  # 爬山：随机挪一个顶点或整体平移
            it += 1
            q = best.copy()
            ext = max(np.ptp(q[0::2]), np.ptp(q[1::2]), 2.0)
            if rng.random() < 0.25:
                q[0::2] += rng.normal(0, ext * 0.15)
                q[1::2] += rng.normal(0, ext * 0.15)
            else:
                k = rng.integers(3)
                sg = max(1.0, ext * 0.2)
                q[2 * k] += rng.normal(0, sg)
                q[2 * k + 1] += rng.normal(0, sg)
            q = clamp(q)
            d, col, r = evaluate(q, T, C, E, xlo, xhi)
            if r is not None and d < bd:
                best, bd, bc, br = q, d, col, r
                fails = 0
            else:
                fails += 1
        apply(bc, br, T, C, E)
        misses = 0
        exts.append(max(np.ptp(best[0::2]), np.ptp(best[1::2])) / 2.5)
        shapes.append((best.astype(int).tolist(), np.round(bc * 255).astype(int).tolist(), -bd))
    return shapes


def _tile_job(args):
    """只把这一块的像素传给子进程，坐标在块内算完再平移回全图。"""
    Tt, Ct, xlo, n, seed, smax = args
    t0 = time.time()
    shapes = fit_region(Tt, Ct, 0, Tt.shape[1], n, seed, smin=1.2, smax=smax)
    for tri, _, _ in shapes:
        tri[0::2] = [v + xlo for v in tri[0::2]]
    return xlo, xlo + Tt.shape[1], shapes, time.time() - t0, Ct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("out")
    ap.add_argument("--total", type=int, default=20000, help="阶段 2 的形状总数")
    ap.add_argument("--n0", type=int, default=1000, help="阶段 1（低分辨率、全局）的形状数")
    ap.add_argument("--f", type=int, default=2, help="阶段 1 的降采样倍数")
    ap.add_argument("--round0", type=int, default=300, help="阶段 2 第一轮的形状数，之后每两轮翻倍")
    ap.add_argument("--tiles", type=int, default=24)
    ap.add_argument("--procs", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    T = np.asarray(Image.open(a.target).convert("RGB"), dtype=np.float64) / 255
    H, W = T.shape[:2]
    bg = np.round(T.reshape(-1, 3).mean(0) * 255) / 255
    t0 = time.time()

    # 阶段 1：低分辨率上铺大形
    f = a.f
    Tl = np.asarray(Image.open(a.target).convert("RGB").resize((W // f, H // f), Image.BOX), dtype=np.float64) / 255
    Cl = np.empty_like(Tl)
    Cl[:] = bg
    s1 = fit_region(Tl, Cl, 0, W // f, a.n0, a.seed, smin=1.2, smax=H // f, K=48, age=80, maxit=400)
    print(f"stage1: {len(s1)} shapes, {time.time() - t0:.0f}s", flush=True)

    # 放大到原分辨率，按顺序重新算颜色
    C = np.empty_like(T)
    C[:] = bg
    E = ((T - C) ** 2).sum(-1)
    stage1 = []
    for tri, _, _ in s1:
        p = np.array(tri, np.float64) * f
        d, col, r = evaluate(p, T, C, E, 0, W)
        if r is None or d >= 0:
            continue
        apply(col, r, T, C, E)
        stage1.append((p.astype(int).tolist(), np.round(col * 255).astype(int).tolist(), -d))
    print(f"stage1 recolored at full res: {len(stage1)} kept, {time.time() - t0:.0f}s", flush=True)

    # 阶段 2：分轮切块并行。每轮的形状数正好分给各块用完，保证下一轮的起点和程序一致
    sizes, done, step_n = [], 0, a.round0
    while done < a.total:
        for _ in range(2):
            if done < a.total:
                sizes.append(min(step_n, a.total - done))
                done += sizes[-1]
        step_n *= 2
    tw = W / a.tiles
    stage2 = []
    with Pool(a.procs) as pool:
        for rd, n_r in enumerate(sizes):
            off = tw / 2 if rd % 2 else 0.0
            if off:
                cuts = [0] + [int(round(off + k * tw)) for k in range(a.tiles)] + [W]
            else:
                cuts = [int(round(k * tw)) for k in range(a.tiles + 1)]
            err = np.array([E[:, cuts[i]:cuts[i + 1]].sum() for i in range(len(cuts) - 1)])
            share = 0.3 * np.diff(cuts) / W + 0.7 * err / err.sum()
            caps = np.floor(n_r * share).astype(int)
            caps[np.argsort(-(n_r * share - caps))[:n_r - caps.sum()]] += 1
            jobs = [(T[:, cuts[i]:cuts[i + 1]].copy(), C[:, cuts[i]:cuts[i + 1]].copy(), cuts[i], int(caps[i]),
                     a.seed * 100000 + rd * 1000 + i + 1, H // 2) for i in range(len(cuts) - 1) if caps[i] > 0]
            res = pool.map(_tile_job, jobs)
            items = []
            for ti, (xlo, xhi, shapes, _, Ct) in enumerate(res):
                C[:, xlo:xhi] = Ct
                g = np.minimum.accumulate([sh[2] for sh in shapes]) if shapes else []
                for k, sh in enumerate(shapes):
                    items.append((-float(g[k]), ti, k, sh))
            items.sort(key=lambda z: (z[0], z[1], z[2]))
            stage2 += [(sh[0], sh[1], sh[2], rd) for _, _, _, sh in items]
            E = ((T - C) ** 2).sum(-1)
            print(f"round {rd}: +{len(items)} shapes (offset {off:.0f}), total {len(stage1) + len(stage2)}, "
                  f"{time.time() - t0:.0f}s", flush=True)

    json.dump({"W": W, "H": H, "bg": np.round(bg * 255).astype(int).tolist(), "alpha": A,
               "stage1": stage1, "stage2": stage2, "rounds": sizes, "tiles": a.tiles,
               "seconds": time.time() - t0}, open(a.out, "w"))
    print(f"saved {a.out}: {len(stage1)} + {len(stage2)} shapes, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

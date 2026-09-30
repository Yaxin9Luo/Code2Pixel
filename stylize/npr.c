// 笔触渲染内核（给 stylize.py 用 ctypes 调用）。
//
// paint_layer：一层笔触（同一支笔）。Hertzmann 1998 的多尺度曲线笔触，但逐笔更新画布：
//   网格格子按随机顺序过一遍；格子里"画布和目标差多少"超过阈值就在差得最多的像素起笔，
//   沿流场方向走，走到"再画不划算"或"跨过边界"时收笔，然后立刻画到画布上，下一笔看到的是新画布。
//   每个像素算出它在笔触里的坐标（沿笔长 u、横跨笔宽 v），再按画种合成：
//     mode 0 油画：不透明覆盖 + 鬃毛条纹 + 颜料厚度（高度图，用来打光）
//     mode 1 水墨：墨浓度按"透光率相乘"累积；笔内一侧浓一侧淡、墨越走越干、飞白、湿边
//     mode 2 水彩：吸光度相加（透明罩染），笔触边缘积色
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static inline uint64_t sm64(uint64_t *s) {
    uint64_t z = (*s += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}
static inline float frand(uint64_t *s) { return (sm64(s) >> 40) * (1.0f / 16777216.0f); }
static inline float clampf(float x, float a, float b) { return x < a ? a : (x > b ? b : x); }
static inline float smooth(float a, float b, float x) {
    float t = clampf((x - a) / (b - a), 0.f, 1.f);
    return t * t * (3 - 2 * t);
}

static void sample(const float *img, int H, int W, int C, float x, float y, float *out) {
    x = clampf(x - 0.5f, 0, W - 1.001f);
    y = clampf(y - 0.5f, 0, H - 1.001f);
    int x0 = (int)x, y0 = (int)y;
    float fx = x - x0, fy = y - y0;
    const float *p00 = img + ((size_t)y0 * W + x0) * C, *p01 = p00 + C, *p10 = p00 + (size_t)W * C, *p11 = p10 + C;
    for (int c = 0; c < C; c++)
        out[c] = (p00[c] * (1 - fx) + p01[c] * fx) * (1 - fy) + (p10[c] * (1 - fx) + p11[c] * fx) * fy;
}

static float dist(const float *a, const float *b, int C) {
    float s = 0;
    for (int c = 0; c < C; c++) s += (a[c] - b[c]) * (a[c] - b[c]);
    return sqrtf(s);
}

// 层参数 lp（下标）：
enum {
    L_R, L_STEP, L_GRID, L_T, L_MINLEN, L_MAXLEN, L_FC, L_STOP,   // 笔半径、步长、网格、起笔阈值、最短/最长步数、方向惯性、收笔阈值
    L_RJLO, L_RJHI,                                               // 每笔半径随机倍数范围
    L_TIN, L_TOUT, L_OP,                                          // 起笔渐粗占比、收笔渐细占比、不透明度（墨量系数）
    L_GRAD, L_DRYP, L_DRY, L_SOFT, L_BRISTLE,                     // 横向浓淡幅度、干笔概率、干笔程度、边缘软度、鬃毛条纹强度
    L_DEPLETE, L_RIM, L_RIMW, L_THICK, L_JIT,                     // 墨沿笔长变淡、水彩积色强度/带宽、油画颜料厚度、颜色扰动
    L_MIX, L_RIDGE,                                               // 油画：一笔里混进第二种颜色的程度、笔触边缘和末端的颜料堆
    L_N
};

typedef struct {
    float *poly, *cum, *bd, *bu, *bs;
    int maxPoly;
    size_t cap;
} Scratch;

// Catmull-Rom 细分：控制点 → 间隔约 seglen 像素的折线（大笔用粗一些的折线就够平滑）。返回点数。
static int spline(const float *P, int n, float *out, int maxOut, float seglen) {
    if (n == 1) { out[0] = P[0]; out[1] = P[1]; return 1; }
    int m = 0;
    for (int i = 0; i < n - 1; i++) {
        const float *p0 = P + 2 * (i > 0 ? i - 1 : i), *p1 = P + 2 * i, *p2 = P + 2 * (i + 1),
                    *p3 = P + 2 * (i + 2 < n ? i + 2 : i + 1);
        float seg = hypotf(p2[0] - p1[0], p2[1] - p1[1]);
        int sub = (int)ceilf(seg / seglen);
        if (sub < 1) sub = 1;
        for (int j = 0; j < sub && m < maxOut - 1; j++) {
            float t = (float)j / sub, t2 = t * t, t3 = t2 * t;
            for (int c = 0; c < 2; c++)
                out[2 * m + c] = 0.5f * ((2 * p1[c]) + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2 +
                                         (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3);
            m++;
        }
    }
    out[2 * m] = P[2 * (n - 1)];
    out[2 * m + 1] = P[2 * (n - 1) + 1];
    return m + 1;
}

// 从 (px,py) 起笔，沿流场走。返回控制点数（写到 P）。col 是这一笔的颜色（mode 1 为墨量 k）。
static int trace_one(const float *ref, const float *canvas, int H, int W, int C, const float *tx, const float *ty,
                     const float *lp, int mode, float px, float py, const float *col, float *P, int maxPts) {
    float rv[8], cv[8];
    int maxLen = (int)lp[L_MAXLEN] < maxPts ? (int)lp[L_MAXLEN] : maxPts;
    int minLen = (int)lp[L_MINLEN];
    float step = lp[L_STEP], fc = lp[L_FC], stop = lp[L_STOP];
    P[0] = px; P[1] = py;
    int k = 1;
    float lx = 0, ly = 0;
    for (int i = 1; i < maxLen; i++) {
        int ix = (int)clampf(px, 0, W - 1), iy = (int)clampf(py, 0, H - 1);
        float dx = tx[(size_t)iy * W + ix], dy = ty[(size_t)iy * W + ix];
        if (lx * dx + ly * dy < 0) { dx = -dx; dy = -dy; }
        if (i > 1) {
            dx = fc * dx + (1 - fc) * lx;
            dy = fc * dy + (1 - fc) * ly;
        }
        float nn = sqrtf(dx * dx + dy * dy);
        if (nn < 1e-6f) break;
        dx /= nn; dy /= nn;
        float nx = px + step * dx, ny = py + step * dy;
        if (nx < 0 || ny < 0 || nx >= W || ny >= H) break;
        sample(ref, H, W, C, nx, ny, rv);
        sample(canvas, H, W, C, nx, ny, cv);
        if (mode == 1) {
            float pred = 1.f - (1.f - cv[0]) * (1.f - col[0]);
            if (pred > rv[0] + stop) break;                                   // 再走会画得太黑
            if (i >= minLen && fabsf(pred - rv[0]) > fabsf(cv[0] - rv[0])) break;
        } else if (mode == 2) {                                                // 吸光度相加
            float over = 0, gain = 0;
            for (int c = 0; c < C; c++) {
                float pred = cv[c] + col[c];
                over = fmaxf(over, pred - rv[c]);
                gain += fabsf(pred - rv[c]) - fabsf(cv[c] - rv[c]);
            }
            if (over > stop) break;
            if (i >= minLen && gain > 0) break;
        } else {
            float dcol = dist(rv, col, C);
            if (dcol > stop) break;                                            // 跨过边界
            if (i >= minLen && dist(rv, cv, C) < dcol) break;                   // 再画不划算
        }
        px = nx; py = ny; lx = dx; ly = dy;
        P[2 * k] = px; P[2 * k + 1] = py; k++;
    }
    return k;
}

static void ensure(Scratch *S, size_t need) {
    if (need <= S->cap) return;
    free(S->bd); free(S->bu); free(S->bs);
    S->cap = need * 2;
    S->bd = (float *)malloc(sizeof(float) * S->cap);
    S->bu = (float *)malloc(sizeof(float) * S->cap);
    S->bs = (float *)malloc(sizeof(float) * S->cap);
}

// 画一笔。sp: 半径, 横向浓淡, 干笔程度, 颜色扰动种子已并入 rs。
static void render_one(float *canvas, float *height, int H, int W, int C, const float *P, int np,
                       const float *col, const float *col2, float R, float grad, float dry, const float *lp, int mode,
                       uint64_t *rs, Scratch *S) {
    int m = spline(P, np, S->poly, S->maxPoly, fmaxf(1.5f, 0.25f * R));
    float *poly = S->poly, *cum = S->cum;
    cum[0] = 0;
    for (int i = 1; i < m; i++) cum[i] = cum[i - 1] + hypotf(poly[2 * i] - poly[2 * i - 2], poly[2 * i + 1] - poly[2 * i - 1]);
    float Ltot = cum[m - 1];
    float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f;
    for (int i = 0; i < m; i++) {
        x0 = fminf(x0, poly[2 * i]); x1 = fmaxf(x1, poly[2 * i]);
        y0 = fminf(y0, poly[2 * i + 1]); y1 = fmaxf(y1, poly[2 * i + 1]);
    }
    int bx0 = (int)floorf(x0 - R - 2), by0 = (int)floorf(y0 - R - 2);
    int bx1 = (int)ceilf(x1 + R + 2), by1 = (int)ceilf(y1 + R + 2);
    if (bx0 < 0) bx0 = 0;
    if (by0 < 0) by0 = 0;
    if (bx1 > W) bx1 = W;
    if (by1 > H) by1 = H;
    if (bx1 <= bx0 || by1 <= by0) return;
    int bw = bx1 - bx0, bh = by1 - by0;
    size_t need = (size_t)bw * bh;
    ensure(S, need);
    float *bd = S->bd, *bu = S->bu, *bs = S->bs;
    for (size_t i = 0; i < need; i++) bd[i] = 1e9f;
    int nseg = m > 1 ? m - 1 : 1;
    for (int i = 0; i < nseg; i++) {
        float ax = poly[2 * i], ay = poly[2 * i + 1];
        float cx = m > 1 ? poly[2 * i + 2] : ax, cy = m > 1 ? poly[2 * i + 3] : ay;
        float ex = cx - ax, ey = cy - ay, len2 = ex * ex + ey * ey, len = sqrtf(len2);
        int sx0 = (int)floorf(fminf(ax, cx) - R - 2) - bx0, sx1 = (int)ceilf(fmaxf(ax, cx) + R + 2) - bx0;
        int sy0 = (int)floorf(fminf(ay, cy) - R - 2) - by0, sy1 = (int)ceilf(fmaxf(ay, cy) + R + 2) - by0;
        if (sx0 < 0) sx0 = 0;
        if (sy0 < 0) sy0 = 0;
        if (sx1 > bw) sx1 = bw;
        if (sy1 > bh) sy1 = bh;
        for (int y = sy0; y < sy1; y++) {
            float py = by0 + y + 0.5f;
            for (int x = sx0; x < sx1; x++) {
                float px = bx0 + x + 0.5f;
                float t = len2 > 1e-9f ? ((px - ax) * ex + (py - ay) * ey) / len2 : 0.f;
                t = clampf(t, 0.f, 1.f);
                float dx = px - (ax + t * ex), dy = py - (ay + t * ey);
                float d = sqrtf(dx * dx + dy * dy);
                size_t k = (size_t)y * bw + x;
                if (d < bd[k]) {
                    bd[k] = d;
                    bu[k] = cum[i] + t * len;
                    bs[k] = (ex * (py - ay) - ey * (px - ax)) >= 0 ? 1.f : -1.f;
                }
            }
        }
    }
    // 鬃毛：横跨笔宽的一维随机条纹（平滑过的），用来做条纹和飞白
    float bristle[65];
    for (int i = 0; i < 65; i++) bristle[i] = frand(rs);
    for (int it = 0; it < 2; it++)
        for (int i = 1; i < 64; i++) bristle[i] = 0.25f * bristle[i - 1] + 0.5f * bristle[i] + 0.25f * bristle[i + 1];
    float bmin = 1, bmax = 0;
    for (int i = 0; i < 65; i++) { bmin = fminf(bmin, bristle[i]); bmax = fmaxf(bmax, bristle[i]); }
    for (int i = 0; i < 65; i++) bristle[i] = (bristle[i] - bmin) / (bmax - bmin + 1e-6f);
    float tin = lp[L_TIN], tout = lp[L_TOUT], op = lp[L_OP], soft = lp[L_SOFT], bstr = lp[L_BRISTLE];
    float jit[8];
    for (int c = 0; c < C; c++) jit[c] = (frand(rs) - 0.5f) * lp[L_JIT];
    if (C == 3) {                                        // 只偏色相、不改亮度（破色）
        float y = 0.299f * jit[0] + 0.587f * jit[1] + 0.114f * jit[2];
        for (int c = 0; c < 3; c++) jit[c] -= y;
    }
    for (int y = 0; y < bh; y++) {
        for (int x = 0; x < bw; x++) {
            size_t k = (size_t)y * bw + x;
            float d = bd[k];
            if (d > R + 1.5f) continue;
            float u = Ltot > 1e-6f ? bu[k] / Ltot : 0.5f;
            float wfac = 1.f;                            // 起笔渐粗、收笔渐细
            if (Ltot > 1e-6f) {
                if (tin > 0 && u < tin) wfac = 0.35f + 0.65f * smooth(0.f, 1.f, u / tin);
                if (tout > 0 && u > 1 - tout) wfac = fminf(wfac, 0.2f + 0.8f * smooth(0.f, 1.f, (1 - u) / tout));
            }
            float half = R * wfac;
            if (d > half + 1.f) continue;
            float v = bs[k] * d / fmaxf(half, 0.5f);    // -1..1 横跨笔宽
            float cov = clampf(half + 0.5f - d, 0.f, 1.f);
            float edge = 1.f;
            if (soft > 0) edge = 1.f - smooth(1.f - soft, 1.f + 0.2f * soft, fabsf(v));
            float a = cov * edge;
            float bv = bristle[(int)clampf((v + 1) * 32.f, 0, 64)];
            if (dry > 0) {                               // 干笔：越往后墨越少，鬃毛之间出现空白
                float thr = dry * smooth(0.15f, 1.f, u) * 1.1f;
                a *= smooth(thr - 0.12f, thr + 0.12f, bv);
            }
            if (a <= 0) continue;
            size_t p = (size_t)(by0 + y) * W + (bx0 + x);
            if (mode == 1) {
                float kk = col[0] * op * (1.f + grad * v * 0.5f) * (1.f - lp[L_DEPLETE] * u);
                kk *= 1.f - bstr * 0.5f * (1.f - bv);
                kk = clampf(kk, 0.f, 1.f);
                canvas[p] = 1.f - (1.f - canvas[p]) * (1.f - a * kk);
            } else if (mode == 0) {
                float aa = a * op;
                float shade = 1.f + bstr * (bv - 0.5f) * 0.25f;
                // 一笔里两种颜料：按鬃毛条纹混进第二种颜色（越往笔尾混得越多）
                float mx = lp[L_MIX] * smooth(0.25f, 0.85f, bv) * (0.5f + 0.5f * u);
                for (int c = 0; c < C; c++) {
                    float base = col[c] * (1 - mx) + col2[c] * mx;
                    float cc = clampf((base + jit[c]) * shade, 0.f, 1.f);
                    canvas[p * C + c] = canvas[p * C + c] * (1 - aa) + cc * aa;
                }
                if (height) {
                    float rid = lp[L_RIDGE] * (smooth(0.6f, 0.95f, fabsf(v)) + smooth(0.8f, 1.f, u));
                    float th = lp[L_THICK] * ((0.55f + 0.45f * bv) * (0.6f + 0.4f * (1.f - fabsf(v))) + rid);
                    height[p] = height[p] * (1 - aa) + th * aa;
                }
            } else {
                float rim = 1.f + lp[L_RIM] * smooth(1.f - lp[L_RIMW], 1.f, fabsf(v));
                float g = 1.f + bstr * (bv - 0.5f) * 0.3f;
                for (int c = 0; c < C; c++) canvas[p * C + c] += a * op * col[c] * rim * g;
            }
        }
    }
}

// 画一层。ref: 目标（已按这层笔的大小模糊过），canvas/height 原地修改。
// 若 out_pts 非空，记录每笔的控制点（[maxStrokes][maxPts][2]）、点数、颜色、半径，供导出 SVG。
// mode 2（水彩）时 ref 与 canvas 都是吸光度，误差只算"还差多少"（只能加深）。返回笔数。
int paint_layer(const float *ref, float *canvas, float *height, int H, int W, int C,
                const float *tx, const float *ty, const float *lp, int mode, uint64_t seed,
                int maxStrokes, int maxPts, float *out_pts, int *out_np, float *out_col, float *out_r) {
    uint64_t rs = seed * 7919 + 17;
    int grid = (int)lp[L_GRID];
    if (grid < 1) grid = 1;
    float T = lp[L_T], R0 = lp[L_R];
    int gx = (W + grid - 1) / grid, gy = (H + grid - 1) / grid, ncell = gx * gy;
    int *order = (int *)malloc(sizeof(int) * ncell);
    for (int i = 0; i < ncell; i++) order[i] = i;
    for (int i = ncell - 1; i > 0; i--) {
        int j = (int)(frand(&rs) * (i + 1));
        if (j > i) j = i;
        int t = order[i]; order[i] = order[j]; order[j] = t;
    }
    int ox = (int)(frand(&rs) * grid), oy = (int)(frand(&rs) * grid);
    Scratch S = {0};
    S.maxPoly = maxPts * 64 + 8;
    S.poly = (float *)malloc(sizeof(float) * 2 * S.maxPoly);
    S.cum = (float *)malloc(sizeof(float) * S.maxPoly);
    float *P = (float *)malloc(sizeof(float) * 2 * maxPts);
    float rv[8], cv[8], col[8];
    int n = 0;
    for (int ci = 0; ci < ncell; ci++) {
        int cx = order[ci] % gx, cy = order[ci] / gx;
        int x0 = cx * grid - ox, y0 = cy * grid - oy, x1 = x0 + grid, y1 = y0 + grid;
        if (x0 < 0) x0 = 0;
        if (y0 < 0) y0 = 0;
        if (x1 > W) x1 = W;
        if (y1 > H) y1 = H;
        if (x1 <= x0 || y1 <= y0) continue;
        double sum = 0;
        float best = -1;
        int bx = x0, by = y0;
        for (int y = y0; y < y1; y++)
            for (int x = x0; x < x1; x++) {
                size_t i = (size_t)y * W + x;
                float d;
                if (mode == 1) d = fmaxf(0.f, ref[i] - canvas[i]);
                else if (mode == 2) {
                    d = 0;
                    for (int c = 0; c < C; c++) d += fmaxf(0.f, ref[i * C + c] - canvas[i * C + c]);
                } else d = dist(ref + i * C, canvas + i * C, C);
                sum += d;
                if (d > best) { best = d; bx = x; by = y; }
            }
        if (sum / ((x1 - x0) * (y1 - y0)) <= T) continue;
        float px = bx + 0.5f, py = by + 0.5f;
        sample(ref, H, W, C, px, py, rv);
        sample(canvas, H, W, C, px, py, cv);
        if (mode == 1) {
            float k = 1.f - (1.f - rv[0]) / fmaxf(1e-3f, 1.f - cv[0]);
            if (k < 0.02f) continue;
            col[0] = clampf(k, 0.f, 1.f);
        } else if (mode == 2) {
            for (int c = 0; c < C; c++) col[c] = fmaxf(0.f, rv[c] - cv[c]);
        } else {
            for (int c = 0; c < C; c++) col[c] = rv[c];
        }
        int np = trace_one(ref, canvas, H, W, C, tx, ty, lp, mode, px, py, col, P, maxPts);
        if (np == 1 && maxPts > 1) {                     // 单点：顺着流场补成一小段短笔，避免圆点
            size_t i0 = (size_t)(int)clampf(py, 0, H - 1) * W + (int)clampf(px, 0, W - 1);
            float h2 = 0.35f * lp[L_STEP];
            P[0] = px - h2 * tx[i0]; P[1] = py - h2 * ty[i0];
            P[2] = px + h2 * tx[i0]; P[3] = py + h2 * ty[i0];
            np = 2;
        }
        float R = R0 * (lp[L_RJLO] + (lp[L_RJHI] - lp[L_RJLO]) * frand(&rs));
        float grad = lp[L_GRAD] * (2 * frand(&rs) - 1);
        float dry = frand(&rs) < lp[L_DRYP] ? lp[L_DRY] * (0.5f + frand(&rs)) : 0.f;
        float col2[8];
        {   // 第二种颜料：笔旁边（横向 1.5 个笔宽处）目标图的颜色
            size_t i0 = (size_t)(int)clampf(py, 0, H - 1) * W + (int)clampf(px, 0, W - 1);
            float sd = frand(&rs) < 0.5f ? -1.5f : 1.5f;
            float qx = px - sd * R * ty[i0], qy = py + sd * R * tx[i0];
            sample(ref, H, W, C, qx, qy, col2);
        }
        render_one(canvas, height, H, W, C, P, np, col, col2, R, grad, dry, lp, mode, &rs, &S);
        if (out_pts && n < maxStrokes) {
            memcpy(out_pts + (size_t)n * maxPts * 2, P, sizeof(float) * 2 * np);
            out_np[n] = np;
            for (int c = 0; c < C; c++) out_col[(size_t)n * C + c] = col[c];
            out_r[n] = R;
        }
        n++;
    }
    free(order); free(P); free(S.poly); free(S.cum); free(S.bd); free(S.bu); free(S.bs);
    return n;
}

// ======================= 低多边形：三角网优化 =======================
// 目标：每个三角形填它覆盖像素的平均色，和原图的平方误差之和最小。
// 行前缀和让每个三角形的误差按行 O(行数) 算出。像素归属：像素中心落在三角形内（左闭右开，与扫描线一致）。
typedef struct {
    int H, W;
    double *P;      // [H][W+1][4]：R、G、B、R²+G²+B² 的行前缀和
} Img;

static void img_build(Img *im, const float *rgb, int H, int W) {
    im->H = H; im->W = W;
    im->P = (double *)malloc(sizeof(double) * (size_t)H * (W + 1) * 4);
    for (int y = 0; y < H; y++) {
        double *row = im->P + (size_t)y * (W + 1) * 4;
        row[0] = row[1] = row[2] = row[3] = 0;
        for (int x = 0; x < W; x++) {
            const float *p = rgb + ((size_t)y * W + x) * 3;
            double *a = row + x * 4, *b = row + (x + 1) * 4;
            b[0] = a[0] + p[0]; b[1] = a[1] + p[1]; b[2] = a[2] + p[2];
            b[3] = a[3] + (double)p[0] * p[0] + (double)p[1] * p[1] + (double)p[2] * p[2];
        }
    }
}

// 三角形统计：像素数、颜色和、平方和。返回误差 S2 - |S1|²/n。
static double tri_err(const Img *im, const float *A, const float *B, const float *C, double *out_s /* 4 */, double *out_n) {
    float ys[3] = {A[1], B[1], C[1]};
    float ymin = fminf(ys[0], fminf(ys[1], ys[2])), ymax = fmaxf(ys[0], fmaxf(ys[1], ys[2]));
    int y0 = (int)ceilf(ymin - 0.5f), y1 = (int)floorf(ymax - 0.5f);
    if (y0 < 0) y0 = 0;
    if (y1 > im->H - 1) y1 = im->H - 1;
    double s0 = 0, s1 = 0, s2 = 0, s3 = 0, n = 0;
    const float *V[3] = {A, B, C};
    for (int y = y0; y <= y1; y++) {
        float yc = y + 0.5f, xl = 1e30f, xr = -1e30f;
        for (int e = 0; e < 3; e++) {
            const float *p = V[e], *q = V[(e + 1) % 3];
            float ya = p[1], yb = q[1];
            if ((yc >= ya && yc < yb) || (yc >= yb && yc < ya)) {
                float x = p[0] + (yc - ya) * (q[0] - p[0]) / (yb - ya);
                xl = fminf(xl, x); xr = fmaxf(xr, x);
            }
        }
        if (xr < xl) continue;
        int x0 = (int)ceilf(xl - 0.5f), x1 = (int)ceilf(xr - 0.5f);
        if (x0 < 0) x0 = 0;
        if (x1 > im->W) x1 = im->W;
        if (x1 <= x0) continue;
        const double *row = im->P + (size_t)y * (im->W + 1) * 4;
        const double *a = row + x0 * 4, *b = row + x1 * 4;
        s0 += b[0] - a[0]; s1 += b[1] - a[1]; s2 += b[2] - a[2]; s3 += b[3] - a[3];
        n += x1 - x0;
    }
    if (out_s) { out_s[0] = s0; out_s[1] = s1; out_s[2] = s2; out_s[3] = s3; }
    if (out_n) *out_n = n;
    if (n <= 0) return 0;
    return s3 - (s0 * s0 + s1 * s1 + s2 * s2) / n;
}

static inline float orient(const float *a, const float *b, const float *c) {
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

// 三角形形状是否合格：方向为正、面积够、最小角不小于阈值（用 cos 比较）。
static int tri_ok(const float *a, const float *b, const float *c, float minArea, float cosMax) {
    float o = orient(a, b, c);
    if (o < 2 * minArea) return 0;
    const float *V[3] = {a, b, c};
    for (int i = 0; i < 3; i++) {
        const float *p = V[i], *q = V[(i + 1) % 3], *r = V[(i + 2) % 3];
        float ux = q[0] - p[0], uy = q[1] - p[1], vx = r[0] - p[0], vy = r[1] - p[1];
        float d = ux * vx + uy * vy, l = sqrtf((ux * ux + uy * uy) * (vx * vx + vy * vy));
        if (l <= 0 || d / l > cosMax) return 0;
    }
    return 1;
}

// 边哈希表（开放寻址）：键 = (min,max) 顶点对，值 = 两侧三角形。
typedef struct { uint64_t *key; int *t0, *t1; size_t cap; } EMap;
#define EMPTY_KEY 0xFFFFFFFFFFFFFFFFULL
#define TOMB_KEY  0xFFFFFFFFFFFFFFFEULL
static inline uint64_t ekey(int a, int b) { return a < b ? ((uint64_t)a << 32) | (uint32_t)b : ((uint64_t)b << 32) | (uint32_t)a; }
static inline size_t ehash(uint64_t k, size_t cap) { k ^= k >> 33; k *= 0xff51afd7ed558ccdULL; k ^= k >> 33; return (size_t)(k & (cap - 1)); }
static size_t emap_find(EMap *m, uint64_t k, int insert) {
    size_t i = ehash(k, m->cap), tomb = (size_t)-1;
    for (;;) {
        if (m->key[i] == EMPTY_KEY) {
            if (!insert) return (size_t)-1;
            if (tomb != (size_t)-1) i = tomb;
            m->key[i] = k; m->t0[i] = -1; m->t1[i] = -1;
            return i;
        }
        if (m->key[i] == TOMB_KEY) { if (tomb == (size_t)-1) tomb = i; }
        else if (m->key[i] == k) return i;
        i = (i + 1) & (m->cap - 1);
    }
}
static void emap_add(EMap *m, int a, int b, int t) {
    size_t i = emap_find(m, ekey(a, b), 1);
    if (m->t0[i] < 0) m->t0[i] = t; else m->t1[i] = t;
}
static void emap_replace(EMap *m, int a, int b, int told, int tnew) {
    size_t i = emap_find(m, ekey(a, b), 0);
    if (i == (size_t)-1) return;
    if (m->t0[i] == told) m->t0[i] = tnew; else if (m->t1[i] == told) m->t1[i] = tnew;
}

// 三角网优化。verts [nv][2]（原地修改），flags：0 自由，1 只能沿 y 动（左右边界），2 只能沿 x 动（上下边界），3 固定。
// tris [nt][3]（逆时针，原地修改，翻边会改连接关系）。每轮：顶点爬山一遍 + 按误差翻边一遍。
// out_err [nt]：结束时每个三角形的误差。返回总误差。
double mesh_optimize(const float *rgb, int H, int W, float *verts, int nv, const int *flags, int *tris, int nt,
                     int iters, float step0, float step_min, float minAngleDeg, float minArea, uint64_t seed,
                     int do_flip, double *out_err) {
    Img im;
    img_build(&im, rgb, H, W);
    uint64_t rs = seed * 911 + 5;
    float cosMax = cosf(minAngleDeg * (float)M_PI / 180.f);
    double *err = (double *)malloc(sizeof(double) * nt);
    for (int t = 0; t < nt; t++)
        err[t] = tri_err(&im, verts + 2 * tris[3 * t], verts + 2 * tris[3 * t + 1], verts + 2 * tris[3 * t + 2], NULL, NULL);
    int *deg = (int *)malloc(sizeof(int) * (nv + 1));
    int *inc = (int *)malloc(sizeof(int) * 3 * nt);
    int *order = (int *)malloc(sizeof(int) * nv);
    EMap m;
    m.cap = 1;
    while (m.cap < (size_t)nt * 4) m.cap <<= 1;
    m.key = (uint64_t *)malloc(sizeof(uint64_t) * m.cap);
    m.t0 = (int *)malloc(sizeof(int) * m.cap);
    m.t1 = (int *)malloc(sizeof(int) * m.cap);
    static const float DIRS[8][2] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}, {0.7071f, 0.7071f}, {-0.7071f, 0.7071f}, {0.7071f, -0.7071f}, {-0.7071f, -0.7071f}};
    float step = step0;
    for (int it = 0; it < iters; it++) {
        // 顶点 → 三角形（CSR）
        memset(deg, 0, sizeof(int) * (nv + 1));
        for (int t = 0; t < 3 * nt; t++) deg[tris[t] + 1]++;
        for (int v = 0; v < nv; v++) deg[v + 1] += deg[v];
        int *fill = (int *)malloc(sizeof(int) * nv);
        memcpy(fill, deg, sizeof(int) * nv);
        for (int t = 0; t < nt; t++)
            for (int k = 0; k < 3; k++) inc[fill[tris[3 * t + k]]++] = t;
        free(fill);
        for (int v = 0; v < nv; v++) order[v] = v;
        for (int i = nv - 1; i > 0; i--) {
            int j = (int)(frand(&rs) * (i + 1)); if (j > i) j = i;
            int tmp = order[i]; order[i] = order[j]; order[j] = tmp;
        }
        // 顶点爬山
        for (int oi = 0; oi < nv; oi++) {
            int v = order[oi];
            if (flags[v] == 3) continue;
            float ox = verts[2 * v], oy = verts[2 * v + 1];
            double eold = 0;
            for (int k = deg[v]; k < deg[v + 1]; k++) eold += err[inc[k]];
            double best = -1e-9;
            float bx = ox, by = oy;
            for (int d = 0; d < 8; d++) {
                float nx = ox + step * DIRS[d][0], ny = oy + step * DIRS[d][1];
                if (flags[v] == 1) nx = ox;
                if (flags[v] == 2) ny = oy;
                if (nx == ox && ny == oy) continue;
                if (nx < 0 || ny < 0 || nx > W || ny > H) continue;
                verts[2 * v] = nx; verts[2 * v + 1] = ny;
                double enew = 0;
                int ok = 1;
                for (int k = deg[v]; k < deg[v + 1] && ok; k++) {
                    int t = inc[k];
                    const float *a = verts + 2 * tris[3 * t], *b = verts + 2 * tris[3 * t + 1], *c = verts + 2 * tris[3 * t + 2];
                    if (!tri_ok(a, b, c, minArea, cosMax)) ok = 0;
                    else enew += tri_err(&im, a, b, c, NULL, NULL);
                }
                verts[2 * v] = ox; verts[2 * v + 1] = oy;
                if (ok && enew - eold < best) { best = enew - eold; bx = nx; by = ny; }
            }
            if (bx != ox || by != oy) {
                verts[2 * v] = bx; verts[2 * v + 1] = by;
                for (int k = deg[v]; k < deg[v + 1]; k++) {
                    int t = inc[k];
                    err[t] = tri_err(&im, verts + 2 * tris[3 * t], verts + 2 * tris[3 * t + 1], verts + 2 * tris[3 * t + 2], NULL, NULL);
                }
            }
        }
        // 按误差翻边
        if (do_flip) {
            for (size_t i = 0; i < m.cap; i++) m.key[i] = EMPTY_KEY;
            for (int t = 0; t < nt; t++)
                for (int k = 0; k < 3; k++) emap_add(&m, tris[3 * t + k], tris[3 * t + (k + 1) % 3], t);
            for (size_t i = 0; i < m.cap; i++) {
                if (m.key[i] == EMPTY_KEY || m.key[i] == TOMB_KEY) continue;
                int t1 = m.t0[i], t2 = m.t1[i];
                if (t1 < 0 || t2 < 0) continue;
                int ea = (int)(m.key[i] >> 32), eb = (int)(m.key[i] & 0xffffffffu);
                // 在 t1 里找出 a→b 的方向和对顶点 c
                int *T1 = tris + 3 * t1, *T2 = tris + 3 * t2;
                int a = -1, b = -1, c = -1, dd = -1;
                for (int k = 0; k < 3; k++) {
                    int p = T1[k], q = T1[(k + 1) % 3];
                    if ((p == ea && q == eb) || (p == eb && q == ea)) { a = p; b = q; c = T1[(k + 2) % 3]; }
                }
                for (int k = 0; k < 3; k++) if (T2[k] != ea && T2[k] != eb) dd = T2[k];
                if (a < 0 || dd < 0) continue;
                const float *pa = verts + 2 * a, *pb = verts + 2 * b, *pc = verts + 2 * c, *pd = verts + 2 * dd;
                if (!tri_ok(pc, pa, pd, minArea, cosMax) || !tri_ok(pd, pb, pc, minArea, cosMax)) continue;
                double e1 = tri_err(&im, pc, pa, pd, NULL, NULL), e2 = tri_err(&im, pd, pb, pc, NULL, NULL);
                if (e1 + e2 >= err[t1] + err[t2] - 1e-6) continue;
                T1[0] = c; T1[1] = a; T1[2] = dd;
                T2[0] = dd; T2[1] = b; T2[2] = c;
                err[t1] = e1; err[t2] = e2;
                emap_replace(&m, a, dd, t2, t1);
                emap_replace(&m, b, c, t1, t2);
                m.key[i] = TOMB_KEY;
                size_t j = emap_find(&m, ekey(c, dd), 1);
                m.t0[j] = t1; m.t1[j] = t2;
            }
        }
        step = fmaxf(step_min, step * 0.75f);
    }
    double total = 0;
    for (int t = 0; t < nt; t++) { total += err[t]; if (out_err) out_err[t] = err[t]; }
    free(err); free(deg); free(inc); free(order); free(m.key); free(m.t0); free(m.t1); free(im.P);
    return total;
}

// 每个三角形的平均色（像素中心归属，与优化一致）。
void mesh_colors(const float *rgb, int H, int W, const float *verts, const int *tris, int nt, float *out_col, float *out_n) {
    Img im;
    img_build(&im, rgb, H, W);
    double s[4], n;
    for (int t = 0; t < nt; t++) {
        tri_err(&im, verts + 2 * tris[3 * t], verts + 2 * tris[3 * t + 1], verts + 2 * tris[3 * t + 2], s, &n);
        for (int c = 0; c < 3; c++) out_col[3 * t + c] = n > 0 ? (float)(s[c] / n) : 0.f;
        out_n[t] = (float)n;
    }
    free(im.P);
}

// ======================= 各向异性 Kuwahara 滤波 =======================
// Kyprianidis et al. 2011（多项式扇区权重，8 个扇区）。img/out: (H, W, 3)。
// phi: 每个像素的主方向（弧度，边缘的切向），A: 各向异性 0..1。radius: 半径（像素），q: 锐度，alpha: 椭圆拉伸程度。
void akf(const float *img, float *out, int H, int W, const float *phi, const float *Aniso,
         float radius, float q, float alpha, float zeta) {
    const int N = 8;
    const float eta = (zeta + cosf((float)M_PI / N)) / (sinf((float)M_PI / N) * sinf((float)M_PI / N));
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            size_t p = (size_t)y * W + x;
            float m[8][4], s[8][3];
            memset(m, 0, sizeof(m)); memset(s, 0, sizeof(s));
            float an = Aniso[p];
            float a = radius * clampf((alpha + an) / alpha, 0.1f, 2.f);
            float b = radius * clampf(alpha / (alpha + an), 0.1f, 2.f);
            float cp = cosf(phi[p]), sp = sinf(phi[p]);
            // SR = S * R(-phi)：把偏移量转到椭圆坐标并归一到半径 0.5 的圆
            float r00 = 0.5f / a * cp, r01 = 0.5f / a * sp, r10 = -0.5f / b * sp, r11 = 0.5f / b * cp;
            int mx = (int)sqrtf(a * a * cp * cp + b * b * sp * sp), my = (int)sqrtf(a * a * sp * sp + b * b * cp * cp);
            const float *c00 = img + p * 3;
            for (int k = 0; k < N; k++) {                     // 中心像素本身给每个扇区一点权重
                for (int c = 0; c < 3; c++) { m[k][c] += c00[c] * 0.125f; s[k][c] += c00[c] * c00[c] * 0.125f; }
                m[k][3] += 0.125f;
            }
            for (int j = 0; j <= my; j++) {
                for (int i = -mx; i <= mx; i++) {
                    if (j == 0 && i <= 0) continue;
                    float vx = r00 * i + r01 * j, vy = r10 * i + r11 * j;
                    float dv = vx * vx + vy * vy;
                    if (dv > 0.25f) continue;
                    int x0 = x + i, y0 = y + j, x1 = x - i, y1 = y - j;
                    x0 = x0 < 0 ? 0 : (x0 >= W ? W - 1 : x0); y0 = y0 < 0 ? 0 : (y0 >= H ? H - 1 : y0);
                    x1 = x1 < 0 ? 0 : (x1 >= W ? W - 1 : x1); y1 = y1 < 0 ? 0 : (y1 >= H ? H - 1 : y1);
                    const float *ca = img + ((size_t)y0 * W + x0) * 3, *cb = img + ((size_t)y1 * W + x1) * 3;
                    float w[8], sum = 0, z, vxx, vyy;
                    vxx = zeta - eta * vx * vx; vyy = zeta - eta * vy * vy;
                    z = fmaxf(0, vy + vxx); w[0] = z * z; sum += w[0];
                    z = fmaxf(0, -vx + vyy); w[2] = z * z; sum += w[2];
                    z = fmaxf(0, -vy + vxx); w[4] = z * z; sum += w[4];
                    z = fmaxf(0, vx + vyy); w[6] = z * z; sum += w[6];
                    float ux = 0.70710678f * (vx - vy), uy = 0.70710678f * (vx + vy);
                    vxx = zeta - eta * ux * ux; vyy = zeta - eta * uy * uy;
                    z = fmaxf(0, uy + vxx); w[1] = z * z; sum += w[1];
                    z = fmaxf(0, -ux + vyy); w[3] = z * z; sum += w[3];
                    z = fmaxf(0, -uy + vxx); w[5] = z * z; sum += w[5];
                    z = fmaxf(0, ux + vyy); w[7] = z * z; sum += w[7];
                    if (sum <= 0) continue;
                    float g = expf(-3.125f * dv) / sum;
                    for (int k = 0; k < N; k++) {
                        float wk = w[k] * g;
                        int k2 = (k + 4) & 7;
                        for (int c = 0; c < 3; c++) {
                            m[k][c] += ca[c] * wk; s[k][c] += ca[c] * ca[c] * wk;
                            m[k2][c] += cb[c] * wk; s[k2][c] += cb[c] * cb[c] * wk;
                        }
                        m[k][3] += wk; m[k2][3] += wk;
                    }
                }
            }
            float o[3] = {0, 0, 0}, ow = 0;
            for (int k = 0; k < N; k++) {
                float mw = m[k][3], sig = 0, mc[3];
                for (int c = 0; c < 3; c++) {
                    mc[c] = m[k][c] / mw;
                    sig += fabsf(s[k][c] / mw - mc[c] * mc[c]);
                }
                float wk = 1.f / (1.f + powf(1000.f * sig, 0.5f * q));
                for (int c = 0; c < 3; c++) o[c] += mc[c] * wk;
                ow += wk;
            }
            for (int c = 0; c < 3; c++) out[p * 3 + c] = o[c] / ow;
        }
    }
}

// ======================= L0 梯度最小化的一步 =======================
// S: (H, W, C)。前向差分 h、v（循环边界），|∇S|² < thr 的像素把梯度置零，输出散度 div = (h(x-1)-h(x)) + (v(y-1)-v(y))。
// hb、vb 是调用方给的临时缓冲（各 H*W*C 个 float）。
void l0_step(const float *S, float *div, float *hb, float *vb, int H, int W, int C, float thr) {
    for (int y = 0; y < H; y++) {
        int yn = y + 1 == H ? 0 : y + 1;
        for (int x = 0; x < W; x++) {
            int xn = x + 1 == W ? 0 : x + 1;
            size_t p = ((size_t)y * W + x) * C, pr = ((size_t)y * W + xn) * C, pd = ((size_t)yn * W + x) * C;
            float g = 0;
            for (int c = 0; c < C; c++) {
                float h = S[pr + c] - S[p + c], v = S[pd + c] - S[p + c];
                hb[p + c] = h; vb[p + c] = v;
                g += h * h + v * v;
            }
            if (g < thr)
                for (int c = 0; c < C; c++) { hb[p + c] = 0; vb[p + c] = 0; }
        }
    }
    for (int y = 0; y < H; y++) {
        int yp = y == 0 ? H - 1 : y - 1;
        for (int x = 0; x < W; x++) {
            int xp = x == 0 ? W - 1 : x - 1;
            size_t p = ((size_t)y * W + x) * C, pl = ((size_t)y * W + xp) * C, pu = ((size_t)yp * W + x) * C;
            for (int c = 0; c < C; c++) div[p + c] = (hb[pl + c] - hb[p + c]) + (vb[pu + c] - vb[p + c]);
        }
    }
}

// ======================= 区域划分（精细量化连通块 + 区域邻接图合并） =======================
static int uf_find(int *p, int x) {
    while (p[x] != x) { p[x] = p[p[x]]; x = p[x]; }
    return x;
}
typedef struct { float d; int a, b; } Pair;
static int pair_cmp(const void *u, const void *v) {
    float a = ((const Pair *)u)->d, b = ((const Pair *)v)->d;
    return a < b ? -1 : (a > b ? 1 : 0);
}
static int u64_cmp(const void *u, const void *v) {
    uint64_t a = *(const uint64_t *)u, b = *(const uint64_t *)v;
    return a < b ? -1 : (a > b ? 1 : 0);
}
// lab: (H, W, 3)。先按 qstep 量化后同色的 4 邻域连通块切小块，再在区域邻接图上按初始色差从小到大合并：
// 合并后两块的平均色差 ≤ de，或者其中一块面积 < min_area，就并（大块吃小块）。labels 输出 0..n-1，返回 n。
int regions_c(const float *lab, int H, int W, float qstep, float de, int min_area, int *labels) {
    int N = H * W;
    int *q = (int *)malloc(sizeof(int) * N * 3), *par = (int *)malloc(sizeof(int) * N);
    for (int i = 0; i < N; i++) {
        for (int c = 0; c < 3; c++) q[3 * i + c] = (int)lrintf(lab[3 * i + c] / qstep);
        par[i] = i;
    }
    #define SAMEQ(i, j) (q[3 * (i)] == q[3 * (j)] && q[3 * (i) + 1] == q[3 * (j) + 1] && q[3 * (i) + 2] == q[3 * (j) + 2])
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int i = y * W + x;
            if (x + 1 < W && SAMEQ(i, i + 1)) { int a = uf_find(par, i), b = uf_find(par, i + 1); if (a != b) par[b] = a; }
            if (y + 1 < H && SAMEQ(i, i + W)) { int a = uf_find(par, i), b = uf_find(par, i + W); if (a != b) par[b] = a; }
        }
    #undef SAMEQ
    int *rid = (int *)malloc(sizeof(int) * N), *comp = (int *)malloc(sizeof(int) * N);
    for (int i = 0; i < N; i++) rid[i] = -1;
    int nc = 0;
    for (int i = 0; i < N; i++) {
        int r = uf_find(par, i);
        if (rid[r] < 0) rid[r] = nc++;
        comp[i] = rid[r];
    }
    double *area = (double *)calloc(nc, sizeof(double)), *sum = (double *)calloc((size_t)nc * 3, sizeof(double));
    for (int i = 0; i < N; i++) {
        area[comp[i]] += 1;
        for (int c = 0; c < 3; c++) sum[3 * (size_t)comp[i] + c] += lab[3 * (size_t)i + c];
    }
    // 邻接对（去重）
    size_t np_ = 0, cap = 1 << 16;
    uint64_t *keys = (uint64_t *)malloc(sizeof(uint64_t) * cap);
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            int i = y * W + x, nb[2] = {x + 1 < W ? i + 1 : -1, y + 1 < H ? i + W : -1};
            for (int k = 0; k < 2; k++) {
                if (nb[k] < 0) continue;
                int a = comp[i], b = comp[nb[k]];
                if (a == b) continue;
                if (a > b) { int t = a; a = b; b = t; }
                if (np_ == cap) { cap *= 2; keys = (uint64_t *)realloc(keys, sizeof(uint64_t) * cap); }
                keys[np_++] = ((uint64_t)a << 32) | (uint32_t)b;
            }
        }
    qsort(keys, np_, sizeof(uint64_t), u64_cmp);
    size_t nu = 0;
    for (size_t i = 0; i < np_; i++) if (i == 0 || keys[i] != keys[i - 1]) keys[nu++] = keys[i];
    Pair *pairs = (Pair *)malloc(sizeof(Pair) * (nu ? nu : 1));
    for (size_t i = 0; i < nu; i++) {
        int a = (int)(keys[i] >> 32), b = (int)(keys[i] & 0xffffffffu);
        double d2 = 0;
        for (int c = 0; c < 3; c++) {
            double t = sum[3 * (size_t)a + c] / area[a] - sum[3 * (size_t)b + c] / area[b];
            d2 += t * t;
        }
        pairs[i].d = (float)sqrt(d2); pairs[i].a = a; pairs[i].b = b;
    }
    qsort(pairs, nu, sizeof(Pair), pair_cmp);
    int *uf = (int *)malloc(sizeof(int) * nc);
    for (int i = 0; i < nc; i++) uf[i] = i;
    for (size_t i = 0; i < nu; i++) {
        int ra = uf_find(uf, pairs[i].a), rb = uf_find(uf, pairs[i].b);
        if (ra == rb) continue;
        double d2 = 0;
        for (int c = 0; c < 3; c++) {
            double t = sum[3 * (size_t)ra + c] / area[ra] - sum[3 * (size_t)rb + c] / area[rb];
            d2 += t * t;
        }
        int small = (area[ra] < area[rb] ? area[ra] : area[rb]) < min_area;
        if (sqrt(d2) <= de || small) {
            if (area[ra] < area[rb]) { int t = ra; ra = rb; rb = t; }
            uf[rb] = ra;
            for (int c = 0; c < 3; c++) sum[3 * (size_t)ra + c] += sum[3 * (size_t)rb + c];
            area[ra] += area[rb];
        }
    }
    int *fid = (int *)malloc(sizeof(int) * nc);
    for (int i = 0; i < nc; i++) fid[i] = -1;
    int n = 0;
    for (int i = 0; i < N; i++) {
        int r = uf_find(uf, comp[i]);
        if (fid[r] < 0) fid[r] = n++;
        labels[i] = fid[r];
    }
    free(q); free(par); free(rid); free(comp); free(area); free(sum); free(keys); free(pairs); free(uf); free(fid);
    return n;
}

// ======================= 线积分卷积（LIC）与沿法向的 DoG =======================
static inline float bilin(const float *img, int H, int W, float x, float y) {
    x = clampf(x, 0, W - 1.001f);
    y = clampf(y, 0, H - 1.001f);
    int x0 = (int)x, y0 = (int)y;
    float fx = x - x0, fy = y - y0;
    const float *p = img + (size_t)y0 * W + x0;
    return (p[0] * (1 - fx) + p[1] * fx) * (1 - fy) + (p[W] * (1 - fx) + p[W + 1] * fx) * fy;
}

// 沿流场 (tx, ty) 双向各走 length 步（步长 step），高斯加权（sigma）平均 src。像素中心在整数坐标。
void lic_c(const float *src, const float *tx, const float *ty, int H, int W, int length, float step, float sigma,
           float *out) {
    float *wt = (float *)malloc(sizeof(float) * (length + 1));
    for (int i = 0; i <= length; i++) wt[i] = expf(-0.5f * (i * step / sigma) * (i * step / sigma));
    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            size_t p = (size_t)y * W + x;
            float acc = src[p], ws = 1;
            for (int sg = 0; sg < 2; sg++) {
                float px = x, py = y, vx = sg ? -tx[p] : tx[p], vy = sg ? -ty[p] : ty[p];
                for (int i = 1; i <= length; i++) {
                    int ix = (int)lrintf(px), iy = (int)lrintf(py);
                    ix = ix < 0 ? 0 : (ix >= W ? W - 1 : ix);
                    iy = iy < 0 ? 0 : (iy >= H ? H - 1 : iy);
                    float dx = tx[(size_t)iy * W + ix], dy = ty[(size_t)iy * W + ix];
                    if (dx * vx + dy * vy < 0) { dx = -dx; dy = -dy; }
                    px += dx * step; py += dy * step;
                    vx = dx; vy = dy;
                    acc += wt[i] * bilin(src, H, W, px, py);
                    ws += wt[i];
                }
            }
            out[p] = acc / ws;
        }
    }
    free(wt);
}

// 沿 (nx, ny) 方向的一维加权和：out = Σ_t wts[t+T] · L(p + t·n)，t = -T..T（流线 DoG 的第一步）。
void dog_line(const float *L, const float *nx, const float *ny, int H, int W, int T, const float *wts, float *out) {
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
            size_t p = (size_t)y * W + x;
            float acc = 0;
            for (int t = -T; t <= T; t++) acc += wts[t + T] * bilin(L, H, W, x + t * nx[p], y + t * ny[p]);
            out[p] = acc;
        }
}

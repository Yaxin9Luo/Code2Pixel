/* primitive 式三角形拟合的内核（覆盖率版）：光栅化、最优颜色、误差变化、随机候选 + 爬山、回拟合。
 * 由 solver.py 通过 ctypes 调用，首次运行时自动编译：cc -O3 -shared -fPIC -o core.so core.c
 * 调用期间 ctypes 会释放 GIL，所以 Python 端可以用线程并行处理互不重叠的块。
 *
 * 渲染模型和浏览器的抗锯齿一致：每个像素按被三角形覆盖的面积比例 cov 混合，
 * C <- C + a*cov*(col - C)。面积用每行 4 条子扫描线、每条精确计算横向重叠来近似。
 * 完全覆盖的内部像素（cov=1）用行前缀和一次求和，边缘像素逐个计算。
 */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define QSTEP 4.0 /* 颜色量化步长（0–255 刻度），越大越好压缩、颜色越粗 */
#define SUB 4     /* 每个像素行的子扫描线数 */

/* 误差加权：每像素误差 = sum_ch d^2 + g_lw * (Y·d)^2，Y 为亮度系数。 */
static double g_lw = 0.0;
static const double LY[3] = {0.299, 0.587, 0.114};
void set_lweight(double lw) { g_lw = lw; }
static inline double pix_err(double d0, double d1, double d2) {
    double y = LY[0] * d0 + LY[1] * d1 + LY[2] * d2;
    return d0 * d0 + d1 * d1 + d2 * d2 + g_lw * y * y;
}
static inline double quant(double v) {
    v = v < 0 ? 0 : (v > 1 ? 1 : v);
    double q = nearbyint(v * 255 / QSTEP) * QSTEP;
    return (q > 255 ? 255 : q) / 255;  /* 255 按步长 4 会舍入成 256，写成十六进制就不合法（浏览器画成黑色） */
}

typedef struct {
    int W, H;
    const float *T; /* H*W*3 目标图 */
    float *C;       /* H*W*3 当前画布 */
    float *E;       /* H*W   每像素误差 */
} Img;

/* ---------- 随机数（xoshiro256**） ---------- */
typedef struct { uint64_t s[4]; } Rng;
static inline uint64_t rotl(uint64_t x, int k) { return (x << k) | (x >> (64 - k)); }
static uint64_t rng_next(Rng *r) {
    uint64_t *s = r->s;
    uint64_t res = rotl(s[1] * 5, 7) * 9, t = s[1] << 17;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t; s[3] = rotl(s[3], 45);
    return res;
}
static double urand(Rng *r) { return (rng_next(r) >> 11) * 0x1.0p-53; }
static double nrand(Rng *r) {
    double u1 = urand(r), u2 = urand(r);
    if (u1 < 1e-300) u1 = 1e-300;
    return sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2);
}
static void rng_seed(Rng *r, uint64_t seed) {
    uint64_t z = seed;
    for (int i = 0; i < 4; i++) {
        z += 0x9e3779b97f4a7c15ULL;
        uint64_t x = z;
        x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
        x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
        r->s[i] = x ^ (x >> 31);
    }
}
static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}
static int cmp_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

/* ---------- 覆盖率光栅化 ---------- */
/* 三角形碰到的像素行 [i0, i1] */
static int tri_rows(const double *p, int H, int *i0, int *i1) {
    double area = (p[2] - p[0]) * (p[5] - p[1]) - (p[4] - p[0]) * (p[3] - p[1]);
    if (area == 0) return 0;
    double ymin = fmin(p[1], fmin(p[3], p[5])), ymax = fmax(p[1], fmax(p[3], p[5]));
    *i0 = (int)floor(ymin);
    if (*i0 < 0) *i0 = 0;
    *i1 = (int)ceil(ymax) - 1;
    if (*i1 > H - 1) *i1 = H - 1;
    return *i1 >= *i0;
}

/* 高度 y 处三角形的横向区间（连续值） */
static int span_at(const double *p, double y, double *lo, double *hi) {
    double l = 1e300, h = -1e300;
    int hit = 0;
    for (int k = 0; k < 3; k++) {
        double xa = p[2 * k], ya = p[2 * k + 1], xb = p[(2 * k + 2) % 6], yb = p[(2 * k + 3) % 6];
        if ((y >= ya && y <= yb) || (y >= yb && y <= ya)) {
            if (ya == yb) {
                l = fmin(l, fmin(xa, xb));
                h = fmax(h, fmax(xa, xb));
            } else {
                double xi = xa + (y - ya) / (yb - ya) * (xb - xa);
                l = fmin(l, xi);
                h = fmax(h, xi);
            }
            hit = 1;
        }
    }
    *lo = l;
    *hi = h;
    return hit && h > l;
}

/* 第 i 行在 [xlo, xhi) 内的覆盖：完全覆盖段 [*a0, *a1]（*a0 > *a1 表示没有），
 * 部分覆盖的像素（列号、覆盖率）写入 bj/bc，个数写入 *nb。bj/bc 至少要有 xhi-xlo 的容量。 */
static int row_cov(const double *p, int i, int xlo, int xhi, int *a0, int *a1, int *nb, int *bj, float *bc) {
    double xl[SUB], xr[SUB];
    int ok[SUB], all = 1, any = 0;
    double mnl = 1e300, mxl = -1e300, mnr = 1e300, mxr = -1e300;
    for (int s = 0; s < SUB; s++) {
        ok[s] = span_at(p, i + (s + 0.5) / SUB, &xl[s], &xr[s]);
        if (ok[s]) {
            any = 1;
            mnl = fmin(mnl, xl[s]);
            mxl = fmax(mxl, xl[s]);
            mnr = fmin(mnr, xr[s]);
            mxr = fmax(mxr, xr[s]);
        } else {
            all = 0;
        }
    }
    *nb = 0;
    *a0 = 1;
    *a1 = 0;
    if (!any) return 0;
    if (all) {
        int c0 = (int)ceil(mxl), c1 = (int)floor(mnr) - 1;
        if (c0 < xlo) c0 = xlo;
        if (c1 > xhi - 1) c1 = xhi - 1;
        if (c1 >= c0) {
            *a0 = c0;
            *a1 = c1;
        }
    }
    int b0 = (int)floor(mnl), b1 = (int)ceil(mxr) - 1;
    if (b0 < xlo) b0 = xlo;
    if (b1 > xhi - 1) b1 = xhi - 1;
    for (int j = b0; j <= b1; j++) {
        if (*a1 >= *a0 && j == *a0) {
            j = *a1;
            continue;
        }
        double cv = 0;
        for (int s = 0; s < SUB; s++)
            if (ok[s]) {
                double o = fmin(j + 1.0, xr[s]) - fmax((double)j, xl[s]);
                if (o > 0) cv += o;
            }
        cv /= SUB;
        if (cv > 1e-9) {
            bj[*nb] = j;
            bc[*nb] = (float)(cv > 1 ? 1 : cv);
            (*nb)++;
        }
    }
    return (*a1 >= *a0) || *nb > 0;
}

/* ---------- 评估 ----------
 * 设像素的混合比例 al = a*cov，u = T - (1-al)C，则
 * sum |T - new|_Q^2 = sum |u|_Q^2 - 2 sum al (col·u + lw (Y·col)(Y·u)) + sum al^2 (|col|^2 + lw (Y·col)^2)，
 * 最优颜色 col = sum al u / sum al^2。需要的累加量都是逐像素相加的。 */
typedef struct {
    double sau[3], sa2, suu, sayu, se;
    long n;
} Acc;

static inline void acc_pixel(const Img *im, size_t q, double al, Acc *A) {
    double yu = 0, uu = 0;
    for (int ch = 0; ch < 3; ch++) {
        double u = im->T[3 * q + ch] - (1 - al) * im->C[3 * q + ch];
        A->sau[ch] += al * u;
        uu += u * u;
        yu += LY[ch] * u;
    }
    A->sa2 += al * al;
    A->suu += uu + g_lw * yu * yu;
    A->sayu += al * yu;
    A->se += im->E[q];
    A->n++;
}

static double acc_eval(const Acc *A, float *col) {
    if (A->n <= 0 || A->sa2 < 1e-12) return 1e300;
    double ycol = 0, cdot = 0, cc = 0;
    for (int ch = 0; ch < 3; ch++) {
        double v = quant(A->sau[ch] / A->sa2);
        col[ch] = (float)v;
        ycol += LY[ch] * v;
        cdot += v * A->sau[ch];
        cc += v * v;
    }
    return A->suu - 2 * (cdot + g_lw * ycol * A->sayu) + A->sa2 * (cc + g_lw * ycol * ycol) - A->se;
}

/* 行前缀和：对混合比例为 a（完全覆盖）时每个像素的 6 个量（u 的三个通道、|u|_Q^2、Y·u、原误差）按行累加。 */
#define NQ 6
typedef struct {
    int xlo, w, H;
    double a;
    double *S; /* S[(i*(w+1) + j)*NQ + k] */
} Pref;

static void pref_row(const Img *im, Pref *P, int i, int from) {
    double *row = P->S + (size_t)i * (P->w + 1) * NQ;
    if (from <= 0) {
        from = 0;
        memset(row, 0, NQ * sizeof(double));
    }
    double acc[NQ];
    memcpy(acc, row + (size_t)from * NQ, sizeof acc);
    size_t base = (size_t)i * im->W + P->xlo;
    const float *t = im->T + base * 3, *c = im->C + base * 3, *e = im->E + base;
    double b = 1 - P->a;
    for (int j = from; j < P->w; j++) {
        double yu = 0, uu = 0;
        for (int ch = 0; ch < 3; ch++) {
            double u = t[3 * j + ch] - b * c[3 * j + ch];
            acc[ch] += u;
            uu += u * u;
            yu += LY[ch] * u;
        }
        acc[3] += uu + g_lw * yu * yu;
        acc[4] += yu;
        acc[5] += e[j];
        memcpy(row + (size_t)(j + 1) * NQ, acc, sizeof acc);
    }
}

void *pref_new(const Img *im, int xlo, int xhi, double a) {
    Pref *P = malloc(sizeof(Pref));
    P->xlo = xlo;
    P->w = xhi - xlo;
    P->H = im->H;
    P->a = a;
    P->S = malloc(sizeof(double) * (size_t)im->H * (P->w + 1) * NQ);
    for (int i = 0; i < im->H; i++) pref_row(im, P, i, 0);
    return P;
}

void pref_free(void *h) {
    Pref *P = h;
    free(P->S);
    free(P);
}

/* 三角形 p 的累加量：内部像素查前缀和，边缘像素逐个算。bj/bc 为调用方提供的缓冲区。 */
static void tri_acc(const Img *im, const Pref *P, int xlo, int xhi, const double *p, double a, int *bj, float *bc,
                    Acc *A) {
    memset(A, 0, sizeof *A);
    int i0, i1;
    if (!tri_rows(p, im->H, &i0, &i1)) return;
    for (int i = i0; i <= i1; i++) {
        int a0, a1, nb;
        if (!row_cov(p, i, xlo, xhi, &a0, &a1, &nb, bj, bc)) continue;
        if (a1 >= a0) {
            if (P) {
                const double *row = P->S + (size_t)i * (P->w + 1) * NQ;
                const double *hi = row + (size_t)(a1 - P->xlo + 1) * NQ, *lo = row + (size_t)(a0 - P->xlo) * NQ;
                for (int ch = 0; ch < 3; ch++) A->sau[ch] += a * (hi[ch] - lo[ch]);
                A->suu += hi[3] - lo[3];
                A->sayu += a * (hi[4] - lo[4]);
                A->se += hi[5] - lo[5];
                A->sa2 += a * a * (a1 - a0 + 1);
                A->n += a1 - a0 + 1;
            } else {
                for (int j = a0; j <= a1; j++) acc_pixel(im, (size_t)i * im->W + j, a, A);
            }
        }
        for (int k = 0; k < nb; k++) acc_pixel(im, (size_t)i * im->W + bj[k], a * bc[k], A);
    }
}

/* 返回画上这个三角形后总误差的变化量（负数表示变好），col 为最优颜色（量化），npix 为覆盖到的像素数。 */
double eval_tri(const Img *im, int xlo, int xhi, const double *p, double a, float *col, long *npix) {
    int *bj = malloc(sizeof(int) * (xhi - xlo + 2));
    float *bc = malloc(sizeof(float) * (xhi - xlo + 2));
    Acc A;
    tri_acc(im, NULL, xlo, xhi, p, a, bj, bc, &A);
    free(bj);
    free(bc);
    *npix = A.n;
    if (A.n == 0) return 0;
    return acc_eval(&A, col);
}

static inline void paint_pixel(Img *im, size_t q, double al, const float *col) {
    for (int ch = 0; ch < 3; ch++) im->C[3 * q + ch] = (float)((1 - al) * im->C[3 * q + ch] + al * col[ch]);
    im->E[q] = (float)pix_err(im->T[3 * q] - im->C[3 * q], im->T[3 * q + 1] - im->C[3 * q + 1],
                              im->T[3 * q + 2] - im->C[3 * q + 2]);
}

/* 落笔；若给了前缀和 P，同时重建受影响的行。 */
static void apply_tri_pref(Img *im, Pref *P, int xlo, int xhi, const double *p, double a, const float *col, int *bj,
                           float *bc) {
    int i0, i1;
    if (!tri_rows(p, im->H, &i0, &i1)) return;
    for (int i = i0; i <= i1; i++) {
        int a0, a1, nb;
        if (!row_cov(p, i, xlo, xhi, &a0, &a1, &nb, bj, bc)) continue;
        int first = xhi;
        if (a1 >= a0) {
            for (int j = a0; j <= a1; j++) paint_pixel(im, (size_t)i * im->W + j, a, col);
            first = a0;
        }
        for (int k = 0; k < nb; k++) {
            paint_pixel(im, (size_t)i * im->W + bj[k], a * bc[k], col);
            if (bj[k] < first) first = bj[k];
        }
        if (P && first < xhi) pref_row(im, P, i, first - P->xlo);
    }
}

void apply_tri(Img *im, int xlo, int xhi, const double *p, double a, const float *col) {
    int *bj = malloc(sizeof(int) * (xhi - xlo + 2));
    float *bc = malloc(sizeof(float) * (xhi - xlo + 2));
    apply_tri_pref(im, NULL, xlo, xhi, p, a, col, bj, bc);
    free(bj);
    free(bc);
}

/* 阶段 1 共享前缀和：落笔之后由调用方更新受影响的行。 */
void pref_update_tri(void *h, const Img *im, const double *p) {
    Pref *P = h;
    int *bj = malloc(sizeof(int) * (P->w + 2));
    float *bc = malloc(sizeof(float) * (P->w + 2));
    int i0, i1;
    if (tri_rows(p, im->H, &i0, &i1)) {
        for (int i = i0; i <= i1; i++) {
            int a0, a1, nb;
            if (!row_cov(p, i, P->xlo, P->xlo + P->w, &a0, &a1, &nb, bj, bc)) continue;
            int first = P->xlo + P->w;
            if (a1 >= a0) first = a0;
            for (int k = 0; k < nb; k++)
                if (bj[k] < first) first = bj[k];
            pref_row(im, P, i, first - P->xlo);
        }
    }
    free(bj);
    free(bc);
}

static void clamp6(double *p, int xlo, int xhi, int H) {
    for (int v = 0; v < 3; v++) {
        double x = nearbyint(p[2 * v]), y = nearbyint(p[2 * v + 1]);
        p[2 * v] = x < xlo ? xlo : (x > xhi ? xhi : x);
        p[2 * v + 1] = y < 0 ? 0 : (y > H ? H : y);
    }
}
static double ptp(const double *p, int off) {
    double lo = fmin(p[off], fmin(p[off + 2], p[off + 4])), hi = fmax(p[off], fmax(p[off + 2], p[off + 4]));
    return hi - lo;
}

/* 按误差构建累积分布，用于按误差大小随机选中心。返回总误差。 */
double build_cdf(const Img *im, int xlo, int xhi, double *cdf) {
    double acc = 0;
    size_t k = 0;
    int w = xhi - xlo;
    for (int i = 0; i < im->H; i++) {
        const float *e = im->E + (size_t)i * im->W + xlo;
        for (int j = 0; j < w; j++) {
            acc += e[j];
            cdf[k++] = acc;
        }
    }
    return acc;
}

/* 为一个形状做搜索（不改画布）：reps 轮 ×（K 个随机候选取最好 → 爬山），返回最好的误差变化量。 */
static double search(const Img *im, const Pref *pf, int xlo, int xhi, Rng *r, const double *cdf, double acc,
                     double smin, double top, int K, int age, int maxit, int reps, double alpha, double *gbest,
                     float *gcol) {
    int H = im->H, w = xhi - xlo;
    size_t npx = (size_t)w * H;
    double p[6], q[6], best[6], gbd = 0;
    float col[3], bcol[3];
    int *bj = malloc(sizeof(int) * (w + 2));
    float *bc = malloc(sizeof(float) * (w + 2));
    Acc A;
    for (int rp = 0; rp < reps; rp++) {
        double bd = 0;
        int have = 0;
        for (int c = 0; c < K; c++) {
            double cx, cy;
            if (urand(r) < 0.7 && acc > 0) {
                double v = urand(r) * acc;
                size_t lo = 0, hi = npx;
                while (lo < hi) {
                    size_t mid = (lo + hi) / 2;
                    if (cdf[mid] < v) lo = mid + 1;
                    else hi = mid;
                }
                if (lo >= npx) lo = npx - 1;
                cy = (double)(lo / w) + urand(r);
                cx = (double)(lo % w) + xlo + urand(r);
            } else {
                cx = xlo + urand(r) * w;
                cy = urand(r) * H;
            }
            double s = exp(log(smin) + urand(r) * (log(top) - log(smin)));
            double ax = exp(log(0.5) + urand(r) * (log(3.0) - log(0.5)));
            for (int v = 0; v < 3; v++) {
                p[2 * v] = cx + nrand(r) * s * ax;
                p[2 * v + 1] = cy + nrand(r) * s / ax;
            }
            clamp6(p, xlo, xhi, H);
            tri_acc(im, pf, xlo, xhi, p, alpha, bj, bc, &A);
            double d = acc_eval(&A, col);
            if (d < bd) {
                bd = d;
                memcpy(best, p, sizeof p);
                memcpy(bcol, col, sizeof col);
                have = 1;
            }
        }
        if (!have) continue;
        int fails = 0, it = 0;
        while (fails < age && it < maxit) {
            it++;
            memcpy(q, best, sizeof q);
            double ext = fmax(fmax(ptp(q, 0), ptp(q, 1)), 2.0);
            if (urand(r) < 0.25) {
                double dx = nrand(r) * ext * 0.15, dy = nrand(r) * ext * 0.15;
                for (int v = 0; v < 3; v++) {
                    q[2 * v] += dx;
                    q[2 * v + 1] += dy;
                }
            } else {
                int v = (int)(urand(r) * 3);
                if (v > 2) v = 2;
                double sg = fmax(1.0, ext * 0.2);
                q[2 * v] += nrand(r) * sg;
                q[2 * v + 1] += nrand(r) * sg;
            }
            clamp6(q, xlo, xhi, H);
            tri_acc(im, pf, xlo, xhi, q, alpha, bj, bc, &A);
            double d = acc_eval(&A, col);
            if (d < bd) {
                bd = d;
                memcpy(best, q, sizeof q);
                memcpy(bcol, col, sizeof col);
                fails = 0;
            } else {
                fails++;
            }
        }
        if (bd < gbd) {
            gbd = bd;
            memcpy(gbest, best, sizeof best);
            memcpy(gcol, bcol, sizeof bcol);
        }
    }
    free(bj);
    free(bc);
    return gbd;
}

/* 供多线程调用：只搜索不落笔。cdf/acc 与前缀和由调用方事先准备（只读共享）。 */
double search_one(const Img *im, void *pref, int xlo, int xhi, const double *cdf, double acc, uint64_t seed,
                  double smin, double top, int K, int age, int maxit, int reps, double alpha, double *out_tri,
                  float *out_col) {
    Rng r;
    rng_seed(&r, seed);
    return search(im, pref, xlo, xhi, &r, cdf, acc, smin, top, K, age, maxit, reps, alpha, out_tri, out_col);
}

/* 在 [xlo, xhi) 这一段里贪心加最多 n 个三角形，原地修改 im->C 和 im->E。返回实际加的个数。 */
int fit_region(Img *im, int xlo, int xhi, int n, uint64_t seed, double smin, double smax, int K, int age, int maxit,
               int reps, double alpha, double deadline, int *out_tri, int *out_col, double *out_gain) {
    Rng r;
    rng_seed(&r, seed);
    int w = xhi - xlo;
    double *cdf = malloc(sizeof(double) * (size_t)w * im->H);
    double *exts = malloc(sizeof(double) * (n > 0 ? n : 1));
    int *bj = malloc(sizeof(int) * (w + 2));
    float *bc = malloc(sizeof(float) * (w + 2));
    int count = 0, misses = 0;
    double best[6];
    float bcol[3];
    Pref *pf = pref_new(im, xlo, xhi, alpha);
    while (count < n && misses < 30) {
        if (deadline > 0 && now() > deadline) break;
        double acc = build_cdf(im, xlo, xhi, cdf);
        double top = smax;
        if (count >= 20 && urand(&r) < 0.85) {
            int m = count < 30 ? count : 30;
            double tmp[30];
            memcpy(tmp, exts + count - m, m * sizeof(double));
            qsort(tmp, m, sizeof(double), cmp_double);
            double med = (m % 2) ? tmp[m / 2] : 0.5 * (tmp[m / 2 - 1] + tmp[m / 2]);
            top = fmin(smax, fmax(3 * smin, 0.8 * med));
        }
        double bd = search(im, pf, xlo, xhi, &r, cdf, acc, smin, top, K, age, maxit, reps, alpha, best, bcol);
        if (bd >= 0) {
            misses++;
            continue;
        }
        apply_tri_pref(im, pf, xlo, xhi, best, alpha, bcol, bj, bc);
        misses = 0;
        exts[count] = fmax(ptp(best, 0), ptp(best, 1)) / 2.5;
        for (int v = 0; v < 6; v++) out_tri[6 * count + v] = (int)best[v];
        for (int ch = 0; ch < 3; ch++) out_col[3 * count + ch] = (int)nearbyint(bcol[ch] * 255);
        out_gain[count] = -bd;
        count++;
    }
    free(cdf);
    free(exts);
    free(bj);
    free(bc);
    pref_free(pf);
    return count;
}

/* 从背景色开始按顺序画 n 个形状，得到最终画布（同时更新 E）。 */
void render_seq(Img *im, const float *bg, int n, const double *tris, const float *cols, double a) {
    size_t npx = (size_t)im->W * im->H;
    for (size_t k = 0; k < npx; k++) {
        for (int ch = 0; ch < 3; ch++) im->C[3 * k + ch] = bg[ch];
        im->E[k] = (float)pix_err(im->T[3 * k] - bg[0], im->T[3 * k + 1] - bg[1], im->T[3 * k + 2] - bg[2]);
    }
    int *bj = malloc(sizeof(int) * (im->W + 2));
    float *bc = malloc(sizeof(float) * (im->W + 2));
    for (int k = 0; k < n; k++) apply_tri_pref(im, NULL, 0, im->W, tris + 6 * k, a, cols + 3 * k, bj, bc);
    free(bj);
    free(bc);
}

/* 对一个三角形覆盖到的每个像素执行 BODY（可用变量 q 为像素下标、al 为混合比例 a*cov）。 */
#define FOR_COVERED(P, A_, W_, H_, BJ, BC, BODY)                                   \
    do {                                                                        \
        int i0_, i1_;                                                           \
        if (tri_rows(P, H_, &i0_, &i1_)) {                                      \
            for (int i_ = i0_; i_ <= i1_; i_++) {                               \
                int a0_, a1_, nb_;                                              \
                if (!row_cov(P, i_, 0, W_, &a0_, &a1_, &nb_, BJ, BC)) continue; \
                for (int j_ = a0_; j_ <= a1_; j_++) {                           \
                    size_t q = (size_t)i_ * (W_) + j_;                          \
                    double al = (A_);                                           \
                    BODY;                                                       \
                }                                                               \
                for (int k_ = 0; k_ < nb_; k_++) {                              \
                    size_t q = (size_t)i_ * (W_) + BJ[k_];                      \
                    double al = (A_) * BC[k_];                                  \
                    BODY;                                                       \
                }                                                               \
            }                                                                   \
        }                                                                       \
    } while (0)

/* 颜色回拟合：形状位置固定时，最终画面对每个颜色是线性的，
 * 颜色 k 对像素 p 的系数是 al_k(p) × prod_{k 之后覆盖 p 的 j} (1 - al_j(p))。
 * 从最后一个形状往前逐个做最小二乘更新（Gauss-Seidel），扫 sweeps 遍。画布须是这 n 个形状的渲染结果。 */
void backfit_colors(Img *im, int n, const double *tris, float *cols, double a, int sweeps) {
    int W = im->W, H = im->H;
    size_t npx = (size_t)W * H;
    float *R = malloc(sizeof(float) * npx * 3);
    float *att = malloc(sizeof(float) * npx);
    int *bj = malloc(sizeof(int) * (W + 2));
    float *bc = malloc(sizeof(float) * (W + 2));
    for (size_t k = 0; k < npx * 3; k++) R[k] = im->T[k] - im->C[k];
    for (int sw = 0; sw < sweeps; sw++) {
        for (size_t k = 0; k < npx; k++) att[k] = 1;
        for (int k = n - 1; k >= 0; k--) {
            const double *p = tris + 6 * k;
            double sw2 = 0, swr[3] = {0, 0, 0};
            FOR_COVERED(p, a, W, H, bj, bc, {
                double w = al * att[q];
                sw2 += w * w;
                for (int ch = 0; ch < 3; ch++) swr[ch] += w * R[3 * q + ch];
            });
            double dl[3] = {0, 0, 0};
            if (sw2 > 1e-12) {
                for (int ch = 0; ch < 3; ch++) {
                    double v = quant(cols[3 * k + ch] + swr[ch] / sw2);
                    dl[ch] = v - cols[3 * k + ch];
                    cols[3 * k + ch] = (float)v;
                }
            }
            FOR_COVERED(p, a, W, H, bj, bc, {
                double w = al * att[q];
                for (int ch = 0; ch < 3; ch++) R[3 * q + ch] -= (float)(w * dl[ch]);
                att[q] = (float)(att[q] * (1 - al));
            });
        }
    }
    for (size_t k = 0; k < npx; k++) {
        for (int ch = 0; ch < 3; ch++) im->C[3 * k + ch] = im->T[3 * k + ch] - R[3 * k + ch];
        im->E[k] = (float)pix_err(R[3 * k], R[3 * k + 1], R[3 * k + 2]);
    }
    free(R);
    free(att);
    free(bj);
    free(bc);
}

/* ---------- 几何回拟合 ----------
 * 正向扫一遍：形状 k 之前的画布 B 精确已知（正向渲染），最终画布 P 已知，
 * At[p] = k 之后所有形状的衰减 prod (1 - al_j(p))（双精度；处理到形状 k 时除去它自己那一项，除数 >= 1-a）。
 * 改动形状 k 时，最终画面变化 = At × (k 之后画布的变化)。
 * 固定旧几何 G（颜色 c）后，设 D0 = (T-P) + At*alG*(c-B)（拿掉形状 k 后的残差），r = |D0|_Q^2，
 * 新几何 N 覆盖的像素 v = At*alN，新残差 = D0 + v B - v cn；
 * 总误差变化 = sum_{p∈N} (|D0 + vB - v cn|_Q^2 - r) + RG，RG = sum_{p∈G} (r - 现误差)。
 * N 的内部像素 alN = a 固定，逐像素量可做行前缀和；边缘像素逐个算。 */
typedef struct {
    Img *im;
    float *B;
    double *At;
    double a;
    double *tris;
    float *cols;
} BF;

void *bf_init(Img *im, const float *bg, int n, double *tris, float *cols, double a) {
    int W = im->W, H = im->H;
    size_t npx = (size_t)W * H;
    BF *f = malloc(sizeof(BF));
    f->im = im;
    f->a = a;
    f->tris = tris;
    f->cols = cols;
    render_seq(im, bg, n, tris, cols, a);
    f->B = malloc(sizeof(float) * npx * 3);
    f->At = malloc(sizeof(double) * npx);
    for (size_t k = 0; k < npx; k++) {
        f->At[k] = 1;
        for (int ch = 0; ch < 3; ch++) f->B[3 * k + ch] = bg[ch];
    }
    int *bj = malloc(sizeof(int) * (W + 2));
    float *bc = malloc(sizeof(float) * (W + 2));
    double *At = f->At;
    for (int k = 0; k < n; k++) FOR_COVERED(tris + 6 * k, a, W, H, bj, bc, { At[q] *= 1 - al; });
    free(bj);
    free(bc);
    return f;
}

#define NB 6
typedef struct {
    int x0, y0, w, h;
    double *S;  /* 前缀和：S[((i-y0)*(w+1) + j)*NB + k] */
    float *alG; /* 区域内旧几何 G 的混合比例 */
} BReg;

/* 某像素在"拿掉形状 k"时的残差 D0，返回 r = |D0|_Q^2 */
static inline double bf_d0(const BF *f, size_t q, double alG, const float *c, double *D0) {
    const Img *im = f->im;
    double At = f->At[q];
    for (int ch = 0; ch < 3; ch++) {
        double Bv = f->B[3 * q + ch];
        D0[ch] = (im->T[3 * q + ch] - im->C[3 * q + ch]) + At * alG * (c[ch] - Bv);
    }
    return pix_err(D0[0], D0[1], D0[2]);
}

/* 像素 q 被新几何以混合比例 alN 覆盖时的 6 个量：|K|_Q^2 - r, vK(3), v(Y·K), v^2，其中 v = At*alN, K = D0 + vB */
static inline void bf_terms(const BF *f, size_t q, double alG, double alN, const float *c, double *t) {
    double D0[3];
    double r = bf_d0(f, q, alG, c, D0);
    double v = f->At[q] * alN, K[3], kk = 0, ky = 0;
    for (int ch = 0; ch < 3; ch++) {
        K[ch] = D0[ch] + v * f->B[3 * q + ch];
        kk += K[ch] * K[ch];
        ky += LY[ch] * K[ch];
    }
    t[0] = kk + g_lw * ky * ky - r;
    for (int ch = 0; ch < 3; ch++) t[1 + ch] = v * K[ch];
    t[4] = v * ky;
    t[5] = v * v;
}

static void breg_build(const BF *f, const double *G, const float *c, BReg *R, int *bj, float *bc) {
    const Img *im = f->im;
    int W = im->W;
    memset(R->alG, 0, sizeof(float) * (size_t)R->w * R->h);
    int i0, i1;
    if (tri_rows(G, im->H, &i0, &i1))
        for (int i = i0; i <= i1; i++) {
            int a0, a1, nb;
            if (i < R->y0 || i >= R->y0 + R->h) continue;
            if (!row_cov(G, i, R->x0, R->x0 + R->w, &a0, &a1, &nb, bj, bc)) continue;
            float *row = R->alG + (size_t)(i - R->y0) * R->w;
            for (int j = a0; j <= a1; j++) row[j - R->x0] = (float)f->a;
            for (int k = 0; k < nb; k++) row[bj[k] - R->x0] = (float)(f->a * bc[k]);
        }
    for (int rr = 0; rr < R->h; rr++) {
        int i = R->y0 + rr;
        double *row = R->S + (size_t)rr * (R->w + 1) * NB, acc[NB] = {0, 0, 0, 0, 0, 0}, t[NB];
        memcpy(row, acc, sizeof acc);
        for (int jj = 0; jj < R->w; jj++) {
            size_t q = (size_t)i * W + R->x0 + jj;
            bf_terms(f, q, R->alG[(size_t)rr * R->w + jj], f->a, c, t);
            for (int k = 0; k < NB; k++) acc[k] += t[k];
            memcpy(row + (size_t)(jj + 1) * NB, acc, sizeof acc);
        }
    }
}

typedef struct {
    double a1, a2[3], a3, a4;
    long np;
} BAcc;

/* 新几何 N 的累加量；N 碰到区域外返回 0 */
static int breg_acc(const BF *f, const BReg *R, const double *N, const float *c, int *bj, float *bc, BAcc *A) {
    const Img *im = f->im;
    int W = im->W;
    memset(A, 0, sizeof *A);
    int i0, i1;
    if (!tri_rows(N, im->H, &i0, &i1)) return 0;
    if (i0 < R->y0 || i1 >= R->y0 + R->h) return 0;
    double t[NB];
    for (int i = i0; i <= i1; i++) {
        int a0, a1, nb;
        if (!row_cov(N, i, 0, W, &a0, &a1, &nb, bj, bc)) continue;
        if (a1 >= a0 && (a0 < R->x0 || a1 >= R->x0 + R->w)) return 0;
        for (int k = 0; k < nb; k++)
            if (bj[k] < R->x0 || bj[k] >= R->x0 + R->w) return 0;
        int rr = i - R->y0;
        if (a1 >= a0) {
            const double *row = R->S + (size_t)rr * (R->w + 1) * NB;
            const double *hi = row + (size_t)(a1 - R->x0 + 1) * NB, *lo = row + (size_t)(a0 - R->x0) * NB;
            A->a1 += hi[0] - lo[0];
            for (int ch = 0; ch < 3; ch++) A->a2[ch] += hi[1 + ch] - lo[1 + ch];
            A->a3 += hi[4] - lo[4];
            A->a4 += hi[5] - lo[5];
            A->np += a1 - a0 + 1;
        }
        for (int k = 0; k < nb; k++) {
            size_t q = (size_t)i * W + bj[k];
            bf_terms(f, q, R->alG[(size_t)rr * R->w + (bj[k] - R->x0)], f->a * bc[k], c, t);
            A->a1 += t[0];
            for (int ch = 0; ch < 3; ch++) A->a2[ch] += t[1 + ch];
            A->a3 += t[4];
            A->a4 += t[5];
            A->np++;
        }
    }
    return A->np > 0;
}

static double bacc_eval(const BAcc *A, double rg, const float *c, float *cn) {
    if (A->np <= 0) return 1e300;
    if (A->a4 < 1e-12) {
        memcpy(cn, c, 3 * sizeof(float)); /* 完全被后面的形状盖住：颜色无所谓，保持原样 */
    } else {
        for (int ch = 0; ch < 3; ch++) cn[ch] = (float)quant(A->a2[ch] / A->a4);
    }
    double ycn = LY[0] * cn[0] + LY[1] * cn[1] + LY[2] * cn[2], cdot = 0, cc = 0;
    for (int ch = 0; ch < 3; ch++) {
        cdot += cn[ch] * A->a2[ch];
        cc += cn[ch] * cn[ch];
    }
    return A->a1 - 2 * (cdot + g_lw * ycn * A->a3) + A->a4 * (cc + g_lw * ycn * ycn) + rg;
}

/* 把形状 k 从 (G, c) 换成 (N, cn)：P += At*(alN(cn-B) - alG(c-B))，再把 B 推进到"形状 k 之后"。 */
static void bf_commit(BF *f, const double *G, const float *c, const double *N, const float *cn, int *bj, float *bc) {
    Img *im = f->im;
    int W = im->W, H = im->H;
    float *B = f->B, *P = im->C;
    double *At = f->At;
    FOR_COVERED(G, f->a, W, H, bj, bc, {
        for (int ch = 0; ch < 3; ch++) P[3 * q + ch] = (float)(P[3 * q + ch] - At[q] * al * (c[ch] - B[3 * q + ch]));
    });
    FOR_COVERED(N, f->a, W, H, bj, bc, {
        for (int ch = 0; ch < 3; ch++) P[3 * q + ch] = (float)(P[3 * q + ch] + At[q] * al * (cn[ch] - B[3 * q + ch]));
    });
    FOR_COVERED(N, f->a, W, H, bj, bc, {
        for (int ch = 0; ch < 3; ch++) B[3 * q + ch] = (float)((1 - al) * B[3 * q + ch] + al * cn[ch]);
    });
}

void bf_range(void *h, int k0, int k1, int xlo, int xhi, int iters, uint64_t seed) {
    BF *f = h;
    Img *im = f->im;
    int W = im->W, H = im->H;
    Rng r;
    rng_seed(&r, seed);
    double N[6], best[6];
    float cn[3], bc3[3];
    int *bj = malloc(sizeof(int) * (W + 2));
    float *bc = malloc(sizeof(float) * (W + 2));
    for (int k = k0; k < k1; k++) {
        double *G = f->tris + 6 * k;
        float *c = f->cols + 3 * k;
        double *At = f->At;
        /* 除去形状 k 自己的衰减：现在 At = k 之后形状的衰减 */
        FOR_COVERED(G, f->a, W, H, bj, bc, { At[q] /= 1 - al; });
        /* RG = sum_{G} (r - 现误差) */
        double rg = 0, D0[3];
        FOR_COVERED(G, f->a, W, H, bj, bc, {
            double rq = bf_d0(f, q, al, c, D0);
            rg += rq - pix_err(im->T[3 * q] - im->C[3 * q], im->T[3 * q + 1] - im->C[3 * q + 1],
                               im->T[3 * q + 2] - im->C[3 * q + 2]);
        });
        /* 区域：G 的包围盒外扩 pad，限制在 [xlo, xhi) × [0, H) 内 */
        double gext = fmax(ptp(G, 0), ptp(G, 1)), pad = fmax(6.0, 0.6 * gext);
        BReg R;
        int rx0 = (int)floor(fmin(G[0], fmin(G[2], G[4])) - pad), rx1 = (int)ceil(fmax(G[0], fmax(G[2], G[4])) + pad);
        int ry0 = (int)floor(fmin(G[1], fmin(G[3], G[5])) - pad), ry1 = (int)ceil(fmax(G[1], fmax(G[3], G[5])) + pad);
        R.x0 = rx0 < xlo ? xlo : rx0;
        R.y0 = ry0 < 0 ? 0 : ry0;
        R.w = (rx1 > xhi ? xhi : rx1) - R.x0;
        R.h = (ry1 > H ? H : ry1) - R.y0;
        if (R.w < 1) R.w = 1;
        if (R.h < 1) R.h = 1;
        R.S = malloc(sizeof(double) * (size_t)R.h * (R.w + 1) * NB);
        R.alG = malloc(sizeof(float) * (size_t)R.h * R.w);
        breg_build(f, G, c, &R, bj, bc);
        BAcc A;
        memcpy(best, G, sizeof best);
        double bd = breg_acc(f, &R, G, c, bj, bc, &A) ? bacc_eval(&A, rg, c, bc3) : 1e300; /* 只重算颜色 */
        if (bd > 0) {
            memcpy(bc3, c, sizeof bc3);
            bd = 0;
        }
        for (int t = 0; t < iters; t++) {
            memcpy(N, best, sizeof N);
            double ext = fmax(fmax(ptp(N, 0), ptp(N, 1)), 2.0);
            if (urand(&r) < 0.25) {
                double dx = nrand(&r) * ext * 0.1, dy = nrand(&r) * ext * 0.1;
                for (int v = 0; v < 3; v++) {
                    N[2 * v] += dx;
                    N[2 * v + 1] += dy;
                }
            } else {
                int v = (int)(urand(&r) * 3);
                if (v > 2) v = 2;
                double sg = fmax(0.7, ext * 0.12);
                N[2 * v] += nrand(&r) * sg;
                N[2 * v + 1] += nrand(&r) * sg;
            }
            clamp6(N, xlo, xhi, H);
            if (!breg_acc(f, &R, N, c, bj, bc, &A)) continue;
            double d = bacc_eval(&A, rg, c, cn);
            if (d < bd) {
                bd = d;
                memcpy(best, N, sizeof best);
                memcpy(bc3, cn, sizeof bc3);
            }
        }
        free(R.S);
        free(R.alG);
        bf_commit(f, G, c, best, bc3, bj, bc);
        memcpy(G, best, sizeof best);
        memcpy(c, bc3, sizeof bc3);
    }
    free(bj);
    free(bc);
}

void bf_finish(void *h) {
    BF *f = h;
    Img *im = f->im;
    size_t npx = (size_t)im->W * im->H;
    for (size_t k = 0; k < npx; k++)
        im->E[k] = (float)pix_err(im->T[3 * k] - im->C[3 * k], im->T[3 * k + 1] - im->C[3 * k + 1],
                                  im->T[3 * k + 2] - im->C[3 * k + 2]);
    free(f->B);
    free(f->At);
    free(f);
}

/* 每个形状的"删除代价"：其余形状（位置、颜色）不动时，拿掉它总误差会增加多少。
 * 正向扫一遍，和几何回拟合同样的量：RG = sum_{G} (拿掉后的误差 - 现误差)。 */
void removal_costs(Img *im, const float *bg, int n, double *tris, float *cols, double a, double *out) {
    BF *f = bf_init(im, bg, n, tris, cols, a);
    int W = im->W, H = im->H;
    int *bj = malloc(sizeof(int) * (W + 2));
    float *bc = malloc(sizeof(float) * (W + 2));
    for (int k = 0; k < n; k++) {
        double *G = tris + 6 * k;
        float *c = cols + 3 * k;
        double *At = f->At, rg = 0, D0[3];
        FOR_COVERED(G, a, W, H, bj, bc, { At[q] /= 1 - al; });
        FOR_COVERED(G, a, W, H, bj, bc, {
            double rq = bf_d0(f, q, al, c, D0);
            rg += rq - pix_err(im->T[3 * q] - im->C[3 * q], im->T[3 * q + 1] - im->C[3 * q + 1],
                               im->T[3 * q + 2] - im->C[3 * q + 2]);
        });
        out[k] = rg;
        float *B = f->B;
        FOR_COVERED(G, a, W, H, bj, bc, {
            for (int ch = 0; ch < 3; ch++) B[3 * q + ch] = (float)((1 - al) * B[3 * q + ch] + al * c[ch]);
        });
    }
    free(bj);
    free(bc);
    bf_finish(f);
}

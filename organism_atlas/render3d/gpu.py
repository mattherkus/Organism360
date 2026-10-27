"""3D-рендер на видеокарте (OpenGL 3.3 через moderngl): те же кадры, что у Scene3D, в сотни раз быстрее.

Устройство повторяет программный рендер scene.py шаг за шагом, только каждый шаг - проход шейдера:
  1. G-буфер: сетки (треугольники), эллипсоиды и узлы трубок (рисуются как квадраты, а точка поверхности
     считается в шейдере) пишут в пиксель глубину, нормаль, номер части, длину вдоль трубки и номер узла;
  2. карта глубины из точки зрения ключевого света - для мягких теней;
  3. самая дальняя видимая точка (для экранного AO) - последовательным уменьшением кадра;
  4. размытия по Гауссу (стыки частей, AO в двух масштабах), большие - в уменьшенном виде, как gblur;
  5. освещение: материалы surface.py, реалистичный свет shading.py, tone mapping;
  6. уменьшение суперсэмплинга и карта частей (номер части в центре итогового пикселя).
Шум fbm3 и тайлы (Вороной, лабиринт, сосуды) берутся из textures.py, поэтому узор тот же.

Если OpenGL 3.3 нет (старый драйвер, удалённый рабочий стол), make_scene() отдаёт обычный Scene3D,
и всё работает как раньше, только медленнее. Классический стиль (style: classic в look.json) тоже
считается программно: это резервный вид.
Контекст OpenGL привязан к потоку, в котором создан: рендер на видеокарте - только из него
(из другого потока кадр считает Scene3D).
"""

import math
import os
import sys
import threading

import numpy as np
from PIL import Image

from ..colors import hex2rgb
from . import look, shading
from .mathutils import unit
from .scene import BG, Scene3D
from .textures import tile_labyrinth, tile_veins, tile_worley

MAXM = 64                          # частей в модели не больше (иначе - программный рендер)
TEX = ("smooth", "lung", "gyri", "folia", "liver", "muscle", "gland", "bowel")
# шумы fbm3 материалов surface.py: (частота, октавы, seed) - номер строки в текстуре шумов
FIXED_NOISE = ((2.0, 2, 1), (3.0, 3, 2), (16, 2, 3), (2.0, 2, 4), (2.2, 2, 6), (1.8, 2, 7), (9, 2, 8),
               (4.2, 3, 9), (5, 2, 10), (3.0, 2, 11))
WAVES = 12                         # волн в строке шума: до трёх октав по четыре синусоиды

_lock = threading.Lock()
_gl = None                         # GL: единственный контекст программы
_failed = None                     # причина, по которой OpenGL недоступен (тогда не пробуем снова)


def disabled():
    """ORGANISM_ATLAS_GPU=0 - всегда программный рендер (для сравнения и на случай плохого драйвера)"""
    return os.environ.get("ORGANISM_ATLAS_GPU", "1").strip() in ("0", "off", "no", "false")


def context():
    """GL или None, если видеокарта недоступна; создаётся при первом вызове в потоке, который будет рисовать"""
    global _gl, _failed
    with _lock:
        if _gl is None and _failed is None and not disabled():
            try:
                _gl = GL()
            except Exception as e:                  # нет moderngl, драйвера или OpenGL 3.3
                _failed = "%s: %s" % (type(e).__name__, e)
                print("3D: видеокарта недоступна (%s), рендер программный" % _failed, file=sys.stderr)
        return _gl


def available():
    return context() is not None


def info():
    """название видеокарты (для подписи в настройках) или None"""
    gl = context()
    return gl.ctx.info.get("GL_RENDERER") if gl else None


def make_scene(parts):
    """сцена для просмотра: на видеокарте, если она есть, иначе программная"""
    return GpuScene(parts) if available() else Scene3D(parts)


def fbm_waves(f, octs, seed):
    """волны fbm3(p, f, octs, seed) из textures.py: [(направление * частота, фаза, амплитуда)];
    тот же порядок вызовов генератора, что и в fbm3, поэтому шум совпадает"""
    rng = np.random.default_rng(seed)
    out, amp, tot = [], 1.0, 0.0
    for o in range(octs):
        for _ in range(4):
            d = rng.normal(size=3)
            d /= np.linalg.norm(d)
            fr = f * 2 ** o * rng.uniform(0.85, 1.2)
            ph = rng.uniform(0, 6.283)
            out.append((d.astype(np.float32) * fr, ph, amp))
        tot += amp * amp
        amp *= 0.55
    k = 1.0 / math.sqrt(tot * 2.0)
    return [(d, ph, a * k) for d, ph, a in out]


# --- шейдеры

HEADER = """#version 330
uniform vec3 ctr, cam, right_, up_;
uniform float scale, zr;
uniform vec2 cpx, size;
vec2 to_ndc(float sx, float sy) { return vec2(2.0 * sx / size.x - 1.0, 1.0 - 2.0 * sy / size.y); }
"""

FS_HEADER = HEADER + """
vec2 pixel_uv() {                  // (u, v) центра пикселя, как Ug, Vg в Scene3D._raster
    return vec2((gl_FragCoord.x - cpx.x) / scale, (cpx.y - (size.y - gl_FragCoord.y)) / scale);
}
"""

MESH_VS = HEADER + """
in vec3 in_pos; in vec3 in_n;
out vec3 v_n; out float v_z;
void main() {
    vec3 rel = in_pos - ctr;
    v_z = dot(rel, cam);
    v_n = in_n;
    gl_Position = vec4(to_ndc(cpx.x + dot(rel, right_) * scale, cpx.y - dot(rel, up_) * scale), -v_z / zr, 1.0);
}
"""

MESH_FS = FS_HEADER + """
uniform float mid;
in vec3 v_n; in float v_z;
layout(location = 0) out vec4 o0;
layout(location = 1) out vec4 o1;
void main() {
    o0 = vec4(v_z, normalize(v_n));
    o1 = vec4(mid, 0.0, -1.0, 1.0);
}
"""

# квадрат вокруг эллипсоида или шара узла трубки; сама поверхность - в шейдере фрагмента
IMPOSTOR_VS = HEADER + """
in vec2 corner;
in vec3 in_c; in vec3 in_r; in vec3 in_m;      // in_m: номер части, длина вдоль трубки, номер узла
flat out vec3 f_c; flat out vec3 f_r; flat out vec3 f_m;
void main() {
    vec3 rel = in_c - ctr;
    float rb = max(in_r.x, max(in_r.y, in_r.z));
    float sx = cpx.x + (dot(rel, right_) + corner.x * rb) * scale + corner.x * 2.0;
    float sy = cpx.y - (dot(rel, up_) + corner.y * rb) * scale - corner.y * 2.0;
    gl_Position = vec4(to_ndc(sx, sy), 0.0, 1.0);
    f_c = in_c; f_r = in_r; f_m = in_m;
}
"""

ELLIPSOID_FS = FS_HEADER + """
flat in vec3 f_c; flat in vec3 f_r; flat in vec3 f_m;
layout(location = 0) out vec4 o0;
layout(location = 1) out vec4 o1;
void main() {
    vec2 uv = pixel_uv();
    vec3 ir2 = 1.0 / (f_r * f_r);
    vec3 q = (ctr - f_c) + uv.x * right_ + uv.y * up_;
    float A = dot(cam * cam, ir2);
    float B = dot(q * cam, ir2);
    float C0 = dot(q * q, ir2) - 1.0;
    float disc = B * B - A * C0;
    if (disc <= 0.0) discard;
    float zz = (-B + sqrt(disc)) / A;
    vec3 pk = (q + zz * cam) * ir2;
    gl_FragDepth = 0.5 - 0.5 * zz / zr;
    o0 = vec4(zz, pk / (length(pk) + 1e-9));
    o1 = vec4(f_m.x, 0.0, -1.0, 1.0);
}
"""

TUBE_FS = FS_HEADER + """
flat in vec3 f_c; flat in vec3 f_r; flat in vec3 f_m;
layout(location = 0) out vec4 o0;
layout(location = 1) out vec4 o1;
void main() {
    vec2 uv = pixel_uv();
    vec3 rel = f_c - ctr;
    float r = f_r.x;
    float du = uv.x - dot(rel, right_), dv = uv.y - dot(rel, up_);
    float rr = r * r - du * du - dv * dv;
    if (rr <= 0.0) discard;
    float sq = sqrt(rr);
    float zz = dot(rel, cam) + sq;
    gl_FragDepth = 0.5 - 0.5 * zz / zr;
    o0 = vec4(zz, (du * right_ + dv * up_ + sq * cam) / r);
    o1 = vec4(f_m.x, f_m.y, f_m.z, 1.0);
}
"""

QUAD_VS = """#version 330
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
"""

# самая дальняя видимая точка: минимум глубины по блокам 8 x 8 (первый проход читает G-буфер)
ZMIN_FS = """#version 330
uniform sampler2D src;
uniform int first;
out vec4 o;
void main() {
    ivec2 sz = textureSize(src, 0);
    ivec2 p = ivec2(gl_FragCoord.xy) * 8;
    float m = 1e9;
    for (int y = 0; y < 8; y++)
        for (int x = 0; x < 8; x++) {
            ivec2 q = p + ivec2(x, y);
            if (q.x >= sz.x || q.y >= sz.y) continue;
            vec4 t = texelFetch(src, q, 0);
            m = min(m, first == 1 && t.x < -1e8 ? 1e9 : t.x);       // фон G-буфера: -1e9
        }
    o = vec4(m);
}
"""

# что размывать: глубина для AO, швы между частями одной ткани и нормали у швов
PREP_FS = """#version 330
uniform sampler2D g0, g1, zmin;
uniform float radius, tol;
uniform int seam_mats[64];
layout(location = 0) out vec4 o0;     // zf, шов, «своя ткань», 0
layout(location = 1) out vec4 o1;     // нормаль * «своя ткань»
bool blendable(vec4 t1) { return t1.w > 0.5 && seam_mats[int(t1.x)] == 1; }
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    ivec2 sz = textureSize(g0, 0);
    vec4 a0 = texelFetch(g0, p, 0), a1 = texelFetch(g1, p, 0);
    float zbg = texelFetch(zmin, ivec2(0), 0).x - 2.0 * radius;
    float zf = a1.w > 0.5 ? a0.x : zbg;
    bool b = blendable(a1);
    float seam = 0.0;
    if (b) {
        // соседи справа и снизу (снизу в кадре - строкой ниже в GL), с переходом через край, как np.roll
        ivec2 qs[2] = ivec2[2](ivec2((p.x + 1) % sz.x, p.y), ivec2(p.x, (p.y - 1 + sz.y) % sz.y));
        for (int k = 0; k < 2; k++) {
            vec4 b0 = texelFetch(g0, qs[k], 0), b1 = texelFetch(g1, qs[k], 0);
            if (blendable(b1) && b1.x != a1.x && abs(a0.x - b0.x) < tol) seam = 1.0;
        }
    }
    o0 = vec4(zf, seam, b ? 1.0 : 0.0, 0.0);
    o1 = vec4(b ? a0.yzw : vec3(0.0), 0.0);
}
"""

# уменьшение перед большим размытием: среднее по пикселям, центры которых попали в клетку
DOWN_FS = """#version 330
uniform sampler2D src;
uniform vec2 dst;
out vec4 o;
void main() {
    ivec2 sz = textureSize(src, 0);
    vec2 k = vec2(sz) / dst;
    vec2 a = floor(gl_FragCoord.xy - 0.5) * k, b = a + k;
    vec4 s = vec4(0.0); float n = 0.0;
    for (int y = int(floor(a.y)); y < int(ceil(b.y)); y++)
        for (int x = int(floor(a.x)); x < int(ceil(b.x)); x++) {
            vec2 c = vec2(x, y) + 0.5;
            if (c.x < a.x || c.x >= b.x || c.y < a.y || c.y >= b.y) continue;
            s += texelFetch(src, clamp(ivec2(x, y), ivec2(0), sz - 1), 0); n += 1.0;
        }
    o = n > 0.0 ? s / n : texelFetch(src, clamp(ivec2(a), ivec2(0), sz - 1), 0);
}
"""

BLUR_FS = """#version 330
uniform sampler2D src;
uniform ivec2 dir;
uniform int r;
uniform float s;
out vec4 o;
void main() {
    ivec2 sz = textureSize(src, 0);
    ivec2 p = ivec2(gl_FragCoord.xy);
    vec4 acc = vec4(0.0); float tot = 0.0;
    for (int i = -r; i <= r; i++) {
        float w = exp(-float(i * i) / (2.0 * s * s));
        acc += w * texelFetch(src, clamp(p + dir * i, ivec2(0), sz - 1), 0);
        tot += w;
    }
    o = acc / tot;
}
"""

SHADE_FS = """#version 330
#define MAXM 64
#define PI 3.14159265358979
uniform sampler2D g0, g1, prep0, seamA, seamB, ao1, ao2, shadow, noise, wor, lab, vein, tube;
uniform vec3 ctr, cam, right_, up_;
uniform float scale, radius;
uniform vec2 cpx, size;
uniform vec3 bg_c, bg_hi;
uniform int draft, use_seams, ao_two, use_shadow;
uniform float seam_s, ao_d1, ao_d2, ao_strength;
// материалы
uniform vec3 m_color[MAXM];
uniform int m_tex[MAXM];
uniform float m_gloss[MAXM], m_rings[MAXM], m_hause[MAXM], m_sss[MAXM], m_wet[MAXM], m_mottle[MAXM], m_veins[MAXM];
uniform vec2 m_rough[MAXM];
// свет (направления в мире; цвета - линейные, уже умножены на яркость)
uniform vec3 l_dir[3], l_col[3], sky, ground;
uniform float ambient, exposure, f0, spec_gain, spec_env;
// тени
uniform vec3 s_l, s_rl, s_ul;
uniform float s_scale, s_size, s_bias, s_soft, s_strength;
out vec4 o;

float fbm(int row, vec3 p) {
    float s = 0.0;
    for (int i = 0; i < %(WAVES)d; i++) {
        vec4 w = texelFetch(noise, ivec2(i, row), 0);
        float a = texelFetch(noise, ivec2(i + %(WAVES)d, row), 0).x;
        if (a == 0.0) break;
        s += a * sin(dot(p, w.xyz) + w.w);
    }
    return s;
}

float samp(sampler2D t, float u, float v) {     // textures.sample: билинейно, с повтором
    float n = float(textureSize(t, 0).x);
    float x = (u - floor(u)) * n, y = (v - floor(v)) * n;
    float x0 = floor(x), y0 = floor(y), fx = x - x0, fy = y - y0;
    int i0 = int(x0) %% int(n), j0 = int(y0) %% int(n);
    int i1 = (i0 + 1) %% int(n), j1 = (j0 + 1) %% int(n);
    return texelFetch(t, ivec2(i0, j0), 0).x * (1.0 - fx) * (1.0 - fy) + texelFetch(t, ivec2(i1, j0), 0).x * fx * (1.0 - fy)
         + texelFetch(t, ivec2(i0, j1), 0).x * (1.0 - fx) * fy + texelFetch(t, ivec2(i1, j1), 0).x * fx * fy;
}

float tri(sampler2D t, vec3 P, vec3 N, float sc) {
    vec3 w = pow(abs(N), vec3(4.0));
    w /= w.x + w.y + w.z + 1e-9;
    vec3 q = P * sc;
    return w.x * samp(t, q.y, q.z) + w.y * samp(t, q.x, q.z) + w.z * samp(t, q.x, q.y);
}

vec4 surf(int m, vec3 P, vec3 N, float sl) {     // surface.surface: (альбедо, высота)
    int tx = m_tex[m];
    float mult = 1.0, h = 0.0;
    vec3 tint = vec3(1.0);
    if (tx == 0) mult += 0.03 * fbm(0, P);
    else if (tx == 1) {
        mult += 0.055 * fbm(1, P) + 0.028 * fbm(2, P);
        mult -= 0.14 * clamp(fbm(3, P) - 0.9, 0.0, 2.0);
        float w = tri(wor, P, N, 0.55);
        mult -= 0.14 * (1.0 - w);
        h = 0.05 * w;
    } else if (tx == 2) {
        float l = tri(lab, P, N, 0.42);
        float sul = clamp((-l - 0.10) * 1.6, 0.0, 1.0);
        mult += 0.04 * clamp((l + 0.15) * 1.2, 0.0, 1.0) - 0.45 * sul;
        if (sul > 0.0) tint = pow(vec3(1.0, 0.90, 0.93), vec3(sul));
        h = -0.075 * sul;
    } else if (tx == 3) {
        float a = sin(P.z * 17.0 + 1.2 * fbm(4, P)) / 0.38;
        float f = exp(-a * a);
        mult -= 0.30 * f;
        h = -0.03 * f;
    } else if (tx == 4) mult += 0.045 * fbm(5, P) + 0.015 * fbm(6, P);
    else if (tx == 5) { float mm = fbm(7, P); mult += 0.035 * mm; h = 0.004 * mm; }
    else if (tx == 6) {
        float w = tri(wor, P, N, 0.32);
        mult += 0.04 * fbm(9, P) - 0.20 * (1.0 - w);
        h = 0.035 * w;
    } else if (tx == 7) mult += 0.035 * fbm(8, P);
    if (m_rings[m] > 0.0) {
        float r = pow(abs(sin(sl * PI / m_rings[m])), 5.0);
        mult *= 1.0 - 0.30 * r;
        h -= 0.012 * r;
    }
    if (m_hause[m] > 0.0) {
        float f = pow(abs(cos(sl * PI / 0.5)), 14.0);
        mult *= 1.0 - 0.34 * f;
        h -= 0.03 * f;
    }
    return vec4(m_color[m] * mult * tint, h);
}

bool bumpy(int m) {                               // у материала есть рельеф (иначе высота везде 0)
    int tx = m_tex[m];
    return tx == 1 || tx == 2 || tx == 3 || tx == 5 || tx == 6 || m_rings[m] > 0.0 || m_hause[m] > 0.0;
}

vec3 aces(vec3 x) { return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }

vec3 tonemap(vec3 lin) {
    float lum = dot(lin, vec3(0.2126, 0.7152, 0.0722));
    float a = aces(vec3(lum)).x;
    vec3 c = lin * (a / (lum + 1e-6));
    float over = max(max(c.r, max(c.g, c.b)) - 1.0, 0.0);
    return clamp(c + over * 0.5, 0.0, 1.0);
}

float shadow_vis(vec3 P) {                        // Scene3D._shadow: карта глубины и кольцо выборок
    vec3 rel = P - ctr;
    float x = s_size / 2.0 + dot(rel, s_rl) * s_scale - 0.5;
    float y = s_size / 2.0 - dot(rel, s_ul) * s_scale - 0.5;
    float d = dot(rel, s_l);
    float dark = 0.0;
    int S = int(s_size);
    for (int k = 0; k < 13; k++) {
        vec2 off;
        if (k == 0) off = vec2(0.0);
        else if (k < 9) { float t = 2.0 * PI * float(k - 1) / 8.0; off = s_soft * vec2(cos(t), sin(t)); }
        else { float t = 0.4 + 2.0 * PI * float(k - 9) / 4.0; off = 0.5 * s_soft * vec2(cos(t), sin(t)); }
        int xi = clamp(int(roundEven(x + off.x)), 0, S - 1);
        int yi = clamp(int(roundEven(y + off.y)), 0, S - 1);
        if (texelFetch(shadow, ivec2(xi, S - 1 - yi), 0).x > d + s_bias) dark += 1.0;
    }
    return 1.0 - s_strength * dark / 13.0;
}

void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    vec2 uvn = gl_FragCoord.xy / size;
    vec4 a0 = texelFetch(g0, p, 0), a1 = texelFetch(g1, p, 0);
    if (a1.w < 0.5) {                             // фон: Scene3D.background
        float xx = float(p.x), yy = size.y - 1.0 - float(p.y);
        float r = length(vec2((xx / size.x - 0.5) / 0.5, (yy / size.y - 0.52) / 0.56));
        float t = pow(clamp(1.0 - r, 0.0, 1.0), 1.6);
        o = vec4(bg_c * (1.0 - t) + bg_hi * t, 1.0);
        return;
    }
    int m = int(a1.x);
    vec3 N = a0.yzw;
    if (use_seams == 1) {                         // Scene3D._soften_seams
        vec4 sa = texture(seamA, uvn);
        vec3 nb = texture(seamB, uvn).xyz / (sa.z + 1e-6);
        float w = clamp(sa.y * 2.5 * seam_s, 0.0, 1.0) * texelFetch(prep0, p, 0).z;     // только своя ткань
        N = N * (1.0 - w) + nb * w;
        N /= length(N) + 1e-9;
    }
    N /= length(N) + 1e-9;
    vec2 uv = vec2((gl_FragCoord.x - cpx.x) / scale, (cpx.y - (size.y - gl_FragCoord.y)) / scale);
    vec3 P = ctr + uv.x * right_ + uv.y * up_ + a0.x * cam;
    float sl = a1.y;
    if (a1.z >= 0.0) {                            // трубка: без осевой компоненты нормали
        int i = int(a1.z);
        vec4 t0 = texelFetch(tube, ivec2(i %% 1024, (i / 1024) * 2), 0);
        float cw = texelFetch(tube, ivec2(i %% 1024, (i / 1024) * 2 + 1), 0).x;
        vec3 Tt = t0.xyz;
        vec3 npd = N - dot(N, Tt) * Tt;
        npd /= length(npd) + 1e-9;
        vec3 nt = npd - t0.w * Tt;
        nt /= length(nt) + 1e-9;
        vec3 nm = cw * nt + (1.0 - cw) * N;
        N = nm / (length(nm) + 1e-9);
    }
    vec4 s0 = surf(m, P, N, sl);
    vec3 alb = s0.xyz;
    if (bumpy(m)) {
        float eps = 0.02;
        float hu = surf(m, P + eps * right_, N, sl).w, hv = surf(m, P + eps * up_, N, sl).w;
        vec3 Nn = N - 0.9 * ((hu - s0.w) / eps * right_ + (hv - s0.w) / eps * up_);
        N = Nn / (length(Nn) + 1e-9);
    }
    // экранный AO
    float zf = a0.x;
    float occ = clamp((texture(ao2, uvn).x - zf) / (ao_d2 * radius), 0.0, 1.0);
    if (ao_two == 1) occ = max(occ, clamp((texture(ao1, uvn).x - zf) / (ao_d1 * radius), 0.0, 1.0));
    float vis = use_shadow == 1 ? shadow_vis(P) : 1.0;
    // shading.shade
    vec3 V = cam;
    vec3 lin_alb = pow(clamp(alb, 0.0, 1.0), vec3(2.2));
    float wet = m_wet[m];
    if (draft == 0) {
        if (m_mottle[m] > 0.0) {
            float mo = m_mottle[m];
            float mm = clamp(0.5 + 0.9 * fbm(%(NFIXED)d + 3 * m, P), 0.0, 1.0);
            lin_alb = lin_alb * (1.0 + mo * (0.6 - mm)) * (1.0 - mo * mm * (1.0 - vec3(0.86, 0.74, 0.80)));
        }
        if (m_veins[m] > 0.0) {
            float v = tri(vein, P, N, 0.45) * clamp(0.5 + fbm(%(NFIXED)d + 3 * m + 1, P), 0.0, 1.0);
            lin_alb = lin_alb * (1.0 - m_veins[m] * v * (1.0 - vec3(0.62, 0.38, 0.55)));
        }
        wet = clamp(m_wet[m] * (0.75 + 0.6 * fbm(%(NFIXED)d + 3 * m + 2, P)), 0.0, 1.0);
    }
    float rough = m_rough[m].x + (m_rough[m].y - m_rough[m].x) * wet;
    float sss = m_sss[m];
    float gfac = clamp(m_gloss[m] / 0.4, 0.3, 1.6);
    float ndv = clamp(dot(N, V), 1e-4, 1.0);
    vec3 wrap = sss * vec3(0.9, 0.42, 0.30), bleed = sss * vec3(0.42, 0.14, 0.09);
    vec3 diffuse = vec3(0.0), spec = vec3(0.0);
    float expo = clamp(2.0 / (rough * rough + 1e-4) - 2.0, 2.0, 4000.0);
    for (int k = 0; k < 3; k++) {
        vec3 L = l_dir[k];
        float ndl = dot(N, L);
        vec3 w_ = k != 2 ? wrap : vec3(0.0);
        vec3 d = clamp((ndl + w_) / (1.0 + w_), 0.0, 1.0);
        if (k == 0 && use_shadow == 1) d = d * (vis + (1.0 - vis) * bleed);
        diffuse += d * l_col[k];
        vec3 Hh = L + V;
        Hh /= length(Hh) + 1e-9;
        float ndh = clamp(dot(N, Hh), 0.0, 1.0);
        float fr = f0 + (1.0 - f0) * pow(1.0 - max(dot(Hh, V), 0.0), 5.0);
        float s = ndh > 0.0 ? fr * (expo + 8.0) / (8.0 * PI) * pow(ndh, expo) * clamp(ndl, 0.0, 1.0) : 0.0;
        if (k == 0 && use_shadow == 1) s *= vis;
        spec += s * gfac * spec_gain * (0.35 + 0.65 * wet) * l_col[k];
    }
    vec3 wup = vec3(0.0, 0.0, 1.0);
    float t = 0.5 + 0.5 * dot(N, wup);
    vec3 amb = (ground * (1.0 - t) + sky * t) * ambient * (1.0 - ao_strength * occ);
    vec3 R = 2.0 * ndv * N - V;
    float tr = clamp(0.5 + 0.5 * dot(R, wup), 0.0, 1.0);
    vec3 env = ground * (1.0 - tr) + sky * pow(tr, 0.6);
    float fr_v = f0 + (1.0 - f0) * pow(1.0 - ndv, 5.0);
    float env_w = spec_env * fr_v * (1.0 - rough) * (1.0 - rough) * (0.3 + 0.7 * wet) * gfac * (1.0 - 0.6 * occ);
    vec3 lin = lin_alb * (diffuse * (1.0 - 0.35 * ao_strength * occ) + amb) + spec + env * env_w;
    o = vec4(clamp(pow(tonemap(lin * exposure), vec3(1.0 / 2.2)), 0.0, 1.0), 1.0);
}
"""

# уменьшение суперсэмплинга (как Image.reduce) и номер части в центре итогового пикселя
REDUCE_FS = """#version 330
uniform sampler2D img, g1;
uniform int ss;
layout(location = 0) out vec4 o;
layout(location = 1) out vec4 ids;
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    vec3 acc = vec3(0.0);
    for (int y = 0; y < ss; y++)
        for (int x = 0; x < ss; x++)
            acc += round(texelFetch(img, p * ss + ivec2(x, y), 0).rgb * 255.0);
    o = vec4(floor(acc / float(ss * ss) + 0.5) / 255.0, 1.0);
    vec4 c = texelFetch(g1, ivec2(p.x * ss + ss / 2, p.y * ss + ss - 1 - ss / 2), 0);
    ids = vec4(c.w > 0.5 ? c.x : -1.0);
}
"""


class GL:
    """контекст OpenGL, шейдеры и общие текстуры (тайлы); кадры рисует GpuScene"""

    def __init__(self):
        import moderngl
        self.mgl = moderngl
        ctx = None
        errors = []
        for kw in ({}, {"backend": "egl"}):        # без экрана в Linux - через EGL
            try:
                ctx = moderngl.create_standalone_context(require=330, **kw)
                break
            except Exception as e:
                errors.append(str(e))
        if ctx is None:
            raise RuntimeError("; ".join(errors))
        self.ctx = ctx
        ctx.gc_mode = "auto"                        # буферы сцены освобождаются вместе с ней
        self.thread = threading.get_ident()
        prog = ctx.program
        self.mesh = prog(vertex_shader=MESH_VS, fragment_shader=MESH_FS)
        self.ellipsoid = prog(vertex_shader=IMPOSTOR_VS, fragment_shader=ELLIPSOID_FS)
        self.tubeprog = prog(vertex_shader=IMPOSTOR_VS, fragment_shader=TUBE_FS)
        self.zmin = prog(vertex_shader=QUAD_VS, fragment_shader=ZMIN_FS)
        self.prep = prog(vertex_shader=QUAD_VS, fragment_shader=PREP_FS)
        self.blur = prog(vertex_shader=QUAD_VS, fragment_shader=BLUR_FS)
        self.shade = prog(vertex_shader=QUAD_VS, fragment_shader=SHADE_FS % {
            "WAVES": WAVES, "NFIXED": len(FIXED_NOISE)})
        self.reduce = prog(vertex_shader=QUAD_VS, fragment_shader=REDUCE_FS)
        self.down = prog(vertex_shader=QUAD_VS, fragment_shader=DOWN_FS)
        quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32).tobytes())
        self.quad = quad
        self.vaos = {name: ctx.vertex_array(p, [(quad, "2f", "in_pos")])
                     for name, p in (("zmin", self.zmin), ("prep", self.prep), ("blur", self.blur),
                                     ("shade", self.shade), ("reduce", self.reduce), ("down", self.down))}
        self.corner = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32).tobytes())
        self.tiles = {}
        for name, make in (("wor", tile_worley), ("lab", tile_labyrinth), ("vein", tile_veins)):
            a = np.ascontiguousarray(make(), np.float32)
            t = ctx.texture((a.shape[1], a.shape[0]), 1, a.tobytes(), dtype="f4")
            t.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self.tiles[name] = t
        self.pool = {}                             # {(w, h, каналы, тип): [(текстура, fbo)]} - между кадрами
        self.sizes = []                            # размеры кадров в пуле (последние сверху)

    # --- текстуры-посредники
    def target(self, size, comps=4, dtype="f4", depth=False, n=1, tag=""):
        """(текстуры, fbo) нужного размера из пула; tag различает одновременно нужные одинаковые цели"""
        key = (size, comps, dtype, depth, n, tag)
        if key not in self.pool:
            mgl = self.mgl
            texs = []
            for _ in range(n):
                t = self.ctx.texture(size, comps, dtype=dtype)
                t.filter = (mgl.LINEAR, mgl.LINEAR)
                t.repeat_x = t.repeat_y = False
                texs.append(t)
            db = self.ctx.depth_renderbuffer(size) if depth else None
            self.pool[key] = (texs, self.ctx.framebuffer(color_attachments=texs, depth_attachment=db))
            if size not in self.sizes:
                self.sizes.insert(0, size)
            else:
                self.sizes.remove(size)
                self.sizes.insert(0, size)
            self._trim()
        return self.pool[key]

    def _trim(self):
        """держать посредников не больше чем для 6 размеров кадра (вращение, зум, смена окна)"""
        while len(self.sizes) > 24:
            old = self.sizes.pop()
            for key in [k for k in self.pool if k[0] == old]:
                texs, fbo = self.pool.pop(key)
                fbo.release()
                for t in texs:
                    t.release()

    def gblur(self, src, size, s, tag):
        """размытие текстуры src (size = (w, h)) по Гауссу с сигмой s - как render2d.noise.gblur:
        большие сигмы - в уменьшенном виде. Возвращает текстуру (читать её через texture(): размер другой)"""
        if s <= 0.05:
            return src
        w, h = size
        if s > 5:
            f = int(s / 2.5)
            small = (max(w // f, 2), max(h // f, 2))
            (dt,), dfbo = self.target(small, tag=tag + "d")
            dfbo.use()
            src.use(0)
            self.down["src"] = 0
            self.down["dst"] = tuple(map(float, small))
            self.vaos["down"].render(self.mgl.TRIANGLE_STRIP)
            src, (w, h), s = dt, small, s / f
        r = int(3 * s) + 1
        (t1,), f1 = self.target((w, h), tag=tag + "h")
        (t2,), f2 = self.target((w, h), tag=tag + "v")
        b = self.blur
        b["r"], b["s"] = r, float(s)
        for (fbo, inp, d) in ((f1, src, (1, 0)), (f2, t1, (0, 1))):
            fbo.use()
            inp.use(0)
            b["src"] = 0
            b["dir"] = d
            self.vaos["blur"].render(self.mgl.TRIANGLE_STRIP)
        return t2


def _set(prog, **values):
    for k, v in values.items():
        if k in prog:
            prog[k].value = v


class GpuScene(Scene3D):
    """Scene3D, которая рисует на видеокарте (render с тем же смыслом параметров).
    Буферы сетки создаются при первом кадре; классический стиль и ошибки OpenGL - программно"""

    def __init__(self, parts):
        super().__init__(parts)
        self._gpu = None
        self.gpu_error = None          # почему последний кадр считался программно (None - на видеокарте)

    # --- буферы сцены
    def _buffers(self, gl):
        if self._gpu is not None:
            return self._gpu
        ctx = gl.ctx
        meshes = []
        for V, F, VN, mid, cull, _FN in self.meshes:
            data = np.hstack([V, VN]).astype(np.float32)
            vbo = ctx.buffer(data.tobytes())
            ibo = ctx.buffer(np.ascontiguousarray(F, np.uint32).tobytes())
            vao = ctx.vertex_array(gl.mesh, [(vbo, "3f 3f", "in_pos", "in_n")], ibo)
            meshes.append((vao, mid, cull))
        # шум: строки FIXED_NOISE, затем по три на часть (пятна, сосуды, влажность), как в shading.py
        specs = list(FIXED_NOISE)
        for m_id in range(len(self.mats)):
            specs += [(1.3, 3, 31 + m_id), (0.9, 2, 47 + m_id), (2.4, 2, 61 + m_id)]
        tab = np.zeros((len(specs), 2 * WAVES, 4), np.float32)
        for row, spec in enumerate(specs):
            for i, (d, ph, a) in enumerate(fbm_waves(*spec)):
                tab[row, i] = (*d, ph)
                tab[row, WAVES + i, 0] = a
        noise = ctx.texture((2 * WAVES, len(specs)), 4, tab.tobytes(), dtype="f4")
        noise.filter = (gl.mgl.NEAREST, gl.mgl.NEAREST)
        # узлы трубок: касательная и наклон радиуса, вес у концов (для нормалей при освещении)
        n = len(self.C)
        rows = max(1, (n + 1023) // 1024)
        td = np.zeros((rows * 2, 1024, 4), np.float32)
        if n:
            idx = np.arange(n)
            td[(idx // 1024) * 2, idx % 1024] = np.column_stack([self.TG, self.SL])
            td[(idx // 1024) * 2 + 1, idx % 1024, 0] = self.CW
        tube = ctx.texture((1024, rows * 2), 4, td.tobytes(), dtype="f4")
        tube.filter = (gl.mgl.NEAREST, gl.mgl.NEAREST)
        self._gpu = {"meshes": meshes, "noise": noise, "tube": tube, "inst": {}}
        return self._gpu

    def _instances(self, gl, kind, step, hidden):
        """экземпляры квадратов для эллипсоидов или узлов трубок (без скрытых частей), с кэшем"""
        bufs = self._gpu["inst"]
        key = (kind, step, hidden)
        if key not in bufs:
            if len(bufs) > 16:
                bufs.clear()
            if kind == "e":
                rows = [(*c, *r, mid, 0.0, -1.0) for c, r, mid in self.ell if mid not in hidden]
            else:
                rows = [(*self.C[i], self.R[i], self.R[i], self.R[i], self.M[i], self.S[i], i)
                        for i in range(0, len(self.C), step) if int(self.M[i]) not in hidden]
            if not rows:
                bufs[key] = None
            else:
                ctx = gl.ctx
                inst = ctx.buffer(np.asarray(rows, np.float32).tobytes())
                prog = gl.ellipsoid if kind == "e" else gl.tubeprog
                vao = ctx.vertex_array(prog, [(gl.corner, "2f", "corner"),
                                              (inst, "3f 3f 3f/i", "in_c", "in_r", "in_m")])
                bufs[key] = (vao, len(rows))
        return bufs[key]

    def _gbuffer(self, gl, fbo, size, cam, right, up, scale, c, step, hidden):
        """G-буфер в fbo: глубина и нормаль (0), часть, длина вдоль трубки, узел, попадание (1)"""
        mgl = gl.mgl
        ctx = gl.ctx
        fbo.use()
        fbo.clear(-1e9, 0.0, 0.0, 0.0, depth=1.0)
        ctx.enable(mgl.DEPTH_TEST)
        ctx.depth_func = "<"
        ctx.front_face = "ccw"
        ctx.cull_face = "back"
        common = dict(ctr=tuple(map(float, self.center)), cam=tuple(map(float, cam)),
                      right_=tuple(map(float, right)), up_=tuple(map(float, up)), scale=float(scale),
                      zr=float(4 * self.radius + 1e-6), cpx=tuple(map(float, c)), size=tuple(map(float, size)))
        g = self._buffers(gl)
        _set(gl.mesh, **common)
        for vao, mid, cull in g["meshes"]:
            if mid in hidden:
                continue
            if cull:
                ctx.enable(mgl.CULL_FACE)
            else:
                ctx.disable(mgl.CULL_FACE)
            gl.mesh["mid"] = float(mid)
            vao.render(mgl.TRIANGLES)
        ctx.disable(mgl.CULL_FACE)
        for kind, prog in (("e", gl.ellipsoid), ("t", gl.tubeprog)):
            inst = self._instances(gl, kind, step if kind == "t" else 1, hidden)
            if inst:
                _set(prog, **common)
                inst[0].render(mgl.TRIANGLE_STRIP, instances=inst[1])
        ctx.disable(mgl.DEPTH_TEST)

    def _zmin(self, gl, g0, size):
        """самая дальняя видимая глубина: текстура 1 x 1 (без чтения в память - сразу в шейдер)"""
        src, first, (w, h) = g0, 1, size
        while True:
            w, h = (w + 7) // 8, (h + 7) // 8
            (t,), fbo = gl.target((w, h), 1, tag="zmin%d" % first)
            fbo.use()
            src.use(0)
            gl.zmin["src"] = 0
            gl.zmin["first"] = first
            gl.vaos["zmin"].render(gl.mgl.TRIANGLE_STRIP)
            if (w, h) == (1, 1):
                return t
            src, first = t, first + 1

    def render(self, w, h, az, el, zoom=1.0, ss=1, ao=0.55, step=1, style=None, shadows=None, bg=BG, hidden=(),
               ids=False):
        lk = look.get()
        st = style or lk["style"]
        gl = context()
        why = None
        if gl is None:
            why = "нет OpenGL"
        elif "lights" not in lk or st != "realistic":
            why = "классический стиль"
        elif len(self.mats) > MAXM:
            why = "больше %d частей" % MAXM
        elif threading.get_ident() != gl.thread:
            why = "другой поток"
        if why is None:
            try:
                with _lock:
                    out = self._render_gpu(gl, lk, w, h, az, el, zoom, ss, step, shadows, bg, frozenset(hidden))
                self.gpu_error = None
                return out if ids else out[0]
            except Exception as e:                  # драйвер отказал - этот кадр и дальше считаем сами
                why = "%s: %s" % (type(e).__name__, e)
                print("3D: ошибка рендера на видеокарте (%s), кадр программный" % why, file=sys.stderr)
                global _failed, _gl
                _failed, _gl = why, None
        self.gpu_error = why
        return super().render(w, h, az, el, zoom, ss, ao, step, style, shadows, bg, hidden, ids)

    def _render_gpu(self, gl, lk, w, h, az, el, zoom, ss, step, shadows, bg, hidden):
        mgl = gl.mgl
        W_, H_ = w * ss, h * ss
        size = (W_, H_)
        a, e = math.radians(az), math.radians(el)
        cam = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        right = np.array([-math.sin(a), math.cos(a), 0.0])
        up = np.array([-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e)])
        scale = zoom * 0.5 * min(W_, H_) / self.radius
        c = (W_ / 2.0, H_ / 2.0)
        R = self.radius
        draft = step > 1

        (g0, g1), gfbo = gl.target(size, 4, depth=True, n=2, tag="g")
        self._gbuffer(gl, gfbo, size, cam, right, up, scale, c, step, hidden)

        # тени: карта глубины из точки зрения ключевого света
        sh = lk["shadows"]["enabled"] if shadows is None else shadows
        if shadows is None and draft:
            sh = False
        key_dir = shading.light_dirs(lk, cam, right, up)["key"]
        shade = gl.shade
        if sh:
            cfg = lk["shadows"]
            S = int(cfg["map_size"])
            L = key_dir
            ref = np.array([0.0, 0.0, 1.0]) if abs(L[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
            rl = unit(np.cross(ref, L))
            ul = unit(np.cross(L, rl))
            s_scale = 0.5 * S / (1.1 * R)
            (sm, _sm1), sfbo = gl.target((S, S), 4, depth=True, n=2, tag="shadow")
            self._gbuffer(gl, sfbo, (S, S), L, rl, ul, s_scale, (S / 2.0, S / 2.0), 1, hidden)
            _set(shade, s_l=tuple(map(float, L)), s_rl=tuple(map(float, rl)), s_ul=tuple(map(float, ul)),
                 s_scale=float(s_scale), s_size=float(S), s_bias=float(2.5 / s_scale), s_soft=float(cfg["softness"]),
                 s_strength=float(cfg["strength"]))
            sm.use(6)
            shade["shadow"] = 6

        # глубина для AO, швы
        zmin = self._zmin(gl, g0, size)
        seam_ids = [i for i, m in enumerate(self.mats) if m["tex"] in lk["seams"]["textures"]]
        use_seams = not draft and len(seam_ids) >= 2
        (p0, p1), pfbo = gl.target(size, 4, n=2, tag="prep")
        pfbo.use()
        prep = gl.prep
        for i, tex in enumerate((g0, g1, zmin)):
            tex.use(i)
        _set(prep, g0=0, g1=1, zmin=2, radius=float(R), tol=float(0.05 * R))
        mask = np.zeros(64, np.int32)
        mask[[i for i in seam_ids if i < 64]] = 1
        prep["seam_mats"].write(mask.tobytes())
        gl.vaos["prep"].render(mgl.TRIANGLE_STRIP)
        m_size = min(W_, H_)
        if use_seams:
            s = lk["seams"]["width"] * m_size
            sa = gl.gblur(p0, size, s, "seamA")
            sb = gl.gblur(p1, size, s, "seamB")
        else:
            s, sa, sb = 0.0, p0, p1
        r_ao = lk["ao"]["radius"] * m_size
        ao2 = gl.gblur(p0, size, 1.0 * r_ao, "ao2")
        ao1 = gl.gblur(p0, size, 0.45 * r_ao, "ao1") if not draft else ao2

        # освещение
        (img,), ifbo = gl.target(size, 4, dtype="f1", tag="img")
        ifbo.use()
        g = self._gpu
        for i, tex in enumerate((g0, g1, sa, sb, ao1, ao2)):
            tex.use(i)
        g["noise"].use(7)
        gl.tiles["wor"].use(8)
        gl.tiles["lab"].use(9)
        gl.tiles["vein"].use(10)
        g["tube"].use(11)
        p0.use(12)
        if not sh:
            gl.tiles["wor"].use(6)                  # что-то привязать к сэмплеру теней
            shade["shadow"] = 6
        _set(shade, g0=0, g1=1, seamA=2, seamB=3, ao1=4, ao2=5, noise=7, wor=8, lab=9, vein=10, tube=11, prep0=12,
             ctr=tuple(map(float, self.center)), cam=tuple(map(float, cam)), right_=tuple(map(float, right)),
             up_=tuple(map(float, up)), scale=float(scale), radius=float(R), cpx=c, size=(float(W_), float(H_)),
             bg_c=tuple(map(float, hex2rgb(bg[0]))), bg_hi=tuple(map(float, hex2rgb(bg[1]))),
             draft=int(draft), use_seams=int(use_seams), ao_two=int(not draft), use_shadow=int(bool(sh)),
             seam_s=float(s), ao_d1=0.10, ao_d2=0.45, ao_strength=float(lk["ao"]["strength"]))
        self._materials(shade, lk, cam, right, up)
        gl.vaos["shade"].render(mgl.TRIANGLE_STRIP)

        # суперсэмплинг и карта частей
        (out, idt), ofbo = gl.target((w, h), 4, n=2, tag="out%s" % ss)
        ofbo.use()
        img.use(0)
        g1.use(1)
        _set(gl.reduce, img=0, g1=1, ss=int(ss))
        gl.vaos["reduce"].render(mgl.TRIANGLE_STRIP)
        rgb = np.frombuffer(ofbo.read(components=3, attachment=0, dtype="f4"), np.float32).reshape(h, w, 3)
        im = Image.fromarray(np.flipud((rgb * 255 + 0.5).astype(np.uint8)))
        part = np.frombuffer(ofbo.read(components=1, attachment=1, dtype="f4"), np.float32).reshape(h, w)
        return im, np.flipud(part).astype(np.int16)

    def _materials(self, prog, lk, cam, right, up):
        """параметры частей и света - в uniform-массивы шейдера освещения"""
        n = len(self.mats)

        def arr(name, values, dtype=np.float32):
            if name in prog:
                a = np.zeros((MAXM,) + np.shape(values[0]) if n else (MAXM,), dtype)
                if n:
                    a[:n] = values
                prog[name].write(a.tobytes())

        prm = [look.material(lk, m["tex"]) for m in self.mats]
        arr("m_color", [m["color"] for m in self.mats])
        arr("m_tex", [TEX.index(m["tex"]) if m["tex"] in TEX else -1 for m in self.mats], np.int32)
        arr("m_gloss", [m["gloss"] for m in self.mats])
        arr("m_rings", [m["rings"] for m in self.mats])
        arr("m_hause", [m["hause"] for m in self.mats])
        arr("m_sss", [p["sss"] for p in prm])
        arr("m_wet", [p["wetness"] for p in prm])
        arr("m_rough", [p["roughness"] for p in prm])
        arr("m_mottle", [p["mottle"] for p in prm])
        arr("m_veins", [p["veins"] for p in prm])
        lt = lk["lights"]
        _set(prog, sky=tuple(map(float, shading.srgb_to_linear(hex2rgb(lt["sky"])))),
             ground=tuple(map(float, shading.srgb_to_linear(hex2rgb(lt["ground"])))),
             ambient=float(lt["ambient"]), exposure=float(lk["exposure"]), f0=float(lk["specular"]["f0"]),
             spec_gain=float(lk["specular"]["gain"]), spec_env=float(lk["specular"]["env"]))
        dirs = shading.light_dirs(lk, cam, right, up)
        names = ("key", "fill", "rim")
        prog["l_dir"].write(np.array([dirs[k] for k in names], np.float32).tobytes())
        prog["l_col"].write(np.array([shading.srgb_to_linear(hex2rgb(lt[k]["color"])) * lt[k]["intensity"]
                                      for k in names], np.float32).tobytes())

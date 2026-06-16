# pc_eqn.py    - Ecuaciones y Sistemas - PiCalc v5.7
# Módulo de carga dinámica. Importar desde main.py vía _cargar_*().
# Usa pc_bridge para acceder a evaluar_expresion/decimal_a_fraccion/etc.
# sin duplicar el núcleo en RAM.
import math
import gc
from pc_bridge import (evaluar_expresion, decimal_a_fraccion,
                       variables_actuales, extraer_numeros, get_matrices)
import random as _rnd

# Shorthand para menos overhead de lookup
_ef  = evaluar_expresion
_daf = decimal_a_fraccion
_va  = variables_actuales
_en  = extraer_numeros

def _fmt_raiz(v):
    """Formatea una raiz real o compleja de forma compacta."""
    if isinstance(v, complex):
        return _daf(v)
    v = round(v, 8)
    return str(int(v)) if v == int(v) else f"{v:.5f}"


def cmd_cuad(cmd):
    """CUAD(a,b,c) -> resuelve ax^2 + bx + c = 0 (formula cuadratica).
    Devuelve X1 y X2; si MODO_COMPLEJO=True acepta discriminante negativo."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        partes = cmd.split("CUAD", 1)[-1].strip().strip("()")
        p = [_ef(v.strip(), _va()) for v in partes.split(",")]
        a, b, c = p[0], p[1], p[2]
        if abs(a) < 1e-12:
            return "a no puede=0", "Usar SOLVE", ""
        disc = b * b - 4 * a * c
        if disc < 0 and not MODO_COMPLEJO:
            return f"disc={disc:.4f}<0", "Activar CMPLX", "para raices i"
        if MODO_COMPLEJO:
            disc_r = cmath.sqrt(complex(disc))
        else:
            disc_r = math.sqrt(disc)
        x1 = (-b + disc_r) / (2 * a)
        x2 = (-b - disc_r) / (2 * a)
        return "Cuadratica:", f"X1={_fmt_raiz(x1)}", f"X2={_fmt_raiz(x2)}"
    gc.collect()
    except Exception as ex:
        return f"Error: {ex}", "", ""


def cmd_cub(cmd):
    """CUB(a,b,c,d) -> resuelve ax^3 + bx^2 + cx + d = 0
    Metodo: depresion cubica + formula de Cardano.
    Devuelve las 3 raices (reales o complejas segun MODO_COMPLEJO)."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        partes = cmd.split("CUB", 1)[-1].strip().strip("()")
        p = [_ef(v.strip(), _va()) for v in partes.split(",")]
        a, b, c, d = p[0], p[1], p[2], p[3]
        if abs(a) < 1e-12:
            return "a no puede=0", "Usar CUAD/SOLVE", ""
        # Normalizar: x^3 + px + q (depresion cubica: sustituir x = t - b/3a)
        b /= a; c /= a; d /= a
        p_c = c - b * b / 3
        q_c = 2 * b * b * b / 27 - b * c / 3 + d
        disc = (q_c / 2) ** 2 + (p_c / 3) ** 3

        if MODO_COMPLEJO or disc >= 0:
            sqD = cmath.sqrt(complex(disc)) if MODO_COMPLEJO else math.sqrt(max(disc, 0))
            u = (-q_c / 2 + sqD)
            v = (-q_c / 2 - sqD)
            u = (u ** (1 / 3)) if u >= 0 else -((-u) ** (1 / 3))
            v = (v ** (1 / 3)) if v >= 0 else -((-v) ** (1 / 3))
            raices = [u + v - b / 3]
            # Las otras dos raices son complejas conjugadas cuando disc > 0
            w = complex(-0.5, 3 ** 0.5 / 2)
            raices.append(w * u + w.conjugate() * v - b / 3)
            raices.append(w.conjugate() * u + w * v - b / 3)
        else:
            # Tres raices reales: caso cissoid (usar angulo)
            r = 2 * math.sqrt(-p_c / 3)
            theta = math.acos(3 * q_c / (p_c * r)) / 3
            raices = [
                r * math.cos(theta) - b / 3,
                r * math.cos(theta - 2 * math.pi / 3) - b / 3,
                r * math.cos(theta - 4 * math.pi / 3) - b / 3,
            ]

        return (f"X1={_fmt_raiz(raices[0])}",
                f"X2={_fmt_raiz(raices[1])}",
                f"X3={_fmt_raiz(raices[2])}")
    gc.collect()
    except Exception as ex:
        return f"Error: {ex}", "", ""


# ── 11v5.5-B. POLINOMIOS GRADO 4 (NUEVO 6 - v5.5) ──────────

def cmd_cuart(cmd):
    """CUART(a,b,c,d,e) -> resuelve ax^4+bx^3+cx^2+dx+e = 0.
    Usa Newton-Raphson en el plano complejo con deflacion sucesiva
    (a diferencia de CUAD/CUB que usan formulas cerradas, el caso
    general de grado 4 se resuelve numericamente, igual de preciso
    para uso practico). Devuelve hasta 4 raices, reales o complejas
    segun corresponda; valores con parte imaginaria despreciable
    (<1e-6) se muestran como reales."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        partes = cmd.split("CUART", 1)[-1].strip().strip("()")
        p = [_ef(v.strip(), _va()) for v in partes.split(",")]
        if len(p) != 5:
            return "Use CUART(", "a,b,c,d,e)", ""
        a = p[0]
        if abs(a) < 1e-12:
            return "a no puede=0", "Usar CUB/CUAD", ""
        coefs = [c / a for c in p]  # normalizar a coef. principal = 1
        raices = resolver_polinomio_newton(coefs)

        def _limpiar(r):
            if abs(r.imag) < 1e-6:
                return round(r.real, 6)
            return complex(round(r.real, 6), round(r.imag, 6))

        raices = [_limpiar(r) for r in raices]
        # Se muestran en 2 lineas (2 raices cada una) por limite de pantalla
        f = [_fmt_raiz(r) for r in raices]
        return (f"X1={f[0]} X2={f[1]}",
                f"X3={f[2]} X4={f[3]}",
                "Newton+deflac.")
    gc.collect()
    except Exception as ex:
        return f"Error Cuart: {ex}"[:16], "", ""


# ── 11v4-D. MODULO TABLE: TABULACION DE FUNCIONES ──

def resolver_sistema_2x2(coefs):
    """Resuelve a1*x+b1*y=c1 ; a2*x+b2*y=c2 por Regla de Cramer."""
    a1, b1, c1, a2, b2, c2 = coefs
    D = det2([a1, b1, a2, b2])
    if abs(D) < 1e-12:
        return None
    Dx = det2([c1, b1, c2, b2])
    Dy = det2([a1, c1, a2, c2])
    return Dx / D, Dy / D


def resolver_sistema_3x3(coefs):
    """Resuelve un sistema 3x3 (12 valores: 3 filas de a,b,c,d) por Cramer."""
    a1, b1, c1, d1, a2, b2, c2, d2, a3, b3, c3, d3 = coefs
    D = det3([a1, b1, c1, a2, b2, c2, a3, b3, c3])
    if abs(D) < 1e-12:
        return None
    Dx = det3([d1, b1, c1, d2, b2, c2, d3, b3, c3])
    Dy = det3([a1, d1, c1, a2, d2, c2, a3, d3, c3])
    Dz = det3([a1, b1, d1, a2, b2, d2, a3, b3, d3])
    return Dx / D, Dy / D, Dz / D


def resolver_sistema_matrices(cmd):
    """Dispatcher de MAT2(...), MAT3(...), DOT(...) y CROSS(...)."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        if "MAT2" in cmd:
            nums = _en(cmd, "MAT2")
            if len(nums) != 6:
                return "Use MAT2(", "a1,b1,c1,a2,b2,c2)", ""
            sol = resolver_sistema_2x2(nums)
            if sol is None:
                return "Sistema sin", "solucion unica", ""
            x, y = (round(v, 10) for v in sol)
            return f"X = {x:.5f}", f"Y = {y:.5f}", ""

        if "MAT3" in cmd:
            nums = _en(cmd, "MAT3")
            if len(nums) != 12:
                return "Use MAT3(12 val.)", "a1,b1,c1,d1,...,d3", ""
            sol = resolver_sistema_3x3(nums)
            if sol is None:
                return "Sistema sin", "solucion unica", ""
            x, y, z = (round(v, 10) for v in sol)
            return f"X={x:.4f} Y={y:.4f}", f"Z = {z:.4f}", ""

        if "DOT" in cmd:
            nums = _en(cmd, "DOT")
            if len(nums) != 6:
                return "Use DOT(", "ax,ay,az,bx,by,bz)", ""
            a, b = nums[0:3], nums[3:6]
            punto = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
            return f"A . B = {punto:.5f}", "", ""

        if "CROSS" in cmd:
            nums = _en(cmd, "CROSS")
            if len(nums) != 6:
                return "Use CROSS(", "ax,ay,az,bx,by,bz)", ""
            a, b = nums[0:3], nums[3:6]
            cx = a[1] * b[2] - a[2] * b[1]
            cy = a[2] * b[0] - a[0] * b[2]
            cz = a[0] * b[1] - a[1] * b[0]
            return f"AxB=({cx:.3f},{cy:.3f},", f"{cz:.3f})", ""
    except Exception:
        pass
    return "Error Matriz", "", ""


# ── 8. CALCULO DIFERENCIAL E INTEGRAL NUMERICO ─────

def cmd_simu(cmd):
    """SIMU<n>(<args>) resuelve un sistema de ecuaciones lineales n×n.
    n puede ser 2, 3 o 4 (hasta 4x4, superando la Casio fx-991 que
    solo llega a 3x3).

    Formato de argumentos (separados por comas, sin espacios):
      SIMU2: a11,a12,b1,a21,a22,b2           (6 numeros)
      SIMU3: a11,a12,a13,b1,...,a33,b3       (12 numeros)
      SIMU4: a11..a44 fila por fila, b1..b4  (20 numeros)

    Devuelve X1, X2 (,X3 ,X4) en las tres lineas de la OLED."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        # Determinar n desde el nombre del comando
        cmd_u = cmd.upper()
        if "SIMU4" in cmd_u:
            n = 4
        elif "SIMU3" in cmd_u:
            n = 3
        elif "SIMU2" in cmd_u:
            n = 2
        else:
            return "Uso: SIMU2/3/4", "SIMU2(a,b,c,d,e,f)", ""

        # Extraer argumentos
        resto = cmd_u.split(f"SIMU{n}", 1)[-1].strip().strip("()")
        args = [_ef(v.strip(), _va())
                for v in resto.split(",")]

        esperado = n * (n + 1)  # n filas × (n coefs + 1 independiente)
        if len(args) != esperado:
            return f"SIMU{n}: {esperado} args", f"tienes {len(args)}", ""

        # Construir A y b: los argumentos van fila por fila,
        # con el termino independiente al FINAL de cada fila.
        # Ej SIMU2: a11,a12,b1, a21,a22,b2
        A = []
        b = []
        for fila in range(n):
            base = fila * (n + 1)
            A.append([args[base + col] for col in range(n)])
            b.append(args[base + n])

        x = _gauss(A, b)

        # Formatear resultado en las 3 lineas de pantalla (max 4 vars)
        def _fmtx(i, v):
            return f"X{i+1}={_daf(round(v, 8))}"

        if n == 2:
            return _fmtx(0, x[0]), _fmtx(1, x[1]), ""
        if n == 3:
            return _fmtx(0, x[0]), _fmtx(1, x[1]), _fmtx(2, x[2])
        # n == 4: tres lineas, la tercera muestra X3 y X4
        return (_fmtx(0, x[0]),
                _fmtx(1, x[1]),
                f"{_fmtx(2, x[2])} {_fmtx(3, x[3])}")

    except ValueError as e:
        return str(e)[:16], "", ""
    gc.collect()
    except Exception as ex:
        return f"Error SIMU: {ex}"[:16], "", ""


# ── 11v5.3-B. REGRESIONES COMPLETAS (NUEVO 2 - v5.3) ─



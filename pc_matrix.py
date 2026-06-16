# pc_matrix.py - Álgebra Matricial 4x4 - PiCalc v5.7
# Módulo de carga dinámica. Importar desde main.py vía _cargar_*().
# Usa pc_bridge para acceder a evaluar_expresion/decimal_a_fraccion/etc.
# sin duplicar el núcleo en RAM.
import math
import gc
from pc_bridge import (evaluar_expresion, decimal_a_fraccion,
                       variables_actuales, extraer_numeros, get_matrices)


# Shorthand para menos overhead de lookup
_ef  = evaluar_expresion
_daf = decimal_a_fraccion
_va  = variables_actuales
_en  = extraer_numeros

def _fmt_mat(m, filas, cols):
    """Formatea una matriz plana para la pantalla OLED (multi-linea)."""
    lineas = []
    for f in range(filas):
        fila = [f"{m[f * cols + c]:.3f}" for c in range(cols)]
        lineas.append(" ".join(fila))
    return lineas


def _get_mat(nombre):
    m = get_matrices().get(nombre)
    if m is None:
        raise ValueError(f"Mat{nombre} no definida")
    return m


def cmd_matdef(cmd):
    """MATDEF<nombre>,<filas>,<cols>,<v1>,<v2>,...
    Guarda la matriz en get_matrices()['nombre'].
    Ejemplo: MATDEFA,2,2,1,2,3,4  ->  MatA = [[1,2],[3,4]]"""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        resto = cmd.split("MATDEF", 1)[-1].strip()
        partes = resto.split(",")
        nombre = partes[0].upper()
        if nombre not in get_matrices():
            return "Nombre: A B C", "", ""
        filas, cols = int(partes[1]), int(partes[2])
        if filas > 4 or cols > 4:
            return "Max 4x4", "", ""
        vals = [_ef(v, _va()) for v in partes[3:]]
        if len(vals) != filas * cols:
            return "Num valores!=", f"{filas}x{cols}", ""
        get_matrices()[nombre] = {"data": vals, "filas": filas, "cols": cols}
        lineas = _fmt_mat(vals, filas, cols)
        return f"Mat{nombre} OK {filas}x{cols}", lineas[0] if lineas else "", lineas[1] if len(lineas) > 1 else ""
    gc.collect()
    except Exception as ex:
        return f"Error Mat: {ex}", "", ""


def cmd_matadd(cmd):
    """MATADD<A>,<B> -> MatA + MatB, resultado en lineas de pantalla."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        partes = cmd.split("MATADD", 1)[-1].strip().split(",")
        a, b = _get_mat(partes[0].upper()), _get_mat(partes[1].upper())
        if a["filas"] != b["filas"] or a["cols"] != b["cols"]:
            return "Dims distintas", "", ""
        res = [x + y for x, y in zip(a["data"], b["data"])]
        lineas = _fmt_mat(res, a["filas"], a["cols"])
        return lineas[0], lineas[1] if len(lineas) > 1 else "", lineas[2] if len(lineas) > 2 else ""
    gc.collect()
    except Exception as ex:
        return f"Error: {ex}", "", ""


def cmd_matmul(cmd):
    """MATMUL<A>,<B> -> MatA x MatB (producto matricial).
    Requiere cols(A) == filas(B); de lo contrario devuelve Error Dimension."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        partes = cmd.split("MATMUL", 1)[-1].strip().split(",")
        a, b = _get_mat(partes[0].upper()), _get_mat(partes[1].upper())
        fa, ca, fb, cb = a["filas"], a["cols"], b["filas"], b["cols"]
        # Validacion explicita de dimensiones ANTES de entrar al bucle
        if ca != fb:
            return "Error Dimension:", f"cols(A)={ca} != filas(B)={fb}", "MATMUL requiere AxB: n*m x m*p"
        res = []
        for i in range(fa):
            for j in range(cb):
                s = sum(a["data"][i * ca + k] * b["data"][k * cb + j] for k in range(ca))
                res.append(s)
        lineas = _fmt_mat(res, fa, cb)
        return lineas[0], lineas[1] if len(lineas) > 1 else "", lineas[2] if len(lineas) > 2 else ""
    gc.collect()
    except Exception as ex:
        return f"Error: {ex}", "", ""


def cmd_mattrans(cmd):
    """MATTRANS<A> -> transpuesta de MatA."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        nombre = cmd.split("MATTRANS", 1)[-1].strip().upper()
        m = _get_mat(nombre)
        f, c = m["filas"], m["cols"]
        res = [m["data"][i * c + j] for j in range(c) for i in range(f)]
        lineas = _fmt_mat(res, c, f)
        return lineas[0], lineas[1] if len(lineas) > 1 else "", ""
    gc.collect()
    except Exception as ex:
        return f"Error: {ex}", "", ""


def cmd_matdet(cmd):
    """MATDET<A> -> determinante de MatA (solo 2x2 y 3x3)."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        nombre = cmd.split("MATDET", 1)[-1].strip().upper()
        m = _get_mat(nombre)
        d = m["data"]
        if m["filas"] == 2 and m["cols"] == 2:
            return f"det = {_daf(det2(d))}", "", ""
        if m["filas"] == 3 and m["cols"] == 3:
            return f"det = {_daf(det3(d))}", "", ""
        return "Solo 2x2 o 3x3", "", ""
    gc.collect()
    except Exception as ex:
        return f"Error: {ex}", "", ""


def cmd_matinv(cmd):
    """MATINV<A> -> inversa de MatA (2x2 o 3x3)."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        nombre = cmd.split("MATINV", 1)[-1].strip().upper()
        m = _get_mat(nombre)
        d = m["data"]
        if m["filas"] == 2 and m["cols"] == 2:
            res = _inv2(d)
            lineas = _fmt_mat(res, 2, 2)
        elif m["filas"] == 3 and m["cols"] == 3:
            res = _inv3(d)
            lineas = _fmt_mat(res, 3, 3)
        else:
            return "Solo 2x2 o 3x3", "", ""
        return lineas[0], lineas[1] if len(lineas) > 1 else "", lineas[2] if len(lineas) > 2 else ""
    gc.collect()
    except Exception as ex:
        return f"Error: {ex}", "", ""


# ── 11v4-C. MODULO EQN: ECUACIONES CUADRATICAS Y CUBICAS ─

def _inv2(d):
    """Inversa de matriz 2x2 (lista plana de 4 elementos)."""
    det = det2(d)
    if abs(det) < 1e-12:
        raise ValueError("Singular")
    return [d[3] / det, -d[1] / det, -d[2] / det, d[0] / det]


def _inv3(d):
    """Inversa de matriz 3x3 por adjugada / det."""
    det = det3(d)
    if abs(det) < 1e-12:
        raise ValueError("Singular")
    a, b, c, dd, e, f, g, h, ii = d
    adj = [
        (e * ii - f * h), -(b * ii - c * h), (b * f - c * e),
        -(dd * ii - f * g), (a * ii - c * g), -(a * f - c * dd),
        (dd * h - e * g), -(a * h - b * g), (a * e - b * dd),
    ]
    return [v / det for v in adj]


# _inv4: no encontrada

def cmd_matedit(cmd):
    """MATEDIT<nombre>,<filas>,<cols>
    Inicia el editor interactivo de matrices desde consola o teclado fisico.
    Ejemplo: MATEDITA,3,3  abre el editor para una matriz 3x3 en MatA."""
    try:
        resto = cmd.upper().split("MATEDIT", 1)[-1].strip()
        partes = resto.split(",")
        nombre = partes[0].strip()
        filas  = int(_ef(partes[1].strip(), _va()))
        cols   = int(_ef(partes[2].strip(), _va()))
        return matedit_iniciar(nombre, filas, cols)
    except Exception as ex:
        return f"Uso: MATEDITA,f,c", f"Error: {ex}"[:16], ""


# ── 11v5.3-D. POL/REC CON MODO_ANGULOS (NUEVO 3 - v5.3) ─
# Las funciones POL/REC originales (v4.x) siempre usaban grados,
# ignorando SETUPRAD. Ahora respetan MODO_ANGULOS: en RAD, theta
# se interpreta como radianes y el angulo de salida tambien es RAD.



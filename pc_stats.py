# pc_stats.py  - Estadística y Distribuciones - PiCalc v5.7
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

def procesar_estadistica(comando):
    """Maneja el ingreso de datos en lista y los calculos STAT.

    NUEVO 2 (v5.3): ademas de la regresion lineal (STATCALC/STATLIN),
    ahora se soportan todos los modelos de la Casio fx-991 ClassWiz:
    STATCUAD (cuadratica), STATEXP (exponencial), STATLOG (logaritmica),
    STATPOT (potencia), STATINV (inversa). Cada modelo delega en
    calcular_regresion(), que usa _regresion_lineal() o _regresion_cuadratica()
    sobre los datos transformados segun el modelo."""
    global ESTADISTICA_DATOS
    try:
        # ---- Ingreso de datos ----
        if "CLEAR" in comando:
            ESTADISTICA_DATOS.clear()
            return "Lista limpia", "N = 0", ""

        if "ADD:" in comando or comando.startswith("ADD:"):
            if len(ESTADISTICA_DATOS) >= LIMITE_ESTADISTICA:
                return f"Lista llena (max {LIMITE_ESTADISTICA})", "", ""
            val = float(comando.split(":")[-1])
            ESTADISTICA_DATOS.append((val, None))
            return f"N = {len(ESTADISTICA_DATOS)}", f"Ultimo: {val}", ""

        # STATX<x>,<y>: par para regresion
        if comando.startswith("X") or comando.startswith(":X"):
            if len(ESTADISTICA_DATOS) >= LIMITE_ESTADISTICA:
                return f"Lista llena (max {LIMITE_ESTADISTICA})", "", ""
            cuerpo = comando.lstrip(":").lstrip("X")
            partes = cuerpo.split(",")
            if len(partes) < 2:
                return "Error: use STATX<x>,<y>", "", ""
            x_val = _ef(partes[0].strip(), _va())
            y_val = _ef(partes[1].strip(), _va())
            ESTADISTICA_DATOS.append((x_val, y_val))
            return (f"N = {len(ESTADISTICA_DATOS)}",
                    f"Par: ({x_val}, {y_val})", "")

        # ---- Calculos ----
        if not ESTADISTICA_DATOS:
            return "Lista vacia", "", ""

        n      = len(ESTADISTICA_DATOS)
        vals_x = [p[0] for p in ESTADISTICA_DATOS]
        ys     = [p[1] for p in ESTADISTICA_DATOS]
        media  = sum(vals_x) / n
        var    = sum((v - media) ** 2 for v in vals_x) / n
        desv   = math.sqrt(var)

        # Detectar mezcla 1v/2v (FIX 1 v5.2, conservado en v5.3)
        hay_pareado = any(y is not None for y in ys)
        hay_nones   = any(y is None     for y in ys)
        mezcla      = hay_pareado and hay_nones

        # Determinar modelo de regresion solicitado
        modelo = None
        if   "CUAD" in comando: modelo = "CUAD"
        elif "EXP"  in comando: modelo = "EXP"
        elif "LOG"  in comando: modelo = "LOG"
        elif "POT"  in comando: modelo = "POT"
        elif "INV"  in comando: modelo = "INV"
        elif "LIN"  in comando or "CALC" in comando: modelo = "LIN"

        if modelo:
            if mezcla:
                return (f"N={n} Med={media:.4f}",
                        f"s={desv:.4f}",
                        "Error: mezcla 1v/2v")
            if not hay_pareado:
                return "Faltan pares (x,y)", "Usa STATX<x>,<y>", ""
            pares = [(p[0], p[1]) for p in ESTADISTICA_DATOS]
            return calcular_regresion(modelo, pares)

        # Sin modelo: resumen de 1 variable
        l3 = "Error: mezcla 1v/2v" if mezcla else f"s={desv:.4f}"
        return (f"N={n}  Med={media:.4f}",
                f"Var={var:.4f}",
                l3)

    gc.collect()
    except Exception as ex:
        return f"Error Estad: {ex}"[:16], "", ""


# ── 9b. DISTRIBUCIONES ESTADISTICAS (NUEVO 1 - v5.5) ───────
# DIST<tipo><args> via teclado: DISTNPD(x,mu,sigma)  -> Normal PDF
#                                 DISTNCD(a,b,mu,sigma) -> Normal CDF en [a,b]
#                                 DISTBIN(x,n,p)        -> Binomial P(X=x)
#                                 DISTPOI(x,lambda)     -> Poisson P(X=x)
# Implementadas sin librerias externas (solo math), igual de livianas
# que el resto del motor para correr en la Pico.


def calcular_regresion(modelo, datos):
    """Despacha el calculo de regresion segun el modelo solicitado.
    datos: lista de tuplas (x, y) (puntos pareados, y != None).
    modelo: "LIN"|"CUAD"|"EXP"|"LOG"|"POT"|"INV"
    Devuelve tupla de 3 strings (lineas de pantalla)."""
    xs = [p[0] for p in datos]
    ys = [p[1] for p in datos]
    n  = len(xs)

    if modelo == "LIN":
        a, b, r = _regresion_lineal(xs, ys)
        return _fmt_regresion("LIN y=a+bx", a, b, r)

    if modelo == "CUAD":
        a, b, c, r = _regresion_cuadratica(xs, ys)
        return _fmt_regresion("CUAD y=a+bx+cx2", a, b, r, c)

    if modelo == "EXP":
        # y = ae^(bx)  ->  ln(y) = ln(a) + bx
        if any(y <= 0 for y in ys):
            return "EXP: y debe ser", "> 0 para todos", "los puntos"
        lnys = [math.log(y) for y in ys]
        ln_a, b, r = _regresion_lineal(xs, lnys)
        return _fmt_regresion("EXP y=ae^bx", math.exp(ln_a), b, r)

    if modelo == "LOG":
        # y = a + b*ln(x)
        if any(x <= 0 for x in xs):
            return "LOG: x debe ser", "> 0 para todos", "los puntos"
        lnxs = [math.log(x) for x in xs]
        a, b, r = _regresion_lineal(lnxs, ys)
        return _fmt_regresion("LOG y=a+b*ln(x)", a, b, r)

    if modelo == "POT":
        # y = ax^b  ->  ln(y) = ln(a) + b*ln(x)
        if any(x <= 0 for x in xs) or any(y <= 0 for y in ys):
            return "POT: x e y deben", "ser > 0", ""
        lnxs = [math.log(x) for x in xs]
        lnys = [math.log(y) for y in ys]
        ln_a, b, r = _regresion_lineal(lnxs, lnys)
        return _fmt_regresion("POT y=ax^b", math.exp(ln_a), b, r)

    if modelo == "INV":
        # y = a + b/x
        if any(x == 0 for x in xs):
            return "INV: x no puede", "ser 0", ""
        inv_xs = [1.0 / x for x in xs]
        a, b, r = _regresion_lineal(inv_xs, ys)
        return _fmt_regresion("INV y=a+b/x", a, b, r)

    return "Modelo desconocido", f"'{modelo}'", "LIN CUAD EXP LOG POT INV"


# ── 11v5.3-C. EDITOR INTERACTIVO DE MATRICES (NUEVO 4 - v5.3) ─
# Estado del editor de matrices
_MATEDIT_ESTADO = {
    "activo": False,   # True mientras el editor esta abierto
    "nombre": None,    # "A", "B" o "C"
    "filas": 0,
    "cols": 0,
    "datos": [],       # lista plana que se va llenando
    "celda": 0,        # indice de la celda actual (0-based)
}


def cmd_dist(cmd):
    """Despacha las distribuciones estadisticas. Formatos:
      DISTNPD(x,mu,sigma)      Normal: densidad puntual
      DISTNCD(a,b,mu,sigma)    Normal: probabilidad acumulada P(a<=X<=b)
      DISTBIN(k,n,p)           Binomial: P(X=k)
      DISTPOI(k,lambda)        Poisson: P(X=k)
    Sin argumentos (solo "DIST"), muestra un recordatorio de sintaxis."""
    try:
        u = cmd.upper()
        if "NPD" in u:
            nums = _en(u, "NPD")
            if len(nums) != 3:
                return "Use NPD(", "x,mu,sigma)", ""
            x, mu, sigma = nums
            val = _normal_pdf(x, mu, sigma)
            return f"Normal PDF", f"f({x})={_daf(round(val,6))}", ""
        if "NCD" in u:
            nums = _en(u, "NCD")
            if len(nums) != 4:
                return "Use NCD(", "a,b,mu,sigma)", ""
            a, b, mu, sigma = nums
            p = _normal_cdf(b, mu, sigma) - _normal_cdf(a, mu, sigma)
            return f"Normal CDF", f"P({a}<=X<={b})", f"= {_daf(round(p,6))}"
        if "BIN" in u:
            nums = _en(u, "BIN")
            if len(nums) != 3:
                return "Use BIN(", "k,n,p)", ""
            k, n, p = nums
            val = _binomial_pmf(k, n, p)
            return f"Binomial n={int(n)} p={p}", f"P(X={int(k)})", f"= {_daf(round(val,6))}"
        if "POI" in u:
            nums = _en(u, "POI")
            if len(nums) != 2:
                return "Use POI(", "k,lambda)", ""
            k, lam = nums
            val = _poisson_pmf(k, lam)
            return f"Poisson lambda={lam}", f"P(X={int(k)})", f"= {_daf(round(val,6))}"
        return "DIST: NPD NCD", "BIN POI", "ej: DISTNPD(0,0,1)"
    gc.collect()
    except Exception as ex:
        return f"Error DIST: {ex}"[:16], "", ""


# ── 10. MEMORIA: STO / RCL / ANS ───────────────────

def _normal_pdf(x, mu, sigma):
    if sigma <= 0:
        raise ValueError("sigma debe ser > 0")
    coef = 1.0 / (sigma * math.sqrt(2 * math.pi))
    expo = -((x - mu) ** 2) / (2 * sigma ** 2)
    return coef * math.exp(expo)



def _normal_cdf(x, mu, sigma):
    """CDF de la normal via la funcion error: Phi(x) = 0.5*(1+erf((x-mu)/(sigma*sqrt2)))."""
    if sigma <= 0:
        raise ValueError("sigma debe ser > 0")
    z = (x - mu) / (sigma * math.sqrt(2))
    return 0.5 * (1 + math.erf(z))



def _binomial_pmf(k, n, p):
    if not (0 <= p <= 1):
        raise ValueError("p debe estar en [0,1]")
    k, n = int(k), int(n)
    if k < 0 or k > n:
        return 0.0
    return math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))



def _poisson_pmf(k, lam):
    if lam < 0:
        raise ValueError("lambda debe ser >= 0")
    k = int(k)
    if k < 0:
        return 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)



def cmd_dist_ext(cmd):
    """Distribuciones nuevas de v5.6: t-Student, Chi2, F, HiperGeom.
    Las distribuciones originales (NPD/NCD/BIN/POI) siguen en cmd_dist()."""
    try:
        u = cmd.upper()

        # ---- t-Student: DISTT(x,nu) o INVT(p,nu) ----
        if "INVT" in u:
            nums = _en(cmd, "INVT")
            if len(nums) < 2:
                return "Use INVT(p,nu)", "", ""
            p, nu = nums[0], int(round(nums[1]))
            return f"InvT p={p:.4f} nu={nu}", f"t = {_inv_t(p,nu):.5f}", ""
        if u.startswith("DISTT"):
            nums = _en(cmd, "DISTT")
            if len(nums) < 2:
                return "Use DISTT(x,nu)", "", ""
            x, nu = nums[0], int(round(nums[1]))
            P = _cdf_t(x, nu)
            return (f"t({nu}) x={x:.4f}",
                    f"P(T<=x) = {P:.5f}",
                    f"P(T>x)  = {1-P:.5f}")

        # ---- Chi-cuadrado: DISTCHI(x,nu) ----
        if "DISTCHI" in u:
            nums = _en(cmd, "DISTCHI")
            if len(nums) < 2:
                return "Use DISTCHI(x,nu)", "", ""
            x, nu = nums[0], int(round(nums[1]))
            P = _cdf_chi2(x, nu)
            f_val = _pdf_chi2(x, nu)
            return (f"Chi2({nu}) x={x:.4f}",
                    f"PDF = {f_val:.5f}",
                    f"CDF = {P:.5f}")

        # ---- F de Snedecor: DISTF(x,d1,d2) ----
        if "DISTF" in u:
            nums = _en(cmd, "DISTF")
            if len(nums) < 3:
                return "Use DISTF(x,d1,d2)", "", ""
            x, d1, d2 = nums[0], int(round(nums[1])), int(round(nums[2]))
            P = _cdf_f(x, d1, d2)
            return (f"F({d1},{d2}) x={x:.4f}",
                    f"P(F<=x) = {P:.5f}", "")

        # ---- Hipergeometrica: DISTHG(k,N,K,n) ----
        if "DISTHG" in u:
            nums = _en(cmd, "DISTHG")
            if len(nums) < 4:
                return "Use DISTHG(k,N,K,n)", "", ""
            k, N, K, n = [int(round(v)) for v in nums[:4]]
            pmf = _hg_pmf(k, N, K, n)
            cdf = _hg_cdf(k, N, K, n)
            return (f"HG(N={N},K={K},n={n})",
                    f"P(X={k}) = {pmf:.5f}",
                    f"P(X<={k}) = {cdf:.5f}")

    gc.collect()
    except Exception as ex:
        return f"Error DIST: {ex}"[:16], "", ""
    return "DIST: T CHI F HG", "DISTT DISTCHI DISTF", "DISTHG"


# ── NUEVO 12: Conversiones de unidades (CONV) ─────────────────────────
# CONV(valor, DE, A)  — todas las unidades en mayusculas.
_CONV_GRUPOS = {
    # longitud (base: metros)
    "M":1.0, "KM":1e3, "CM":1e-2, "MM":1e-3,
    "MI":1609.344, "YD":0.9144, "FT":0.3048, "IN":0.0254,
    "NM":1852.0,          # milla nautica
    # masa (base: kg)
    "KG":1.0, "G":1e-3, "MG":1e-6, "T":1e3,
    "LB":0.45359237, "OZ":0.028349523,
    # volumen (base: litros)
    "L":1.0, "ML":1e-3, "CL":1e-2, "DL":0.1,
    "GAL":3.785411784, "QT":0.946352946, "PT":0.473176473, "CUP":0.236588236,
    "FLOZ":0.029573530,
    # presion (base: Pa)
    "PA":1.0, "KPA":1e3, "MPA":1e6, "BAR":1e5,
    "ATM":101325.0, "PSI":6894.757, "MMHG":133.322,
    # velocidad (base: m/s)
    "MS":1.0, "KMH":1/3.6, "MPH":0.44704, "KN":0.514444,
    # energia (base: J)
    "J":1.0, "KJ":1e3, "CAL":4.184, "KCAL":4184.0, "WH":3600.0, "KWH":3.6e6,
    "EV":1.60218e-19, "BTU":1055.06,
}
# Temperatura: conversion especial (no lineal)
_TEMP_UNIDADES = {"C", "F", "K"}



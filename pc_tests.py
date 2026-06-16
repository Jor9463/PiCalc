# pc_tests.py  - Suite de Pruebas (solo dev) - PiCalc v5.7
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

def run_tests():
    """Ejecuta casos edge criticos y devuelve (pasados, fallados, log).
    Solo disponible en consola PC (bloqueado en MODO_EXAMEN).
    Invocar con el token TEST."""
    if MODO_EXAMEN:
        return "Bloqueado en", "Modo Examen", ""

    pasados = 0
    fallados = 0
    log = []

    def check(nombre, resultado, esperado):
        nonlocal pasados, fallados
        ok = resultado == esperado
        estado = "OK" if ok else "FAIL"
        if not ok:
            fallados += 1
            log.append(f"  {estado}: {nombre}")
            log.append(f"    got={resultado!r}")
            log.append(f"    exp={esperado!r}")
        else:
            pasados += 1
            log.append(f"  {estado}: {nombre}")

    # --- tokenizador ---
    try:
        tokenizar("1.2.3")
        check("tokenizar 1.2.3", "no lanzó", "error")
    except ValueError:
        check("tokenizar 1.2.3", "error", "error")

    # --- division por cero ---
    r, *_ = procesar_todo("1/0")
    check("division por cero", r, "Division por cer")

    # --- parentesis desbalanceados ---
    r, *_ = procesar_todo("SIN(")
    check("parentesis desbal.", r, "Parentesis desba")

    # --- token desconocido ---
    r, *_ = procesar_todo("FOOBAR")
    check("token desconocido", "Token" in r, True)

    # --- raiz negativa sin CMPLX ---
    prev = MODO_COMPLEJO
    globals()["MODO_COMPLEJO"] = False
    try:
        _ef("SQRT(-1)", _va())
        check("sqrt(-1) sin cmplx", "no lanzó", "error")
    except (ValueError, Exception):
        check("sqrt(-1) sin cmplx", "error", "error")
    globals()["MODO_COMPLEJO"] = prev

    # --- TABLE overflow ---
    r, *_ = cmd_table("TABLEX,0,100,1")
    check("TABLE overflow 101 pts", "Rango" in r, True)

    # --- TABLE valida (5 pts) ---
    r, *_ = cmd_table("TABLEX^2,0,4,1")
    check("TABLE 5 pts OK", r, "TABLE (5 pts)")

    # --- MCD con variables ---
    MEMORIA["A"] = 12
    MEMORIA["B"] = 8
    r, *_ = procesar_todo("MCD(A,B)")
    check("MCD con variables", r, "MCD = 4")
    MEMORIA["A"] = 0.0
    MEMORIA["B"] = 0.0

    # --- fracciones continuas ---
    check("fraccion 1/3", _daf(1/3), "1/3")
    check("fraccion 2/3", _daf(2/3), "2/3")
    check("entero 14", _daf(14.0), "14")

    # --- BASE-N con complejo (FIX 1 v4.5) ---
    prev_c = globals()["MODO_COMPLEJO"]
    globals()["MODO_COMPLEJO"] = True
    r, *_ = cmd_basen("BIN(SQRT(-1))")
    globals()["MODO_COMPLEJO"] = prev_c
    check("BIN complejo rechazado", "complejo" in r.lower() or "Error" in r, True)

    # --- cuadratica ---
    r = cmd_cuad("CUAD(1,-5,6)")
    check("CUAD x^2-5x+6", r, ("Cuadratica:", "X1=3", "X2=2"))

    # --- NUEVO 1 (v5.0): FACT / NPR / NCR ---
    check("5! = 120", _daf(calcular_factorial(5)), "120")
    check("0! = 1", _daf(calcular_factorial(0)), "1")
    check("NPR(5,2) = 20", _daf(calcular_npr(5, 2)), "20")
    check("NCR(5,2) = 10", _daf(calcular_ncr(5, 2)), "10")
    check("NCR(170,2) sin overflow", _daf(calcular_ncr(170, 2)), "14365")
    try:
        calcular_factorial(-1)
        check("FACT(-1) lanza error", "no lanzó", "error")
    except ValueError:
        check("FACT(-1) lanza error", "error", "error")
    try:
        calcular_factorial(171)
        check("FACT(171) lanza error (overflow)", "no lanzó", "error")
    except ValueError:
        check("FACT(171) lanza error (overflow)", "error", "error")

    # --- NUEVO 2 (v5.0): CONJ / ARG ---
    prev_c = globals()["MODO_COMPLEJO"]
    globals()["MODO_COMPLEJO"] = True
    r, *_ = procesar_todo("CONJ(2+3*I)")
    check("CONJ(2+3i) = 2-3i", r, "2-3i")
    r, *_ = procesar_todo("ARG(0+1*I)")
    check("ARG(i) = 90 (DEG)", r, "90")
    globals()["MODO_COMPLEJO"] = prev_c
    r, *_ = procesar_todo("ARG(5)")
    check("ARG(5 real) = 0", r, "0")
    r, *_ = procesar_todo("ARG(-5)")
    check("ARG(-5 real) = 180", r, "180")

    # --- NUEVO 3 (v5.0): SETUP RAD activa el motor (FIX 0) ---
    prev_ang = globals()["MODO_ANGULOS"]
    cmd_setup("SETUPRAD")
    r, *_ = procesar_todo("SIN(PI/2)")
    check("SIN(PI/2) en RAD = 1", r, "1")
    cmd_setup("SETUPDEG")
    r, *_ = procesar_todo("SIN(90)")
    check("SIN(90) en DEG = 1", r, "1")
    globals()["MODO_ANGULOS"] = prev_ang

    # --- NUEVO 3 (v5.0): SETUP FIX / SCI / NORM ---
    prev_fmt = globals()["FORMATO_NUM"]
    prev_dec = globals()["FORMATO_DECIMALES"]
    cmd_setup("SETUPFIX2")
    r, *_ = procesar_todo("1/3")
    check("1/3 en FIX2 = 0.33", r, "0.33")
    cmd_setup("SETUPSCI3")
    r, *_ = procesar_todo("123456")
    check("123456 en SCI3 = 1.235E+05", r, "1.235E+05")
    cmd_setup("SETUPNORM")
    r, *_ = procesar_todo("1/3")
    check("1/3 en NORM = 1/3", r, "1/3")
    globals()["FORMATO_NUM"] = prev_fmt
    globals()["FORMATO_DECIMALES"] = prev_dec

    # --- NUEVO 4 (v5.0): STAT regresion lineal y=2x+1 ---
    prev_datos = list(globals()["ESTADISTICA_DATOS"])
    procesar_estadistica("CLEAR")
    for x, y in [(1, 3), (2, 5), (3, 7), (4, 9)]:
        procesar_estadistica(f"X{x},{y}")
    l1, l2, l3 = procesar_estadistica("CALC")
    check("STAT regresion y=2x+1 -> l1 tiene 'a=1'", "a=1" in l1, True)
    check("STAT regresion y=2x+1 -> l2 tiene 'b=2'", "b=2" in l2, True)
    check("STAT regresion y=2x+1 -> r=1", l3, "r=1.0000")
    procesar_estadistica("CLEAR")
    globals()["ESTADISTICA_DATOS"] = prev_datos

    # --- NUEVO 1 (v5.5): distribuciones estadisticas ---
    r1, r2, r3 = cmd_dist("DISTNPD(0,0,1)")
    check("DISTNPD(0,0,1) ~ 0.39894", "0.39894" in r2, True)
    r1, r2, r3 = cmd_dist("DISTBIN(0,10,0.5)")
    check("DISTBIN(0,10,0.5) ~ 0.00098", "0.00098" in r3, True)
    r1, r2, r3 = cmd_dist("DISTPOI(0,1)")
    check("DISTPOI(0,1) ~ 0.36788", "0.36788" in r3, True)

    # --- NUEVO 2 (v5.5): TABLE2 doble funcion ---
    global TABLA_RESULTADO, TABLA_INDICE
    prev_tabla = list(TABLA_RESULTADO)
    r, *_ = cmd_table2("TABLE2X,X^2,0,2,1")
    check("TABLE2 genera 3 filas", len(TABLA_RESULTADO), 3)
    check("TABLE2 fila0 = (0,0,0)", TABLA_RESULTADO[0], (0, 0, 0))
    check("TABLE2 fila2 = (2,2,4)", TABLA_RESULTADO[2], (2, 2, 4))
    TABLA_RESULTADO = prev_tabla

    # --- NUEVO 3 (v5.5): memoria extendida A-Z ---
    check("D en MEMORIA tras extension", "D" in MEMORIA, True)
    check("E NO esta en MEMORIA (es constante)", "E" in MEMORIA, False)
    check("I NO esta en MEMORIA (es imaginaria)", "I" in MEMORIA, False)
    MEMORIA["D"] = 7.0
    r, *_ = procesar_todo("D*2")
    check("variable D funciona en expresiones", r, "14")
    MEMORIA["D"] = 0.0

    # --- NUEVO 4 (v5.5): conversion DMS <-> decimal ---
    r1, r2, r3 = cmd_dms("DMS(10,30,0)")
    check("DMS(10,30,0) = 21/2 (10.5)", r1, "DMS = 21/2")
    r1, r2, r3 = cmd_todms("TODMS(10.5)")
    check("TODMS(10.5) = 10°30'0.0\"", r1, "10\u00b030'0.0\"")

    # --- NUEVO 5 (v5.5): modo SHEET con formulas ---
    prev_sheet = dict(SHEET_DATOS)
    prev_sheet_cursor = list(SHEET_CURSOR)
    SHEET_DATOS.clear()
    SHEET_DATOS["A1"] = "5.0"
    SHEET_DATOS["B1"] = "3.0"
    SHEET_DATOS["C1"] = "=A1+B1*2"
    check("SHEET formula A1+B1*2 = 11", _evaluar_celda("C1"), 11.0)
    SHEET_DATOS["D1"] = "=D1"  # referencia circular directa
    try:
        _evaluar_celda("D1")
        check("SHEET detecta ref. circular", "no lanzó", "error")
    except ValueError:
        check("SHEET detecta ref. circular", "error", "error")
    SHEET_DATOS.clear()
    SHEET_DATOS.update(prev_sheet)
    globals()["SHEET_CURSOR"] = prev_sheet_cursor

    # --- NUEVO 6 (v5.5): polinomio grado 4 ---
    r1, r2, r3 = cmd_cuart("CUART(1,0,-5,0,4)")
    # x^4-5x^2+4 = (x^2-1)(x^2-4) -> raices +-1, +-2 en algun orden
    raices_txt = r1 + " " + r2
    check("CUART x^4-5x^2+4 contiene raiz 1", "X1=1" in raices_txt or "X2=1" in raices_txt, True)
    check("CUART x^4-5x^2+4 contiene raiz 2", "2" in raices_txt, True)

    # --- NUEVO 7 (v5.5): raiz k-esima exacta generalizada ---
    r1, r2, r3 = cmd_raizn("RAIZN(8,3)")
    check("RAIZN(8,3) = 2 (raiz cubica exacta)", r1, "2")
    r1, r2, r3 = cmd_raizn("RAIZN(16,3)")
    check("RAIZN(16,3) = 2*raizN3(2)", r1, "2*raizN3(2)")

    total = pasados + fallados
    print(f"\n=== TEST SUITE PiCalc v5.5 ===")
    for l in log:
        print(l)
    print(f"\nResultado: {pasados}/{total} pasados")
    return (f"Tests: {pasados}/{total}",
            "OK" if fallados == 0 else f"{fallados} fallaron",
            "Ver consola" if not ENTORNO_PICO else "")


# ── 11v4-A. MODULO CMPLX: NUMEROS COMPLEJOS ────────

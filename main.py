# PiCalc OS v5.7 - main.py
# Raspberry Pi Pico / MicroPython | Motor RPN propio (sin eval)
# Arquitectura modular con carga dinámica para minimizar RAM.
#
# Módulos de carga dinámica (se importan solo al activar el modo):
#   pc_stats.py   → STAT (modo 3): regresión, distribuciones
#   pc_matrix.py  → MATRIX (modo 6): álgebra matricial 4x4
#   pc_eqn.py     → EQN (modo 5): ecuaciones grado 2/3/4, sistemas
#   pc_tests.py   → TEST: suite de pruebas (solo en desarrollo)
#
# RAM al arrancar (núcleo solo): ~38-42 KB bytecode
# RAM modo pesado activo (máx):  ~53-58 KB bytecode
# Flash libre estimada:          >1.8 MB (archivos .mpy precompilados)

import gc
import math
import pc_bridge  # puente de dependencias (carga única)
# ── Constantes de cadena frecuentes (evitan strings duplicados en RAM) ──
_E_NODISP  = "Error: No disp"  # bloqueo modo examen
_E_SIN     = "Error Sintaxis"   # expresion invalida
_E_DIM     = "Error Dimension:"  # mismatch matricial
_E_RANGO   = "Error: Rango Max"  # TABLE demasiado grande
_E_PASO0   = "Error: paso=0"     # TABLE/SUM paso nulo
_MOD_CARG  = None               # modulo de carga dinamica activo


try:
    import time  # MicroPython/Pico
except ImportError:
    import time  # CPython
import cmath
import json
# ── 1. DETECCION DE ENTORNO Y HARDWARE ─────────────
try:
    import machine
    import sh1106
    ENTORNO_PICO = True
except ImportError:
    ENTORNO_PICO = False

# ---- Estado global ----
MODO_EXAMEN = True  # True = Modo bloqueado (Clase) | False = CAS / ClassWiz completo
# NUEVO 3 (v5.5): memoria extendida de A-Z. Se excluyen E (constante de
# Euler) e I (unidad imaginaria), ya reservadas en CONSTANTES. El resto
# del alfabeto (24 letras) queda disponible para STO/RCL/SAVE, igual
# que la memoria extendida de la fx-991EX (A,B,C,D,X,Y,M + independ.).
_LETRAS_MEMORIA = [c for c in "ABCDFGHJKLMNOPQRSTUVWXYZ"]
MEMORIA = {c: 0.0 for c in _LETRAS_MEMORIA}
MEMORIA["X"] = 0.0
MEMORIA["Y"] = 0.0
ANS = 0.0
# FIX 3 (v5.1): unificamos las dos listas paralelas de v5.0
# (ESTADISTICA_LISTA / ESTADISTICA_LISTA_Y) en una sola lista de
# tuplas (x, y_o_None). Modo 1-variable (STATADD:v) guarda (v, None);
# modo pareado (STATX<x>,<y>) guarda (x, y). Ver procesar_estadistica().
ESTADISTICA_DATOS = []
ENTRADA_TOKENS = []
CURSOR_POS = 0          # NEW v4.3: indice de insercion dentro de ENTRADA_TOKENS
LIMITE_ESTADISTICA = 50  # cuida la RAM de la Pico

# ── NUEVO 1 (v5.6): HISTORIAL de calculos ─────────────────
try:
    from collections import deque as _deque
    HISTORIAL = _deque(maxlen=20)  # buffer circular O(1), 0 overhead
except ImportError:
    HISTORIAL = []  # CPython o MicroPython sin collections
HIST_MAX   = 20  # buffer circular: entradas antiguas se descartan solas
HIST_INDICE = 0     # fila visible en la vista de historial
EN_HIST    = False  # True = vista de historial abierta

# ── NUEVO (v5.6): submenu DIST y tipo de regresion ─────────
EN_MENU_DIST = False
STAT_REG = "LIN"    # LIN/CUAD/EXP/LOG/POT/INV

# ---- Estado v4.0 ----
MODO_COMPLEJO = False
MATRICES = {"A": None, "B": None, "C": None}
TABLA_RESULTADO = []
TABLA_INDICE = 0  # NUEVO 1 (v5.2): fila actual mostrada al navegar con IZQ/DER

# ---- Estado v4.3: Modo de calculadora (menu MODE) ----
# 1=COMP, 2=CMPLX, 3=STAT, 4=BASE-N, 5=EQN, 6=MATRIX, 7=TABLE, 8=VECTOR
MODO_CALC = 1
MODO_CALC_NOMBRES = {
    1: "COMP", 2: "CMPLX", 3: "STAT",  4: "BASE-N",
    5: "EQN",  6: "MATRIX", 7: "TABLE", 8: "VECTOR",
}
EN_MENU_MODE = False
# NUEVO 3 (v5.2): submenu de tipo de ecuacion, abierto tras elegir
# el modo 5 (EQN) en el menu MODE.
EN_MENU_EQN = False

# ---- Estado v5.5: Modo SHEET (hoja de calculo simplificada) ----
# Grilla de 6 columnas (A-F) x 10 filas. Cada celda guarda o un
# valor literal o una formula string (ej: "=A1+B2*2"). Las formulas
# se evaluan on-demand (sin cache) reusando evaluar_expresion().
SHEET_FILAS = 10
SHEET_COLS = 6  # columnas A..F
SHEET_DATOS = {}      # clave "A1".."F10" -> string crudo (numero o formula)
SHEET_CURSOR = ["A", 1]  # [columna, fila] actual del cursor de hoja
EN_MODO_SHEET = False

# FIX 4 (v4.4): variable de seleccion separada del MODO_CALC confirmado.
# IZQ/DER mueven _SELECCION_MENU sin pisar MODO_CALC hasta que el
# usuario confirme con IGUAL o un digito (igual que la Casio fisica).
_SELECCION_MENU = 1

# ---- Constantes de configuracion (v4.4) ----
# FIX 8: el denominador maximo para fracciones continuas esta documentado.
# 1000 es apropiado para la Pico (264KB RAM): cubre todas las fracciones
# de uso practico (1/999 y menores) sin exceder recursos.
FRACCION_DEN_MAX = 1000

# FIX 9: el tope de TABLE es independiente de LIMITE_ESTADISTICA.
# Cambiar uno no afecta al otro, evitando overflow silencioso de RAM.
TABLA_MAX_FILAS = 45  # igual que la Casio fx-991 ClassWiz

# FIX 10: lista explicita de que bloquea MODO_EXAMEN.
# Cada funcion avanzada consulta esta constante, no chequeos dispersos.
# Funciones bloqueadas: SOLVE, DERIV, INT, matrices, factorizacion,
#   polinomios, distribuciones, TABLE, BASE-N, CMPLX.
BYPASS_RESTRICCIONES = frozenset({
    "SOLVE", "DERIV", "INT", "MAT2", "MAT3", "DOT", "CROSS",
    "MATDEF", "MATADD", "MATMUL", "MATTRANS", "MATDET", "MATINV",
    "PRIMOS", "CUAD", "CUB", "CUART", "TABLE", "TABLE2", "BIN", "OCT", "HEX",
    "AND", "OR", "XOR", "NOT", "CMPLX", "DIST", "SHEET", "RAIZN",
    "SUM", "PROD", "CONV",   # NUEVO v5.6
})

display = None
if ENTORNO_PICO:
    try:
        i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
        display = sh1106.SH1106_I2C(128, 64, i2c)
        display.sleep(False)
    except Exception:
        pass


# ── 2. MATRIZ DE TECLADO FISICO (6 filas x 8 columnas = 48 teclas) ─
# Filas -> salidas digitales (se activan una a la vez).
# Columnas -> entradas con pull-down (leen si la fila activa llega).
PINES_FILAS = [6, 7, 8, 9, 10, 11]
PINES_COLUMNAS = [12, 13, 14, 15, 16, 17, 18, 19]
DEBOUNCE_MS = 150

filas_io = []
columnas_io = []
if ENTORNO_PICO:
    try:
        # FIX v3.1: Las filas se inicializan en ENTRADA (alta impedancia) en vez
        # de salida LOW. Sólo se pasan a OUT/HIGH durante el escaneo de esa fila.
        # Esto evita el cortocircuito GPIO si dos teclas de la misma columna se
        # presionan al mismo tiempo (un pin OUT-HIGH vs otro OUT-LOW = destrucción).
        filas_io = [machine.Pin(p, machine.Pin.IN) for p in PINES_FILAS]
        columnas_io = [machine.Pin(p, machine.Pin.IN, machine.Pin.PULL_DOWN) for p in PINES_COLUMNAS]
    except Exception:
        filas_io = []
        columnas_io = []

# Capa principal: cada celda es el TOKEN inyectado en ENTRADA_TOKENS o
# un comando especial (AC, DEL, IGUAL, BYPASS, STO, RCL, 2ND).
# NEW v4.3: teclas de navegacion IZQUIERDA, DERECHA y MODE agregadas.
LAYOUT_TECLADO = [
    ["7", "8", "9", "(", ")", "DEL", "AC", "2ND"],
    ["4", "5", "6", "*", "/", "^", "%", "STO"],
    ["1", "2", "3", "+", "-", ",", "ANS", "RCL"],
    ["0", ".", "X", "PI", "E", "SIN(", "COS(", "TAN("],
    ["A", "B", "C", "Y", "=", "IGUAL", "BYPASS", "SQRT("],
    ["LN(", "LOG(", "EXP(", "ABS(", "ASIN(", "ACOS(", "ATAN(", "RAIZ("],
    # v5.5: SHEETUP/SHEETDOWN (navegacion de filas en modo SHEET)
    ["IZQ", "DER", "MODE", "SETUP", "SHEETUP", "SHEETDOWN", "", ""],
]

# Capa secundaria (tecla 2ND/SHIFT): funciones avanzadas poco usadas.
LAYOUT_TECLADO_2ND = [
    ["SOLVE", "DERIV", "INT", "STAT", "MAT2(", "MAT3(", "DOT(", "CROSS("],
    ["POL(", "REC(", "PRIMOS", "MCD", "MCM", "RANINT(", "SINH(", "COSH("],
    ["TANH(", "CMPLX", "CUAD(", "CUB(", "TABLE", "BIN(", "OCT(", "HEX("],
    ["MATDEF", "MATADD", "MATMUL", "MATTRANS", "MATDET", "MATINV", "SAVE", "TEST"],
    ["FACT(", "NPR(", "NCR(", "CONJ(", "ARG(", "STATX", "STATCLEAR", "VEC2("],
    ["VEC3(", "SIMU2(", "SIMU3(", "SIMU4(", "MATEDIT", "STATCUAD", "STATEXP", "STATLOG"],
    # v5.6: HIST, SUM, PROD, CONV, AFRAC, distribuciones nuevas
    ["DIST", "TABLE2", "DMS(", "TODMS(", "SHEET", "CUART(", "RAIZN(", "HIST"],
    ["SUM(", "PROD(", "CONV(", "AFRAC(", "MOD(", "DISTT(", "DISTCHI(", "DISTF("],
    ["DISTHG(", "", "", "", "", "", "", ""],
]

_ultimo_estado = {}
_ultimo_cambio = {}
MODO_2ND = False

def _ahora_ms():
    if ENTORNO_PICO:
        return time.ticks_ms()
    return int(time.time() * 1000)

def _diferencia_ms(ahora, antes):
    if ENTORNO_PICO:
        return time.ticks_diff(ahora, antes)
    return ahora - antes

def escanear_teclado():
    """Recorre la matriz fila por fila (con antirebote) y devuelve el
    token de la primera tecla nueva detectada, o None si no hay nada.

    FIX v3.1 - Modo alta impedancia entre filas:
      Cada fila se configura como OUT/HIGH solo mientras se la escanea;
      antes y después queda como IN (alta impedancia / flotante).
      Esto elimina el cortocircuito OUT-HIGH vs OUT-LOW que ocurre cuando
      el usuario presiona dos teclas de la misma columna simultáneamente.
    """
    global MODO_2ND
    if not (filas_io and columnas_io):
        return None

    for i, fila in enumerate(filas_io):
        # Activar SÓLO esta fila como salida HIGH
        fila.init(machine.Pin.OUT)
        fila.value(1)

        for j, col in enumerate(columnas_io):
            estado = col.value()
            clave = (i, j)
            anterior = _ultimo_estado.get(clave, 0)
            ahora = _ahora_ms()

            if estado == 1 and anterior == 0:
                ultimo_cambio = _ultimo_cambio.get(clave, 0)
                if _diferencia_ms(ahora, ultimo_cambio) > DEBOUNCE_MS:
                    _ultimo_estado[clave] = 1
                    _ultimo_cambio[clave] = ahora
                    # Volver a alta impedancia ANTES de retornar
                    fila.init(machine.Pin.IN)
                    capa = LAYOUT_TECLADO_2ND if MODO_2ND else LAYOUT_TECLADO
                    # FIX 3 (v4.4): verificar que (i,j) exista en la capa antes
                    # de leer el token. Ruido electrico o filas extra no deben
                    # causar IndexError ni togglear MODO_2ND accidentalmente.
                    if i >= len(capa) or j >= len(capa[i]):
                        return None
                    token = capa[i][j]
                    if token == "2ND":
                        MODO_2ND = not MODO_2ND  # solo si es exactamente "2ND"
                        return None
                    if token != "":
                        MODO_2ND = False
                    return token if token != "" else None
            elif estado == 0 and anterior == 1:
                _ultimo_estado[clave] = 0

        # Devolver a alta impedancia al terminar de escanear esta fila
        fila.init(machine.Pin.IN)
    return None


# ── 3. CAPA DE SALIDA / RENDERIZADO VISUAL ─────────
def renderizar_pantalla(linea_eq, l2="", l3="", l4="", cursor_pos=None):
    """Renderiza hasta 4 lineas para OLED 128x64 o consola PC.
    NEW v4.3: acepta cursor_pos (indice de caracter en linea_eq) para
    mostrar el cursor '|'. El scroll horizontal se centra alrededor
    del cursor en vez de mostrar siempre el extremo derecho."""
    ANCHO_OLED = 16

    # Insertar cursor visual '|' en la posicion indicada
    if cursor_pos is not None:
        linea_con_cursor = linea_eq[:cursor_pos] + "|" + linea_eq[cursor_pos:]
    else:
        linea_con_cursor = linea_eq + "|"

    # Scroll horizontal centrado en el cursor para OLED
    cur_idx = cursor_pos if cursor_pos is not None else len(linea_eq)
    # Ajustar el indice considerando el caracter "|" insertado
    cur_en_str = cur_idx  # posicion del "|" en linea_con_cursor
    inicio_oled = max(0, cur_en_str - ANCHO_OLED // 2)
    vista_eq_oled = linea_con_cursor[inicio_oled: inicio_oled + ANCHO_OLED]

    if ENTORNO_PICO and display:
        display.fill(0)
        display.text(vista_eq_oled, 0, 2, 1)
        display.text(l2[:ANCHO_OLED], 0, 18, 1)
        display.text(l3[:ANCHO_OLED], 0, 34, 1)
        display.text(l4[:ANCHO_OLED], 0, 50, 1)
        display.show()
    else:
        ANCHO_CONSOLA = 28
        inicio_con = max(0, cur_en_str - ANCHO_CONSOLA // 2)
        vista_eq_consola = linea_con_cursor[inicio_con: inicio_con + ANCHO_CONSOLA]
        print("\n" + "=" * 34)
        print("| [PANTALLA CASIO CLASSWIZ]        |")
        print("-" * 34)
        print(f"| L1: {vista_eq_consola:<28} |")
        print(f"| L2: {l2:<28} |")
        print(f"| L3: {l3:<28} |")
        print(f"| L4: {l4:<28} |")
        print("=" * 34)


# ── 4. AYUDANTES MATEMATICOS Y ALGEBRA BASICA ──────
def mcd(a, b):
    while b:
        a, b = b, a % b
    return a

def mcm(a, b):
    return abs(a * b) // mcd(a, b) if (a and b) else 0

def factorizar_primos(n):
    if MODO_EXAMEN:
        return _E_NODISP
    try:
        num = int(float(n))
        if num < 2:
            return str(num)
        factores = []
        d = 2
        while d * d <= num:
            while (num % d) == 0:
                factores.append(str(d))
                num //= d
            d += 1
        if num > 1:
            factores.append(str(num))
        return " * ".join(factores)
    except Exception:
        return "Error"

# 4b. COMBINATORIA: FACT (n!), NPR (permutaciones), NCR (combinaciones)
#     (NUEVO 1 - v5.0)
LIMITE_FACTORIAL = 170  # 170! < 1.8e308 (limite de un float64); 171! desborda

def calcular_factorial(n):
    """n! para entero 0 <= n <= LIMITE_FACTORIAL. Lanza ValueError si
    n no es un entero no negativo o excede el limite (overflow de float)."""
    if n < 0 or n != int(n):
        raise ValueError("FACT: n debe ser entero >= 0")
    n = int(n)
    if n > LIMITE_FACTORIAL:
        raise ValueError(f"FACT: n>{LIMITE_FACTORIAL} desborda")
    resultado = 1
    for i in range(2, n + 1):
        resultado *= i
    return float(resultado)

def calcular_npr(n, r):
    """Permutaciones: nPr = n! / (n-r)!  con 0 <= r <= n."""
    if n < 0 or r < 0 or n != int(n) or r != int(r):
        raise ValueError("NPR: n,r deben ser enteros >= 0")
    n, r = int(n), int(r)
    if r > n:
        raise ValueError("NPR: requiere r<=n")
    if n > LIMITE_FACTORIAL:
        raise ValueError(f"NPR: n>{LIMITE_FACTORIAL} desborda")
    resultado = 1
    for i in range(n - r + 1, n + 1):
        resultado *= i
    return float(resultado)

def calcular_ncr(n, r):
    """Combinaciones: nCr = n! / (r! * (n-r)!)  con 0 <= r <= n.
    Calculado de forma incremental para evitar factoriales grandes
    cuando r es pequeno (ej: NCR(170,2) no necesita 170!)."""
    if n < 0 or r < 0 or n != int(n) or r != int(r):
        raise ValueError("NCR: n,r deben ser enteros >= 0")
    n, r = int(n), int(r)
    if r > n:
        raise ValueError("NCR: requiere r<=n")
    r = min(r, n - r)  # simetria: nCr = nC(n-r), usar el r mas chico
    resultado = 1
    for i in range(r):
        resultado = resultado * (n - i) // (i + 1)
    return float(resultado)


# ── 5. MOTOR DE EXPRESIONES (SHUNTING-YARD + RPN) ──

def _conj_impl(x): return x.conjugate() if isinstance(x, complex) else x
def _arg_stub(x): return 0.0

# Aliases locales de math (reduce lookup en FUNC_MAP y evaluar_rpn)
_sin = math.sin;  _cos = math.cos;  _tan = math.tan
_asin = math.asin; _acos = math.acos; _atan = math.atan
_sinh = math.sinh; _cosh = math.cosh; _tanh = math.tanh
_log = math.log;  _log10 = math.log10; _exp = math.exp
_sqrt = math.sqrt; _abs = abs; _floor = math.floor
_pi = math.pi;    _e = math.e

FUNC_MAP = {
    # --- Trigonometricas directas (argumento en la unidad activa) ---
    "SIN":  {"fn": _sin, "angulo": "in"},
    "COS":  {"fn": _cos, "angulo": "in"},
    "TAN":  {"fn": _tan, "angulo": "in"},
    # --- Trigonometricas inversas (resultado en la unidad activa) ---
    "ASIN": {"fn": _asin, "angulo": "out"},
    "ACOS": {"fn": _acos, "angulo": "out"},
    "ATAN": {"fn": _atan, "angulo": "out"},
    # --- Sin dependencia del modo angular ---
    "SINH": {"fn": _sinh, "angulo": None},
    "COSH": {"fn": _cosh, "angulo": None},
    "TANH": {"fn": _tanh, "angulo": None},
    "LN":   {"fn": _log,   "angulo": None},
    "LOG":  {"fn": _log10, "angulo": None},
    "EXP":  {"fn": _exp,   "angulo": None},
    "SQRT": {"fn": _sqrt,  "angulo": None},
    "RAIZ": {"fn": _sqrt,  "angulo": None},
    "ABS":  {"fn": abs,        "angulo": None},
    # --- Especiales (bloque propio en evaluar_rpn, no usan "fn") ---
    "FACT": {"fn": calcular_factorial, "angulo": None, "especial": "fact"},
    "CONJ": {"fn": None, "angulo": None, "especial": "conj"},
    "ARG":  {"fn": None, "angulo": None, "especial": "arg"},
}

CONSTANTES = {"PI": math.pi, "E": math.e, "I": 1j}  # I = unidad imaginaria

PRECEDENCIA = {"+": 2, "-": 2, "*": 3, "/": 3, "%": 3, "^": 5, "NEG": 6, "NEGL": 4}
ASOC_DERECHA = ("^", "NEG", "NEGL")

def tokenizar(expr):
    """Convierte un string en una lista de tokens (NUM, VAR, FUNC, OP)."""
    tokens = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c == " ":
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            puntos = 0  # FIX 1 (v4.4): solo se permite un punto decimal por numero
            while j < n and (expr[j].isdigit() or expr[j] == "."):
                if expr[j] == ".":
                    puntos += 1
                    if puntos > 1:
                        raise ValueError(f"Numero invalido: {expr[i:j+1]}")
                j += 1
            tokens.append(("NUM", float(expr[i:j])))
            i = j
            continue
        if c.isalpha():
            j = i
            while j < n and expr[j].isalpha():
                j += 1
            nombre = expr[i:j]
            if nombre in FUNC_MAP:
                tokens.append(("FUNC", nombre))
            elif nombre in CONSTANTES:
                tokens.append(("NUM", CONSTANTES[nombre]))
            elif nombre == "ANS" or nombre in MEMORIA:
                tokens.append(("VAR", nombre))
            else:
                raise ValueError("Token desconocido: " + nombre)
            i = j
            continue
        if c in "+-*/^%(),":
            tokens.append(("OP", c))
            i += 1
            continue
        raise ValueError("Caracter no valido: " + c)
    return tokens

def _debe_pop(top_val, op):
    """Decide si el operador en la cima de la pila debe pasar a la salida
    antes de empujar 'op', segun precedencia y asociatividad."""
    prec_top = PRECEDENCIA.get(top_val, 0)
    prec_op = PRECEDENCIA[op]
    if prec_top > prec_op:
        return True
    if prec_top == prec_op and op not in ASOC_DERECHA:
        return True
    return False

def a_rpn(tokens):
    """Algoritmo Shunting-yard: convierte tokens infijos a notacion RPN."""
    salida = []
    pila = []
    prev = None  # token anterior, usado para detectar el menos unario

    for (tipo, val) in tokens:
        if tipo in ("NUM", "VAR"):
            salida.append((tipo, val))
        elif tipo == "FUNC":
            pila.append((tipo, val))
        elif tipo == "OP":
            if val == "(":
                pila.append((tipo, val))
            elif val == ")":
                while pila and pila[-1] != ("OP", "("):
                    salida.append(pila.pop())
                if not pila:
                    raise ValueError("Parentesis desbalanceados")
                pila.pop()  # descarta "("
                if pila and pila[-1][0] == "FUNC":
                    salida.append(pila.pop())
            elif val == ",":
                while pila and pila[-1] != ("OP", "("):
                    salida.append(pila.pop())
            elif val == "-" and (prev is None or (prev[0] == "OP" and prev[1] != ")") or prev[0] == "FUNC"):
                neg_tras_potencia = prev is not None and prev == ("OP", "^")
                op_neg = "NEG" if neg_tras_potencia else "NEGL"
                while pila and pila[-1][0] == "OP" and pila[-1][1] != "(" and _debe_pop(pila[-1][1], op_neg):
                    salida.append(pila.pop())
                pila.append(("OP", op_neg))
            else:
                op = val
                while pila and pila[-1][0] == "OP" and pila[-1][1] != "(" and _debe_pop(pila[-1][1], op):
                    salida.append(pila.pop())
                pila.append(("OP", op))
        prev = (tipo, val)

    while pila:
        top = pila.pop()
        if top == ("OP", "("):
            raise ValueError("Parentesis desbalanceados")
        salida.append(top)

    return salida

def evaluar_rpn(rpn, variables=None):
    """Evalua una lista de tokens en notacion RPN usando una pila.
    En MODO_COMPLEJO usa cmath para SQRT y funciones trigonometricas,
    permitiendo resultados complejos (ej: SQRT(-1) = i)."""
    if variables is None:
        variables = {}
    pila = []

    # Mapa de funciones cmath para MODO_COMPLEJO
    FUNC_MAP_CMPLX = {
        "SQRT": cmath.sqrt, "RAIZ": cmath.sqrt,
        "LN":   cmath.log,  "LOG":  lambda x: cmath.log(x, 10),
        "EXP":  cmath.exp,
        "SIN":  cmath.sin,  "COS":  cmath.cos,  "TAN": cmath.tan,
        "ASIN": cmath.asin, "ACOS": cmath.acos, "ATAN": cmath.atan,
    }

    for (tipo, val) in rpn:
        if tipo == "NUM":
            pila.append(val)
        elif tipo == "VAR":
            if val not in variables:
                raise ValueError("Variable no definida: " + val)
            pila.append(variables[val])  # puede ser complex si MODO_COMPLEJO
        elif tipo == "FUNC":
            arg = pila.pop()
            info = FUNC_MAP[val]
            especial = info.get("especial")

            # NUEVO 1 (v5.0): FACT - factorial, siempre real, valida entero.
            if especial == "fact":
                if isinstance(arg, complex):
                    raise ValueError("FACT: no soporta complejos")
                pila.append(calcular_factorial(arg))
                continue

            # NUEVO 2 (v5.0): CONJ y ARG - operan sobre real O complejo.
            if especial == "conj":
                pila.append(arg.conjugate() if isinstance(arg, complex) else arg)
                continue
            if especial == "arg":
                if isinstance(arg, complex):
                    angulo_rad = cmath.phase(arg)
                else:
                    angulo_rad = 0.0 if arg >= 0 else math.pi
                # FIX 0 (v5.0): respeta MODO_ANGULOS (ver mas abajo)
                if MODO_ANGULOS == "DEG":
                    pila.append(math.degrees(angulo_rad))
                else:
                    pila.append(angulo_rad)
                continue

            # FIX 0 (v5.0): MODO_ANGULOS="RAD" desactiva la conversion
            # grados<->radianes para las funciones trigonometricas. En
            # v4.5 esta conversion se aplicaba SIEMPRE sin importar
            # MODO_ANGULOS, por lo que SETUPRAD no tenia ningun efecto
            # sobre el motor matematico (solo se guardaba el estado).
            usar_grados = (MODO_ANGULOS == "DEG")
            angulo = info["angulo"]

            if MODO_COMPLEJO and val in FUNC_MAP_CMPLX:
                fn = FUNC_MAP_CMPLX[val]
                # grados -> radianes para trig en modo complejo (solo si DEG)
                if angulo == "in" and usar_grados:
                    arg = cmath.pi * arg / 180
                resultado = fn(arg)
                if angulo == "out" and usar_grados:
                    resultado = cmath.phase(resultado) * 180 / cmath.pi
                elif angulo == "out":
                    resultado = cmath.phase(resultado)
            else:
                fn = info["fn"]
                if angulo == "in" and usar_grados:
                    arg = math.radians(arg)
                resultado = fn(arg)
                if angulo == "out" and usar_grados:
                    resultado = math.degrees(resultado)
            pila.append(resultado)
        elif tipo == "OP":
            if val in ("NEG", "NEGL"):
                a = pila.pop()
                pila.append(-a)
            else:
                b = pila.pop()
                a = pila.pop()
                if val == "+":
                    pila.append(a + b)
                elif val == "-":
                    pila.append(a - b)
                elif val == "*":
                    pila.append(a * b)
                elif val == "/":
                    # FIX 2 (v4.4): division por cero con mensaje explicito
                    if not isinstance(b, complex) and abs(b) < 1e-12:
                        raise ValueError("Division por cero")
                    pila.append(a / b)
                elif val == "%":
                    pila.append(a % b)
                elif val == "^":
                    pila.append(a ** b)
                else:
                    raise ValueError("Operador desconocido: " + val)
    if len(pila) != 1:
        raise ValueError("Expresion invalida")
    return pila[0]

def evaluar_expresion(expr, variables=None):
    """Punto de entrada unico: tokeniza, convierte a RPN y evalua.
    Reemplaza todo uso de eval() en el motor matematico."""
    tokens = tokenizar(expr)
    rpn = a_rpn(tokens)
    return evaluar_rpn(rpn, variables)

def variables_actuales(extra=None):
    """Diccionario de variables disponibles para el motor: memoria (A,B,C,X,Y)
    + ANS (ultimo resultado), opcionalmente sobreescrito/extendido por 'extra'."""
    datos = dict(MEMORIA)
    datos["ANS"] = ANS
    if extra:
        datos.update(extra)
    return datos


# ── 6. NUCLEO MATEMATICO AVANZADO ──────────────────
def calcular_raiz_analitica(valor_str):
    try:
        valor = evaluar_expresion(valor_str.upper(), variables_actuales())
        if valor < 0:
            return "Error: Negativo"
        raiz = round(valor ** 0.5, 10)  # tolerancia de punto flotante
        if MODO_EXAMEN or raiz.is_integer():
            return str(int(raiz)) if raiz.is_integer() else f"{raiz:.5f}"

        # Extraccion analitica de factores (ej: 2*v(3))
        fuera, dentro = 1, int(round(valor, 10))
        d = 2
        while d * d <= dentro:
            if dentro % (d * d) == 0:
                fuera *= d
                dentro //= (d * d)
            else:
                d += 1
        return f"{fuera}*v({dentro})" if fuera > 1 else f"v({dentro})"
    except Exception:
        return "Error"


# ── 6b. RAIZ K-ESIMA EXACTA GENERALIZADA (NUEVO 7 - v5.5) ──
# RAIZ()/calcular_raiz_analitica() ya hacia esta extraccion de factores
# para raiz cuadrada (sqrt(12) = 2*sqrt(3)). RAIZN(n,k) generaliza el
# mismo principio a la raiz k-esima: extrae todo factor cuya potencia
# k-esima divide exactamente a n, dejando el resto bajo el radical.
# Ej: RAIZN(16,3) = raiz cubica de 16 = 2 * raiz cubica de 2.
def cmd_raizn(cmd):
    """RAIZN(n,k) -> raiz k-esima de n, exacta si es posible o con
    extraccion analitica de factores (estilo Casio) si no lo es.
    Soporta n negativo cuando k es impar (raiz real negativa)."""
    try:
        nums = extraer_numeros(cmd, "RAIZN")
        if len(nums) != 2:
            return "Use RAIZN(", "n,k)", ""
        n, k = nums[0], int(nums[1])
        if k <= 0:
            return "Error: k debe", "ser entero > 0", ""
        if n < 0 and k % 2 == 0:
            return "Error: raiz par", "de negativo", ""

        signo = -1 if n < 0 else 1
        n_abs = abs(n)

        raiz = round(n_abs ** (1.0 / k), 10)
        raiz_redonda = round(raiz)
        if abs(raiz_redonda ** k - n_abs) < 1e-6:
            return str(signo * raiz_redonda), "", ""

        if MODO_EXAMEN:
            return f"{signo * raiz:.5f}", "", ""

        # Extraccion analitica: busca el mayor 'fuera' tal que
        # fuera^k divide exactamente a n_abs, dejando 'dentro' bajo
        # la raiz k-esima (factorizacion por tanteo, like sqrt-case).
        n_int = int(round(n_abs, 10))
        fuera, dentro = 1, n_int
        d = 2
        while d ** k <= dentro:
            while dentro % (d ** k) == 0:
                fuera *= d
                dentro //= (d ** k)
            d += 1

        signo_txt = "-" if signo < 0 else ""
        if dentro == 1:
            return f"{signo_txt}{fuera}", "", ""
        base = f"raizN{k}({dentro})"
        expr = f"{fuera}*{base}" if fuera > 1 else base
        return f"{signo_txt}{expr}", "", ""
    except Exception as ex:
        return f"Error RAIZN: {ex}"[:16], "", ""

def decimal_a_fraccion(val):
    # Numeros complejos: formatear al estilo Casio "a+bi" sin parentesis ni "j"
    if isinstance(val, complex):
        r, im = round(val.real, 8), round(val.imag, 8)

        def _fmt_parte(v):
            """Formatea un float como entero si es exacto, o decimal si no."""
            if v == int(v):
                return str(int(v))
            return f"{v:.5f}"

        if r == 0 and im == 0:
            return "0"
        if r == 0:
            # Solo parte imaginaria: "-3i" o "2i" o "-i" o "i"
            signo = "-" if im < 0 else ""
            mag = abs(im)
            return f"{signo}{'i' if mag == 1 else _fmt_parte(mag) + 'i'}"
        if im == 0:
            return _fmt_parte(r)
        # Ambas partes no nulas: "2+3i", "2-3i", "2+i", "2-i"
        signo = "+" if im > 0 else "-"
        mag = abs(im)
        im_str = "i" if mag == 1 else _fmt_parte(mag) + "i"
        return f"{_fmt_parte(r)}{signo}{im_str}"

    if isinstance(val, float):
        if math.isnan(val):
            return "Error: NaN"
        if math.isinf(val):
            return "Error: Inf" if val > 0 else "Error: -Inf"

    # NUEVO 3 (v5.0): FIX/SCI fuerzan un formato fijo, salteando el
    # chequeo de entero y la aproximacion a fraccion de NORM. Los
    # complejos arriba NO se ven afectados (siempre usan el estilo
    # Casio "a+bi"); FIX/SCI son solo para el camino "real" de abajo.
    if FORMATO_NUM == "FIX":
        try:
            return f"{val:.{FORMATO_DECIMALES}f}"
        except Exception:
            return f"{val:.5f}"
    # NUEVO 4 (v5.6): notacion de ingenieria (exponente multiplo de 3)
    if FORMATO_ENG:
        try:
            return _fmt_eng(val)
        except Exception:
            return f"{val:.5g}"

    if FORMATO_NUM == "SCI":
        try:
            # FIX 2 (v5.2): "E" mayuscula (estilo Casio "1.235E+05")
            # en vez de "e" minuscula (estilo Python "1.235e+05").
            return f"{val:.{FORMATO_DECIMALES}E}"
        except Exception:
            return f"{val:.5E}"

    # FIX v4.2: el chequeo de entero y la aproximacion a fraccion se aplican
    # SIEMPRE, incluso en MODO_EXAMEN. Antes, en examen (modo por defecto),
    # todo numero real pasaba directo a "{val:.5f}" sin filtrar los .0 ni
    # intentar fraccion, por lo que 2+3*4 mostraba "14.00000" en vez de "14".
    try:
        val = round(val, 10)
        if isinstance(val, int) or val.is_integer():
            return str(int(val))

        signo = -1 if val < 0 else 1
        x = abs(val)
        h_prev, h_prev2 = 1, 0
        k_prev, k_prev2 = 0, 1
        resto = x
        num, den = 0, 1
        for _ in range(20):
            entero = int(resto)
            h_cur = entero * h_prev + h_prev2
            k_cur = entero * k_prev + k_prev2
            num, den = h_cur, k_cur
            if den == 0 or den > FRACCION_DEN_MAX:
                num, den = h_prev, k_prev
                break
            frac = resto - entero
            if abs(x - num / den) < 1e-9:
                break
            if frac == 0:
                break
            resto = 1 / frac
            h_prev2, h_prev = h_prev, h_cur
            k_prev2, k_prev = k_prev, k_cur
        if den != 0 and den < FRACCION_DEN_MAX and abs(x - num / den) < 1e-9:
            return f"{signo * num}/{den}"
        return f"{val:.5f}"
    except Exception:
        return f"{val:.5f}"


# ── 6c. STUBS DE CARGA DINÁMICA (pc_stats / pc_matrix / pc_eqn) ──
def _cargar_stats():
    """Carga pc_stats.py bajo demanda y devuelve el módulo.
    Uso: m = _cargar_stats(); m.procesar_estadistica(cmd); del m; gc.collect()
    En PC (desarrollo) también funciona si pc_stats.py está en el path."""
    global _MOD_CARG
    import pc_stats as _s
    _MOD_CARG = _s
    return _s

def procesar_estadistica(comando):
    m = _cargar_stats()
    try:
        return m.procesar_estadistica(comando)
    finally:
        pass  # mantener en RAM mientras el modo STAT siga activo

def calcular_regresion(datos, tipo):
    m = _cargar_stats()
    return m.calcular_regresion(datos, tipo)

def cmd_dist(cmd):
    m = _cargar_stats()
    return m.cmd_dist(cmd)

def cmd_dist_ext(cmd):
    m = _cargar_stats()
    return m.cmd_dist_ext(cmd)

def _liberar_stats():
    global _MOD_CARG
    import sys
    for k in list(sys.modules.keys()):
        if k == 'pc_stats':
            del sys.modules[k]
    _MOD_CARG = None
    gc.collect()

def _cargar_matrix():
    global _MOD_CARG
    import pc_matrix as _m
    _MOD_CARG = _m
    return _m

def cmd_matdef(cmd):   return _cargar_matrix().cmd_matdef(cmd)
def cmd_matadd(cmd):   return _cargar_matrix().cmd_matadd(cmd)
def cmd_matmul(cmd):   return _cargar_matrix().cmd_matmul(cmd)
def cmd_mattrans(cmd): return _cargar_matrix().cmd_mattrans(cmd)
def cmd_matdet(cmd):   return _cargar_matrix().cmd_matdet(cmd)
def cmd_matinv(cmd):   return _cargar_matrix().cmd_matinv(cmd)
def cmd_matedit(cmd):  return _cargar_matrix().cmd_matedit(cmd)

def _liberar_matrix():
    import sys
    for k in list(sys.modules.keys()):
        if k == 'pc_matrix':
            del sys.modules[k]
    gc.collect()

def _cargar_eqn():
    global _MOD_CARG
    import pc_eqn as _e
    _MOD_CARG = _e
    return _e

def cmd_cuad(cmd):                   return _cargar_eqn().cmd_cuad(cmd)
def cmd_cub(cmd):                    return _cargar_eqn().cmd_cub(cmd)
def cmd_cuart(cmd):                  return _cargar_eqn().cmd_cuart(cmd)
def resolver_sistema_matrices(cmd):  return _cargar_eqn().resolver_sistema_matrices(cmd)
def cmd_simu(cmd):                   return _cargar_eqn().cmd_simu(cmd)

def _liberar_eqn():
    import sys
    for k in list(sys.modules.keys()):
        if k == 'pc_eqn':
            del sys.modules[k]
    gc.collect()

def run_tests():
    """Carga pc_tests.py, ejecuta la suite y libera el módulo."""
    import pc_tests as _t
    try:
        return _t.run_tests()
    finally:
        import sys
        if 'pc_tests' in sys.modules:
            del sys.modules['pc_tests']
        gc.collect()


# ── 7. SOLVER, MATRICES Y VECTORES (ALGEBRA REAL) ──
def resolver_ecuacion_lineal(eq_str):
    """Resuelve f(x) = 0 o f(x) = g(x) mediante Newton-Raphson (25 iter max).

    FIX v3.1 - Transformación segura de la ecuación:
      En vez de eq.replace("=", "-(") + ")" que corrompe paréntesis internos
      (ej: SIN(X)=0.5 → SIN(X-(0.5) — paréntesis del seno queda abierto),
      buscamos el índice EXACTO del "=" de igualdad y construimos la expresión
      como  lhs-(rhs)  respetando la estructura original de ambos lados.
    """
    if MODO_EXAMEN:
        return _E_NODISP
    eq_str = eq_str.upper()

    # Localizar el "=" real (ignorando los que puedan estar dentro de tokens)
    if "=" in eq_str:
        idx = eq_str.index("=")
        lhs = eq_str[:idx]
        rhs = eq_str[idx + 1:]
        eq = f"{lhs}-({rhs})"   # transforma  LHS=RHS  →  LHS-(RHS)
    else:
        eq = eq_str

    x = 1.0
    h = 1e-6
    for _ in range(25):
        try:
            f_x = evaluar_expresion(eq, variables_actuales({"X": x}))
            f_xh = evaluar_expresion(eq, variables_actuales({"X": x + h}))
            derivada = (f_xh - f_x) / h
            if abs(derivada) < 1e-12:
                break
            nuevo_x = x - (f_x / derivada)
            if abs(nuevo_x - x) < 1e-6:
                nuevo_x = round(nuevo_x, 10)
                return f"X = {int(nuevo_x)}" if nuevo_x.is_integer() else f"X = {nuevo_x:.5f}"
            x = nuevo_x
        except Exception:
            break
    return "Sin Solucion Real"

def extraer_numeros(cmd, etiqueta):
    """Extrae una lista de floats entre parentesis (o lo que siga) tras 'etiqueta'."""
    resto = cmd.split(etiqueta, 1)[-1]
    inicio = resto.find("(")
    fin = resto.rfind(")")
    if inicio != -1 and fin != -1 and fin > inicio:
        contenido = resto[inicio + 1:fin]
    else:
        contenido = resto.replace("(", "").replace(")", "")
    return [float(x) for x in contenido.split(",") if x.strip() != ""]

def det2(m):
    """Determinante de una matriz 2x2 dada como [a, b, c, d]."""
    return m[0] * m[3] - m[1] * m[2]

def det3(m):
    """Determinante de una matriz 3x3 dada como [a,b,c, d,e,f, g,h,i]."""
    a, b, c, d, e, f, g, h, i = m
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)

def calcular_derivada(eq, punto_str):
    if MODO_EXAMEN:
        return _E_NODISP
    try:
        eq_u = eq.upper()
        x = evaluar_expresion(punto_str.upper(), variables_actuales())
        h = 1e-5
        f_xh1 = evaluar_expresion(eq_u, variables_actuales({"X": x + h}))
        f_xh2 = evaluar_expresion(eq_u, variables_actuales({"X": x - h}))
        return f"d/dx = {(f_xh1 - f_xh2) / (2 * h):.5f}"
    except Exception:
        return "Error"

def calcular_integral(eq, limites_str):
    """Integral definida usando la Regla de Simpson (100 intervalos)."""
    if MODO_EXAMEN:
        return _E_NODISP
    try:
        eq_u = eq.upper()
        partes = limites_str.split(",")
        lim_inf = evaluar_expresion(partes[0].upper(), variables_actuales())
        lim_sup = evaluar_expresion(partes[1].upper(), variables_actuales())
        n = 100
        h = (lim_sup - lim_inf) / n
        suma = (evaluar_expresion(eq_u, variables_actuales({"X": lim_inf}))
                + evaluar_expresion(eq_u, variables_actuales({"X": lim_sup})))

        for i in range(1, n):
            x = lim_inf + i * h
            peso = 4 if i % 2 != 0 else 2
            suma += peso * evaluar_expresion(eq_u, variables_actuales({"X": x}))
        return f"INT = {(suma * h / 3):.5f}"
    except Exception:
        return "Error"


# ── 9. ESTADISTICA BASADA EN LISTAS (STAT) ─────────
def comando_sto(cmd):
    """'<expr>STOA' guarda el valor de <expr> (o de ANS si esta vacio) en A."""
    global ANS
    partes = cmd.split("STO")
    expr_part = partes[0].strip()
    resto = partes[1].strip() if len(partes) > 1 else ""
    var = resto[0:1]
    if var not in MEMORIA:
        # NUEVO 3 (v5.5): mensaje actualizado, ahora son A-Z menos E/I.
        return "Error: use STO A-Z"
    try:
        valor = ANS if expr_part == "" else evaluar_expresion(expr_part, variables_actuales())
        MEMORIA[var] = valor
        ANS = valor
        return f"{var} = {decimal_a_fraccion(valor)}"
    except Exception:
        return _E_SIN

def comando_rcl(cmd):
    """'RCLA' recupera el valor guardado en A y lo deja como resultado/ANS."""
    global ANS
    partes = cmd.split("RCL")
    resto = partes[1].strip() if len(partes) > 1 else ""
    var = resto[0:1]
    if var not in MEMORIA:
        return "Error: use RCL A-Z"
    ANS = MEMORIA[var]
    return f"{var} = {decimal_a_fraccion(MEMORIA[var])}"


# ── 10v4.5-A. PERSISTENCIA EN FLASH (NUEVO 1 - v4.5) ─
_RUTA_ESTADO = "/picalc_state.json" if ENTORNO_PICO else "./picalc_state.json"

try:
    import ujson as _json_mod   # MicroPython
except ImportError:
    import json as _json_mod    # CPython (PC / tests)

def _serializar_valor(v):
    """Convierte un valor (float, complex, None) a formato JSON seguro."""
    if isinstance(v, complex):
        return {"__complex__": True, "r": v.real, "i": v.imag}
    return v

def _deserializar_valor(v):
    """Reconstruye un valor desde su representacion JSON."""
    if isinstance(v, dict) and v.get("__complex__"):
        return complex(v["r"], v["i"])
    return v

def guardar_estado():
    """Guarda MEMORIA, ANS, modos, SETUP y matrices en flash/disco.
    Llamar con el token SAVE (capa 2ND del teclado) o al apagar."""
    try:
        estado = {
            "memoria": {k: _serializar_valor(v) for k, v in MEMORIA.items()},
            "ans": _serializar_valor(ANS),
            "modo_calc": MODO_CALC,
            "modo_complejo": MODO_COMPLEJO,
            # FIX 1 (v5.1, CRITICO): antes SETUPRAD/SETUPFIX/SETUPSCI se
            # perdian al reiniciar porque no se incluian aqui.
            "modo_angulos": MODO_ANGULOS,
            "formato_num": FORMATO_NUM,
            "formato_decimales": FORMATO_DECIMALES,
            "matrices": {
                nombre: {
                    "data": [_serializar_valor(x) for x in m["data"]],
                    "filas": m["filas"],
                    "cols": m["cols"],
                } if m is not None else None
                for nombre, m in MATRICES.items()
            },
            # NUEVO v5.6: historial y tipo de regresion
            "historial": HISTORIAL[-HIST_MAX:],
            "stat_reg":  STAT_REG,
            # NUEVO 5 (v5.5): persistir el contenido de la hoja SHEET.
            # SHEET_DATOS solo guarda strings (numeros o "=formula"),
            # asi que se serializa directo sin pasar por _serializar_valor.
            "sheet_datos": dict(SHEET_DATOS),
        }
        with open(_RUTA_ESTADO, "w") as f:
            _json_mod.dump(estado, f)
        return "Estado guardado"
    except Exception as ex:
        return f"Error save: {ex}"

def cargar_estado():
    """Carga el estado guardado previamente. Se llama al arrancar."""
    global ANS, MODO_CALC, MODO_COMPLEJO, MODO_ANGULOS, FORMATO_NUM, FORMATO_DECIMALES
    global SHEET_DATOS
    try:
        with open(_RUTA_ESTADO, "r") as f:
            estado = _json_mod.load(f)
        for k, v in estado.get("memoria", {}).items():
            if k in MEMORIA:
                MEMORIA[k] = _deserializar_valor(v)
        ANS = _deserializar_valor(estado.get("ans", 0.0))
        MODO_CALC = int(estado.get("modo_calc", 1))
        MODO_COMPLEJO = bool(estado.get("modo_complejo", False))

        # FIX 1 (v5.1): restaurar SETUP, validando valores por si el
        # archivo fue editado a mano o quedo de una version anterior
        # que no guardaba estas claves (estado.get devuelve el valor
        # actual como default, asi que un archivo viejo no rompe nada).
        ang = estado.get("modo_angulos", MODO_ANGULOS)
        if ang in ("DEG", "RAD"):
            MODO_ANGULOS = ang

        fmt = estado.get("formato_num", FORMATO_NUM)
        if fmt in ("NORM", "FIX", "SCI"):
            FORMATO_NUM = fmt

        try:
            FORMATO_DECIMALES = max(0, min(9, int(estado.get("formato_decimales", FORMATO_DECIMALES))))
        except (TypeError, ValueError):
            pass

        for nombre, m in estado.get("matrices", {}).items():
            if nombre in MATRICES and m is not None:
                MATRICES[nombre] = {
                    "data": [_deserializar_valor(x) for x in m["data"]],
                    "filas": m["filas"],
                    "cols": m["cols"],
                }

        # NUEVO 5 (v5.5): restaurar la hoja SHEET si existia en el archivo.
        sheet_guardado = estado.get("sheet_datos", {})
        if isinstance(sheet_guardado, dict):
            SHEET_DATOS.clear()
            SHEET_DATOS.update(sheet_guardado)

        # NUEVO v5.6: restaurar historial y tipo de regresion
        global HISTORIAL, STAT_REG
        hist_raw = estado.get("historial", [])
        if isinstance(hist_raw, list):
            HISTORIAL = [e for e in hist_raw
                         if isinstance(e, dict) and "expr" in e and "res" in e]
        sr = estado.get("stat_reg", STAT_REG)
        if sr in ("LIN", "CUAD", "EXP", "LOG", "POT", "INV"):
            STAT_REG = sr
        return True
    except OSError:
        return False  # archivo no existe todavia (primer arranque)
    except Exception:
        return False


# ── 10v4.5-B. SETUP (FIX 4 - v4.5, completado en v5.0) ─
# En v4.3 la tecla SETUP del layout fisico se definia pero nunca
# se procesaba: el token pasaba al buffer y se evaluaba como
# expresion desconocida. v4.5 agrego cmd_setup() con DEG/RAD;
# v5.0 completa FIX/SCI/NORM (NUEVO 3) y conecta MODO_ANGULOS al
# motor matematico (FIX 0, ver evaluar_rpn).
MODO_ANGULOS = "DEG"  # "DEG" o "RAD" — usado por el motor trig

def _rad_a_modo_angular(rad):
    """Convierte un angulo en radianes al MODO_ANGULOS actual (DEG/RAD).
    Usado por VEC2/VEC3 (NUEVO 2, v5.2) para mostrar angulos de forma
    consistente con SETUP DEG/RAD, igual que ASIN/ACOS/ATAN."""
    return math.degrees(rad) if MODO_ANGULOS == "DEG" else rad

FORMATO_NUM = "NORM"
FORMATO_DECIMALES = 4  # 0-9, usado por FIX y SCI

def _parsear_decimales(resto, predeterminado):
    """FIX 4 (v5.1): extrae la cantidad de decimales (0-9) del texto
    que sigue a FIX/SCI, tomando TODOS los digitos consecutivos (no
    solo el primero) y recortando al rango valido al final.
    Ej: 'SETUPFIX10' -> resto='10' -> 10 -> recortado a 9 (no a 1,
    como pasaba antes al leer solo resto[0]).
    FIX 5 (v5.2): .strip() defensivo al inicio, por si algun futuro
    llamador pasa el resto con espacios sin recortar (los llamadores
    actuales ya hacian .strip() antes de llamar)."""
    resto = resto.strip()
    digitos = ""
    for ch in resto:
        if ch.isdigit():
            digitos += ch
        else:
            break
    n = int(digitos) if digitos else predeterminado
    return max(0, min(9, n))

def cmd_setup(cmd=""):
    """Muestra y permite cambiar la configuracion del sistema.
    SETUP        -> muestra estado actual
    SETUPDEG     -> angulos en grados
    SETUPRAD     -> angulos en radianes
    SETUPFIX<n>  -> formato fijo de n decimales (0-9)
    SETUPSCI     -> notacion cientifica (usa FORMATO_DECIMALES cifras)
    SETUPNORM    -> formato automatico (default, fracciones + 5 dec.)
    Estimacion de RAM: TABLA_MAX_FILAS*2 floats*8 bytes = 720B (seguro)."""
    global MODO_ANGULOS, FORMATO_NUM, FORMATO_DECIMALES
    cmd_u = cmd.upper()

    if "DEG" in cmd_u:
        MODO_ANGULOS = "DEG"
        return "Angulos: DEG", "Grados activados", ""
    if "RAD" in cmd_u:
        MODO_ANGULOS = "RAD"
        return "Angulos: RAD", "Radianes activados", ""

    # NUEVO 3 (v5.0): SETUPFIX<n> -- n decimales fijos (0-9)
    if "FIX" in cmd_u:
        resto = cmd_u.split("FIX")[-1].strip()
        n = _parsear_decimales(resto, FORMATO_DECIMALES)
        FORMATO_NUM = "FIX"
        FORMATO_DECIMALES = n
        return f"Formato: FIX {n}", f"{n} decimales fijos", ""

    # NUEVO 3 (v5.0): SETUPSCI -- notacion cientifica
    if "SCI" in cmd_u:
        resto = cmd_u.split("SCI")[-1].strip()
        n = _parsear_decimales(resto, FORMATO_DECIMALES)
        FORMATO_NUM = "SCI"
        FORMATO_DECIMALES = n
        return f"Formato: SCI {n}", "Notacion cientif.", ""

    # NUEVO 4 (v5.6): SETUPENG -- notacion de ingenieria
    if "ENG" in cmd_u:
        global FORMATO_ENG
        FORMATO_ENG = True
        FORMATO_NUM = "NORM"
        return "Formato: ENG", "exp multiplo de 3", ""

    # NUEVO 3 (v5.0): SETUPNORM -- vuelve al formato automatico v4.x
    if "NORM" in cmd_u:
        FORMATO_NUM = "NORM"
        FORMATO_ENG = False
        return "Formato: NORM", "Fraccion/5 dec.", ""

    # Sin argumento: mostrar estado del sistema
    mats_def = sum(1 for m in MATRICES.values() if m is not None)
    fmt_txt = FORMATO_NUM if FORMATO_NUM == "NORM" else f"{FORMATO_NUM}{FORMATO_DECIMALES}"
    return (f"Ang:{MODO_ANGULOS} Fmt:{fmt_txt}",
            f"Cmplx:{'SI' if MODO_COMPLEJO else 'NO'} Mat:{mats_def}/3",
            f"TABLE max:{TABLA_MAX_FILAS} Den<{FRACCION_DEN_MAX}")


# ── 10v4.5-C. TEST SUITE INTEGRADA (NUEVO 3 - v4.5) ─
def toggle_cmplx():
    """Activa/desactiva el modo numeros complejos."""
    global MODO_COMPLEJO
    MODO_COMPLEJO = not MODO_COMPLEJO
    return f"Modo CMPLX: {'ON' if MODO_COMPLEJO else 'OFF'}"


# ── 11v4-B. MODULO MAT: MATRICES INDEPENDIENTES (hasta 4x4) ─
def _evaluar_poly(coefs, x):
    """Evalua un polinomio (lista de coeficientes, grado mayor primero)
    en x, soportando x complejo via cmath/complex aritmetica nativa."""
    r = 0
    for c in coefs:
        r = r * x + c
    return r


def _derivada_poly(coefs):
    """Devuelve los coeficientes de la derivada del polinomio."""
    n = len(coefs) - 1
    return [c * (n - i) for i, c in enumerate(coefs[:-1])]


def _newton_raiz_compleja(coefs, x0, iters=100, tol=1e-10):
    """Una raiz via Newton-Raphson en el plano complejo, partiendo de x0."""
    deriv = _derivada_poly(coefs)
    x = complex(x0)
    for _ in range(iters):
        fx = _evaluar_poly(coefs, x)
        if abs(fx) < tol:
            break
        dfx = _evaluar_poly(deriv, x)
        if abs(dfx) < 1e-14:
            x += complex(0.1, 0.1)  # escapar de un punto critico
            continue
        x_nuevo = x - fx / dfx
        if abs(x_nuevo - x) < tol:
            x = x_nuevo
            break
        x = x_nuevo
    return x


def _deflactar_poly(coefs, raiz):
    """Division sintetica: divide coefs por (x - raiz), descartando el resto
    (que deberia ser ~0 si 'raiz' es una raiz real del polinomio)."""
    nuevo = [coefs[0]]
    for c in coefs[1:-1]:
        nuevo.append(nuevo[-1] * raiz + c)
    return nuevo


def resolver_polinomio_newton(coefs):
    """Encuentra TODAS las raices de un polinomio via Newton + deflacion
    sucesiva, partiendo de semillas distribuidas en el plano complejo
    para maximizar la chance de converger a raices distintas (igual de
    espiritu al metodo de Durand-Kerner simplificado)."""
    coefs = list(coefs)
    grado = len(coefs) - 1
    raices = []
    semillas = [complex(0.4, 0.9), complex(-0.6, 0.7),
                complex(0.7, -0.4), complex(-0.8, -0.3)]
    activos = coefs
    for k in range(grado):
        semilla = semillas[k % len(semillas)] * (k + 1)
        r = _newton_raiz_compleja(activos, semilla)
        raices.append(r)
        if len(activos) > 2:
            activos = _deflactar_poly(activos, r)
    return raices


def cmd_table(cmd):
    """TABLE<expr>,<inicio>,<fin>,<paso>
    Genera la tabla f(x) para x en [inicio, fin] con paso dado.
    FIX 5 (v4.4): x se calcula como inicio + i*paso en cada iteracion
    para eliminar la acumulacion de error de punto flotante que ocurre
    cuando se suma paso repetidamente.
    FIX 9 (v4.4): el limite usa TABLA_MAX_FILAS (constante independiente
    de LIMITE_ESTADISTICA) para que ambas no se interfieran."""
    global TABLA_RESULTADO, TABLA_INDICE
    if MODO_EXAMEN:
        return _E_NODISP, "", ""
    try:
        resto = cmd.split("TABLE", 1)[-1].strip()
        partes = resto.split(",")
        eq_u = partes[0].upper()
        inicio = evaluar_expresion(partes[1], variables_actuales())
        fin    = evaluar_expresion(partes[2], variables_actuales())
        paso   = evaluar_expresion(partes[3], variables_actuales())

        if paso == 0:
            return _E_PASO0, "", ""

        pasos_estimados = int(abs(fin - inicio) / abs(paso)) + 1
        if pasos_estimados > TABLA_MAX_FILAS:
            return _E_RANGO, f"max {TABLA_MAX_FILAS} filas", f"({pasos_estimados} pedidos)"

        TABLA_RESULTADO = []
        for i in range(pasos_estimados):
            # FIX 5: indice en vez de suma acumulada — sin error iterativo
            x = inicio + i * paso
            if paso > 0 and x > fin + 1e-9:
                break
            if paso < 0 and x < fin - 1e-9:
                break
            fx = evaluar_expresion(eq_u, variables_actuales({"X": x}))
            x_fmt = round(x, 6)
            fx_fmt = round(fx, 6) if not isinstance(fx, complex) else fx
            TABLA_RESULTADO.append((x_fmt, fx_fmt))

        if not TABLA_RESULTADO:
            return "Tabla vacia", "", ""

        # NUEVO 1 (v5.2): arrancar el scroll desde la primera fila.
        TABLA_INDICE = 0
        x0, fx0 = TABLA_RESULTADO[0]
        n = len(TABLA_RESULTADO)
        return (f"TABLE ({n} pts)",
                f"fila 1/{n}: x={x0}",
                f"f(x)={decimal_a_fraccion(fx0)}" + (" IZQ/DER" if n > 1 else ""))
    except Exception as ex:
        return f"Error Table: {ex}", "", ""

def renderizar_tabla_fila():
    """NUEVO 1 (v5.2): muestra la fila TABLA_INDICE de TABLA_RESULTADO.
    Se invoca desde IZQ/DER cuando el buffer de entrada esta vacio,
    permitiendo recorrer fila por fila la ultima TABLE generada
    (en vez de solo ver la primera fila como en v5.1).
    NUEVO 2 (v5.5): cada fila ahora puede ser (x, fx) [TABLE simple]
    o (x, fx, gx) [TABLE2]. Se detecta la longitud de la tupla para
    decidir si mostrar una o dos columnas de resultado."""
    n = len(TABLA_RESULTADO)
    if n == 0:
        renderizar_pantalla("0", cursor_pos=0)
        return
    fila = TABLA_RESULTADO[TABLA_INDICE]
    if len(fila) == 3:
        x, fx, gx = fila
        renderizar_pantalla(f"TABLE fila {TABLA_INDICE + 1}/{n}",
                             f"x={x} f={decimal_a_fraccion(fx)}",
                             f"g={decimal_a_fraccion(gx)}",
                             "IZQ/DER mueve, AC sale")
    else:
        x, fx = fila
        renderizar_pantalla(f"TABLE fila {TABLA_INDICE + 1}/{n}",
                             f"x = {x}",
                             f"f(x) = {decimal_a_fraccion(fx)}",
                             "IZQ/DER mueve, AC sale")


def cmd_table2(cmd):
    """TABLE2<f>,<g>,<inicio>,<fin>,<paso> (NUEVO 2 - v5.5)
    Genera una tabla con DOS funciones f(x) y g(x) evaluadas sobre el
    mismo rango de x, igual que el modo TABLE de la fx-991EX cuando se
    activan ambas funciones f(x) y g(x). Reusa el mismo limite
    TABLA_MAX_FILAS y la misma cache TABLA_RESULTADO que TABLE simple
    (cada fila es (x, fx, gx) en vez de (x, fx))."""
    global TABLA_RESULTADO, TABLA_INDICE
    if MODO_EXAMEN:
        return _E_NODISP, "", ""
    try:
        resto = cmd.split("TABLE2", 1)[-1].strip()
        partes = resto.split(",")
        if len(partes) < 5:
            return "Use TABLE2<f>,", "<g>,ini,fin,paso", ""
        eq_f = partes[0].upper()
        eq_g = partes[1].upper()
        inicio = evaluar_expresion(partes[2], variables_actuales())
        fin    = evaluar_expresion(partes[3], variables_actuales())
        paso   = evaluar_expresion(partes[4], variables_actuales())

        if paso == 0:
            return _E_PASO0, "", ""

        pasos_estimados = int(abs(fin - inicio) / abs(paso)) + 1
        if pasos_estimados > TABLA_MAX_FILAS:
            return _E_RANGO, f"max {TABLA_MAX_FILAS} filas", f"({pasos_estimados} pedidos)"

        TABLA_RESULTADO = []
        for i in range(pasos_estimados):
            x = inicio + i * paso
            if paso > 0 and x > fin + 1e-9:
                break
            if paso < 0 and x < fin - 1e-9:
                break
            vars_x = variables_actuales({"X": x})
            fx = evaluar_expresion(eq_f, vars_x)
            gx = evaluar_expresion(eq_g, vars_x)
            x_fmt = round(x, 6)
            fx_fmt = round(fx, 6) if not isinstance(fx, complex) else fx
            gx_fmt = round(gx, 6) if not isinstance(gx, complex) else gx
            TABLA_RESULTADO.append((x_fmt, fx_fmt, gx_fmt))

        if not TABLA_RESULTADO:
            return "Tabla vacia", "", ""

        TABLA_INDICE = 0
        x0, fx0, gx0 = TABLA_RESULTADO[0]
        n = len(TABLA_RESULTADO)
        return (f"TABLE2 ({n} pts)",
                f"x={x0} f={decimal_a_fraccion(fx0)}",
                f"g={decimal_a_fraccion(gx0)}" + (" IZQ/DER" if n > 1 else ""))
    except Exception as ex:
        return f"Error Table2: {ex}", "", ""


# ── 11v4-E. MODULO BASEN: CONVERSION DE BASE Y LOGICA DE BITS ─
def _evaluar_entero(expr):
    """Evalua una expresion y la convierte a int (truncando al entero mas cercano).
    FIX 1 (v4.5): valida que el resultado no sea complex ni infinito/NaN antes
    de convertir. BIN(3+2I) antes propagaba un TypeError confuso; ahora es
    explicito. También rechaza infinitos que darian int() OverflowError en Pico."""
    val = evaluar_expresion(expr.strip(), variables_actuales())
    if isinstance(val, complex):
        raise ValueError("No soporta complejos en BASE-N")
    if not math.isfinite(val):
        raise ValueError("Resultado no finito")
    return int(val)

def cmd_basen(cmd):
    """BIN(n), OCT(n), HEX(n) -> convierte n a la base indicada.
    AND(a,b), OR(a,b), XOR(a,b), NOT(n) -> logica de bits (32 bits)."""
    try:
        u = cmd.upper()
        if u.startswith("BIN"):
            n = _evaluar_entero(u[3:].strip("() "))
            return f"BIN: {bin(n)}", f"(={n})", ""
        if u.startswith("OCT"):
            n = _evaluar_entero(u[3:].strip("() "))
            return f"OCT: {oct(n)}", f"(={n})", ""
        if u.startswith("HEX"):
            n = _evaluar_entero(u[3:].strip("() "))
            return f"HEX: {hex(n).upper()}", f"(={n})", ""
        if u.startswith("AND"):
            p = u[3:].strip("() ").split(",")
            a, b = _evaluar_entero(p[0]), _evaluar_entero(p[1])
            return f"{a} AND {b}", f"= {a & b}", f"HEX: {hex(a & b).upper()}"
        if u.startswith("OR"):
            p = u[2:].strip("() ").split(",")
            a, b = _evaluar_entero(p[0]), _evaluar_entero(p[1])
            return f"{a} OR {b}", f"= {a | b}", f"HEX: {hex(a | b).upper()}"
        if u.startswith("XOR"):
            p = u[3:].strip("() ").split(",")
            a, b = _evaluar_entero(p[0]), _evaluar_entero(p[1])
            return f"{a} XOR {b}", f"= {a ^ b}", f"HEX: {hex(a ^ b).upper()}"
        if u.startswith("NOT"):
            n = _evaluar_entero(u[3:].strip("() "))
            r = (~n) & 0xFFFFFFFF  # NOT de 32 bits sin signo
            return f"NOT {n}", f"= {r}", f"HEX: {hex(r).upper()}"
        return "Cmd BASE-N:", "BIN OCT HEX", "AND OR XOR NOT"
    except Exception as ex:
        return f"Error BASE-N: {ex}", "", ""


# ── 11v5.3-A. ECUACIONES SIMULTANEAS (NUEVO 1 - v5.3) ─

def _gauss(A, b):
    """Eliminacion gaussiana con pivoteo parcial.
    A: lista de listas n×n (se modifica in-place).
    b: lista de n independientes (se modifica in-place).
    Retorna lista de n soluciones, o lanza ValueError si singular."""
    n = len(b)
    # Construir matriz aumentada
    M = [A[i][:] + [b[i]] for i in range(n)]

    for col in range(n):
        # Pivoteo parcial: busca la fila con mayor valor absoluto en esta col
        pivot_fila = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[pivot_fila] = M[pivot_fila], M[col]

        if abs(M[col][col]) < 1e-12:
            raise ValueError("Sistema sin solucion unica")

        for fila in range(col + 1, n):
            factor = M[fila][col] / M[col][col]
            for j in range(col, n + 1):
                M[fila][j] -= factor * M[col][j]

    # Sustitucion hacia atras
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = M[i][n]
        for j in range(i + 1, n):
            x[i] -= M[i][j] * x[j]
        x[i] /= M[i][i]
    return x

def _regresion_lineal(xs, ys):
    """Minimos cuadrados y = a + bx.
    Devuelve (a, b, r) donde r es el coef. de correlacion de Pearson."""
    n = len(xs)
    if n < 2:
        raise ValueError("Se necesitan >= 2 puntos")
    sx  = sum(xs);  sy  = sum(ys)
    sxx = sum(x*x for x in xs)
    sxy = sum(x*y for x, y in zip(xs, ys))
    syy = sum(y*y for y in ys)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        raise ValueError("Datos degenerados (x constante)")
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    # Coeficiente de correlacion r
    num_r = n * sxy - sx * sy
    den_r = math.sqrt(max(0.0, (n * sxx - sx**2) * (n * syy - sy**2)))
    r = num_r / den_r if den_r > 1e-12 else 0.0
    return a, b, r

def _regresion_cuadratica(xs, ys):
    """Regresion cuadratica y = a + bx + cx² por sistema 3x3 normal."""
    n = len(xs)
    if n < 3:
        raise ValueError("Se necesitan >= 3 puntos para cuadratica")
    sx  = sum(xs);    sx2 = sum(x**2 for x in xs)
    sx3 = sum(x**3 for x in xs); sx4 = sum(x**4 for x in xs)
    sy  = sum(ys)
    sxy = sum(x*y for x, y in zip(xs, ys))
    sx2y = sum(x**2*y for x, y in zip(xs, ys))
    # Sistema 3x3: [n sx sx2; sx sx2 sx3; sx2 sx3 sx4] * [a;b;c] = [sy;sxy;sx2y]
    A = [[n,   sx,  sx2],
         [sx,  sx2, sx3],
         [sx2, sx3, sx4]]
    b_vec = [sy, sxy, sx2y]
    a, b, c = _gauss(A, b_vec)
    # r² como fraccion de varianza explicada
    y_mean = sy / n
    ss_tot = sum((y - y_mean)**2 for y in ys)
    ss_res = sum((y - (a + b*x + c*x**2))**2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 1e-12 else 1.0
    return a, b, c, math.sqrt(max(0.0, r2))

def _fmt_regresion(modelo, a, b, r, c=None):
    """Formatea el resultado de una regresion en 3 lineas de pantalla."""
    fa = decimal_a_fraccion(round(a, 5))
    fb = decimal_a_fraccion(round(b, 5))
    fr = f"{r:.4f}"
    linea1 = f"{modelo}: a={fa}"
    linea2 = f"b={fb}"
    if c is not None:
        linea2 += f" c={decimal_a_fraccion(round(c, 5))}"
    return linea1, linea2, f"r={fr}"

def matedit_iniciar(nombre, filas, cols):
    """Inicia el editor de matrices: reserva estado y muestra la primera celda.
    Se llama al seleccionar el modo 6 (MATRIX) y elegir dimension,
    o desde el token MATEDIT<A>,<filas>,<cols> en consola."""
    global _MATEDIT_ESTADO
    nombre = nombre.upper()
    if nombre not in MATRICES:
        return "Nombre: A B C", "", ""
    if filas < 1 or filas > 4 or cols < 1 or cols > 4:
        return "Max 4x4", f"Got {filas}x{cols}", ""
    _MATEDIT_ESTADO = {
        "activo": True,
        "nombre": nombre,
        "filas": int(filas),
        "cols": int(cols),
        "datos": [],
        "celda": 0,
    }
    return _matedit_prompt()

def _matedit_prompt():
    """Devuelve el mensaje de pantalla para la celda actual del editor."""
    e = _MATEDIT_ESTADO
    if not e["activo"]:
        return "Editor inactivo", "", ""
    celda = e["celda"]
    total = e["filas"] * e["cols"]
    fila  = celda // e["cols"] + 1
    col   = celda %  e["cols"] + 1
    return (f"Mat{e['nombre']} {e['filas']}x{e['cols']}",
            f"Ingresa [{fila},{col}]",
            f"({celda+1}/{total}) IGUAL=ok")

def matedit_ingresar(valor_str):
    """Recibe el valor de la celda actual (como string evaluable),
    lo agrega al buffer y avanza. Si es la ultima celda, guarda la
    matriz en MATRICES y cierra el editor.
    Devuelve tupla de 3 strings para la pantalla."""
    global _MATEDIT_ESTADO
    e = _MATEDIT_ESTADO
    if not e["activo"]:
        return "Editor no abierto", "", ""
    try:
        val = evaluar_expresion(valor_str.strip(), variables_actuales())
    except Exception as ex:
        return f"Error: {ex}"[:16], "Reintenta el valor", _matedit_prompt()[1]

    e["datos"].append(val)
    e["celda"] += 1
    total = e["filas"] * e["cols"]

    if e["celda"] >= total:
        # Ultimo elemento: guardar y cerrar
        MATRICES[e["nombre"]] = {
            "data": e["datos"][:],
            "filas": e["filas"],
            "cols": e["cols"],
        }
        nombre = e["nombre"]
        f, c = e["filas"], e["cols"]
        e["activo"] = False
        return (f"Mat{nombre} {f}x{c} guardada",
                f"{total} elementos OK",
                "AC para salir")

    return _matedit_prompt()

def _angulo_a_rad(theta):
    """Convierte theta desde la unidad activa (DEG/RAD) a radianes."""
    return theta if MODO_ANGULOS == "RAD" else math.radians(theta)

def _rad_a_angulo(rad):
    """Convierte radianes a la unidad activa (DEG/RAD)."""
    return rad if MODO_ANGULOS == "RAD" else math.degrees(rad)

def cmd_pol(cmd):
    """POL(r, theta): convierte coordenadas polares a rectangulares.
    theta se interpreta en la unidad activa (DEG o RAD segun SETUP).
    Devuelve X, Y."""
    try:
        nums = extraer_numeros(cmd, "POL")
        r, theta = nums[0], nums[1]
        rad = _angulo_a_rad(theta)
        x = r * math.cos(rad)
        y = r * math.sin(rad)
        return (f"X = {decimal_a_fraccion(round(x, 6))}",
                f"Y = {decimal_a_fraccion(round(y, 6))}", "")
    except Exception as ex:
        return f"Error POL: {ex}"[:16], "", ""

def cmd_rec(cmd):
    """REC(x, y): convierte coordenadas rectangulares a polares.
    El angulo devuelto esta en la unidad activa (DEG o RAD segun SETUP)."""
    try:
        nums = extraer_numeros(cmd, "REC")
        x, y = nums[0], nums[1]
        r   = math.hypot(x, y)
        ang = _rad_a_angulo(math.atan2(y, x))
        return (f"R = {decimal_a_fraccion(round(r, 6))}",
                f"ANG = {decimal_a_fraccion(round(ang, 4))}", "")
    except Exception as ex:
        return f"Error REC: {ex}"[:16], "", ""


# ── 11v5.5-A. CONVERSION SEXAGESIMAL DMS <-> DECIMAL (NUEVO 4 - v5.5) ─
# La fx-991 tiene una tecla dedicada "°' "" para trabajar con grados,
# minutos y segundos. Aqui se ofrecen dos comandos equivalentes:
#   DMS(g,m,s)   -> grados decimales (g + m/60 + s/3600), con el signo
#                   de 'g' aplicado al resultado completo.
#   TODMS(valor) -> descompone un grado decimal en (g, m, s) y devuelve
#                   el string formateado "g°m'.s\"" igual que la Casio.
def cmd_dms(cmd):
    """DMS(g,m,s) -> grados decimales. Acepta m y s negativos o positivos;
    el signo final lo determina 'g' (igual que la convención DMS estándar:
    -10°30' = -(10 + 30/60), nunca -10 + 30/60)."""
    try:
        nums = extraer_numeros(cmd, "DMS")
        if len(nums) != 3:
            return "Use DMS(", "g,m,s)", ""
        g, m, s = nums
        signo = -1 if g < 0 else 1
        valor = signo * (abs(g) + abs(m) / 60 + abs(s) / 3600)
        return (f"DMS = {decimal_a_fraccion(round(valor, 8))}",
                f"({g}\u00b0{m}'{s}\")", "")
    except Exception as ex:
        return f"Error DMS: {ex}"[:16], "", ""


def cmd_todms(cmd):
    """TODMS(valor) -> descompone un grado decimal en grados, minutos
    y segundos, formato Casio: 10.5125 -> 10°30'45.0\"."""
    try:
        nums = extraer_numeros(cmd, "TODMS")
        if len(nums) != 1:
            return "Use TODMS(", "valor)", ""
        valor = nums[0]
        signo = "-" if valor < 0 else ""
        x = abs(valor)
        g = int(x)
        resto_min = (x - g) * 60
        m = int(resto_min)
        s = round((resto_min - m) * 60, 2)
        # Acarreo: si el redondeo de segundos llega a 60, ajustar minutos/grados
        if s >= 60:
            s -= 60
            m += 1
        if m >= 60:
            m -= 60
            g += 1
        return (f"{signo}{g}\u00b0{m}'{s}\"",
                f"(= {decimal_a_fraccion(round(valor, 6))}\u00b0)", "")
    except Exception as ex:
        return f"Error TODMS: {ex}"[:16], "", ""


# ── 11v5.3-E. MATEDIT EN EL BUCLE (estado de ingreso celda a celda) ─
# El bucle iniciar() consulta _MATEDIT_ESTADO["activo"] para saber
# si debe redirigir el token IGUAL a matedit_ingresar() en vez del
# calculo normal. El buffer ENTRADA_TOKENS sigue funcionando igual:
# el usuario escribe el valor de la celda y presiona IGUAL para confirmarlo.

# NUEVO 2 (v5.2): el modo 8 (VECTOR) del menu MODE ya tenia DOT/CROSS
# (producto escalar/vectorial entre DOS vectores), pero no tenia ninguna
# operacion sobre UN solo vector (modulo, direccion), que es lo que la
# Casio fx-991 ofrece como entrada principal del modo VECTOR.
def cmd_vector(cmd):
    """VEC2(x,y)  -> modulo |v| y angulo respecto al eje X.
    VEC3(x,y,z) -> modulo |v| y los 3 angulos directores (con los ejes
                   X, Y, Z), via acos(componente/modulo).
    Los angulos se muestran en DEG o RAD segun MODO_ANGULOS (SETUP)."""
    if MODO_EXAMEN:
        return _E_NODISP, "", ""
    try:
        if "VEC2" in cmd:
            nums = extraer_numeros(cmd, "VEC2")
            if len(nums) != 2:
                return "Use VEC2(", "x,y)", ""
            x, y = nums
            mag = math.hypot(x, y)
            ang = _rad_a_modo_angular(math.atan2(y, x))
            return (f"|v| = {decimal_a_fraccion(mag)}",
                    f"ang = {decimal_a_fraccion(ang)}", "")

        if "VEC3" in cmd:
            nums = extraer_numeros(cmd, "VEC3")
            if len(nums) != 3:
                return "Use VEC3(", "x,y,z)", ""
            x, y, z = nums
            mag = math.sqrt(x * x + y * y + z * z)
            if mag == 0:
                return "|v| = 0", "Vector nulo", ""
            ax = _rad_a_modo_angular(math.acos(max(-1.0, min(1.0, x / mag))))
            ay = _rad_a_modo_angular(math.acos(max(-1.0, min(1.0, y / mag))))
            az = _rad_a_modo_angular(math.acos(max(-1.0, min(1.0, z / mag))))
            return (f"|v| = {decimal_a_fraccion(mag)}",
                    f"aX={decimal_a_fraccion(ax)} aY={decimal_a_fraccion(ay)}",
                    f"aZ = {decimal_a_fraccion(az)}")
    except Exception as ex:
        return f"Error Vec: {ex}", "", ""
    return "Error Vec", "", ""


# ── 11v5.5-C. MODO SHEET: HOJA DE CALCULO SIMPLIFICADA (NUEVO 5 - v5.5) ─
# Replica simplificada del modo Spreadsheet de la fx-991EX: grilla de
# celdas A1:F10 donde cada celda guarda un numero o una formula que
# empieza con "=" y puede referenciar otras celdas (=A1+B2*2). No hay
# recalculo automatico encadenado con deteccion de ciclos complejos;
# en su lugar, cada formula se evalua "on demand" siguiendo referencias
# de forma recursiva, con un limite de profundidad para detectar
# referencias circulares (A1=B1, B1=A1) sin colgar la Pico.

def _celda_valida(col, fila):
    return col in "ABCDEF" and 1 <= fila <= SHEET_FILAS


def _celda_id(col, fila):
    return f"{col}{fila}"


def _evaluar_celda(celda_id, _pila_visitada=None):
    """Evalua el contenido de una celda, siguiendo formulas de forma
    recursiva. Lanza ValueError si detecta referencia circular o si
    la celda esta vacia (se trata como 0.0 para no romper formulas
    que suman rangos con celdas no llenadas, igual que una hoja real)."""
    if _pila_visitada is None:
        _pila_visitada = set()
    if celda_id in _pila_visitada:
        raise ValueError(f"Ref circular en {celda_id}")
    crudo = SHEET_DATOS.get(celda_id)
    if crudo is None or crudo == "":
        return 0.0
    if not crudo.startswith("="):
        # Valor literal (numero)
        return float(crudo)

    _pila_visitada.add(celda_id)
    formula = crudo[1:].upper()
    # Construir el set de variables disponibles: las 60 celdas (A1..F10)
    # se exponen como variables de un solo "token" reusando el mismo
    # tokenizador alfabetico, por lo que aqui resolvemos manualmente
    # cada referencia ColFila dentro de la formula antes de evaluar.
    import re
    def _reemplazar(match):
        ref = match.group(0)
        col_ref, fila_ref = ref[0], int(ref[1:])
        if not _celda_valida(col_ref, fila_ref):
            raise ValueError(f"Celda invalida: {ref}")
        valor = _evaluar_celda(_celda_id(col_ref, fila_ref), _pila_visitada)
        return f"({valor})"

    formula_resuelta = re.sub(r"[A-F](?:[1-9]|10)\b", _reemplazar, formula)
    resultado = evaluar_expresion(formula_resuelta, variables_actuales())
    _pila_visitada.discard(celda_id)
    return resultado


def renderizar_sheet():
    """Muestra la celda actual (SHEET_CURSOR), su contenido crudo y su
    valor evaluado. Navegacion con IZQ/DER (columna) y flechas dedicadas
    si el hardware las tiene; en consola PC se usa SHEETUP/SHEETDOWN
    ademas de IZQ/DER para moverse en ambas direcciones."""
    col, fila = SHEET_CURSOR
    celda_id = _celda_id(col, fila)
    crudo = SHEET_DATOS.get(celda_id, "")
    try:
        valor = _evaluar_celda(celda_id)
        valor_txt = decimal_a_fraccion(round(valor, 6)) if isinstance(valor, (int, float)) else str(valor)
    except Exception as ex:
        valor_txt = f"Err: {ex}"[:16]
    crudo_txt = crudo if crudo else "(vacia)"
    renderizar_pantalla(f"SHEET {celda_id}", f"= {crudo_txt}"[:16],
                         f"val: {valor_txt}", "IZQ/DER/SHEETUP/DOWN")


def cmd_sheet(cmd=""):
    """Entrada al modo SHEET. 'SHEET' solo (sin argumentos) abre el
    modo y posiciona el cursor en A1. Dentro del modo, el bucle
    principal redirige el texto ingresado (numero o '=formula') a
    sheet_ingresar_celda() cuando se presiona IGUAL."""
    global EN_MODO_SHEET, SHEET_CURSOR
    if MODO_EXAMEN:
        return _E_NODISP, "", ""
    EN_MODO_SHEET = True
    SHEET_CURSOR = ["A", 1]
    return "Modo SHEET", "A1:F10 disponibles", "Escribe y IGUAL"


def sheet_ingresar_celda(texto):
    """Guarda 'texto' (numero o formula '=...') en la celda actual y
    devuelve las 3 lineas de pantalla con el resultado evaluado."""
    col, fila = SHEET_CURSOR
    celda_id = _celda_id(col, fila)
    texto = texto.strip()
    if texto == "":
        SHEET_DATOS.pop(celda_id, None)
    elif texto.startswith("="):
        SHEET_DATOS[celda_id] = texto
    else:
        try:
            # Permite expresiones simples sin "=" como atajo (ej: "2+3")
            valor = evaluar_expresion(texto.upper(), variables_actuales())
            SHEET_DATOS[celda_id] = str(valor)
        except Exception:
            return f"Error en {celda_id}", "Valor invalido", ""
    renderizar_sheet()
    return "", "", ""  # renderizar_sheet ya pinto la pantalla


def sheet_mover(direccion):
    """Mueve SHEET_CURSOR. direccion: 'IZQ','DER','ARRIBA','ABAJO'."""
    global SHEET_CURSOR
    col, fila = SHEET_CURSOR
    cols = "ABCDEF"
    idx = cols.index(col)
    if direccion == "IZQ":
        idx = max(0, idx - 1)
    elif direccion == "DER":
        idx = min(len(cols) - 1, idx + 1)
    elif direccion == "ARRIBA":
        fila = max(1, fila - 1)
    elif direccion == "ABAJO":
        fila = min(SHEET_FILAS, fila + 1)
    SHEET_CURSOR = [cols[idx], fila]
    renderizar_sheet()


# ── 11. CAPA DE ENTRADA: TOKENS Y MULTIPLICACION IMPLICITA ─
ALIAS_TOKENS = {nombre: nombre + "(" for nombre in FUNC_MAP}
# Comandos especiales de teclado fisico / 2ND que no estan en FUNC_MAP:
ALIAS_TOKENS.update({
    "MAT2": "MAT2(", "MAT3": "MAT3(", "DOT": "DOT(", "CROSS": "CROSS(",
    "POL": "POL(", "REC": "REC(",
    "CUAD": "CUAD(", "CUB": "CUB(",
    "BIN": "BIN(", "OCT": "OCT(", "HEX": "HEX(",
    "NPR": "NPR(", "NCR": "NCR(",  # NUEVO 1 (v5.0): permutaciones/combinaciones
    "VEC2": "VEC2(", "VEC3": "VEC3(",  # NUEVO 2 (v5.2): modo VECTOR real
    # v5.5: DMS/TODMS, CUART (polinomio grado 4), RAIZN (raiz k-esima exacta)
    "DMS": "DMS(", "TODMS": "TODMS(", "CUART": "CUART(", "RAIZN": "RAIZN(",
})

def es_numero_str(s):
    return s != "" and all(ch in "0123456789." for ch in s)

VALORES_CIERRE = (")", "PI", "E")

def necesita_mult_implicita(anterior, nuevo):
    """True si hay que insertar un '*' entre dos tokens consecutivos
    para soportar patrones humanos: 2(3+4), 3PI, (2+3)(4+5), X(2), 5SIN(...), etc."""
    cierra_valor = (anterior in VALORES_CIERRE or anterior in MEMORIA
                    or anterior == "ANS" or es_numero_str(anterior))
    abre_valor = (
        nuevo == "("
        or nuevo in CONSTANTES
        or nuevo in MEMORIA
        or nuevo == "ANS"
        or es_numero_str(nuevo)
        or nuevo.endswith("(")  # funciones: SIN(, SQRT(, MAT2(, etc.
    )
    if not (cierra_valor and abre_valor):
        return False
    if es_numero_str(anterior) and es_numero_str(nuevo):
        return False  # no separar digitos del mismo numero (2,3 -> "23")
    return True

def construir_expresion(tokens):
    """Une la lista de TOKENS insertando '*' donde haga falta
    (multiplicacion implicita). El resultado es lo que se le pasa
    al motor de evaluacion / parser de comandos."""
    partes = []
    anterior = None
    for tok in tokens:
        if anterior is not None and necesita_mult_implicita(anterior, tok):
            partes.append("*")
        partes.append(tok)
        anterior = tok
    return "".join(partes)


# ── 11b. MENU MODE (v4.3) - Identico al de la Casio fx-991 CW ─
# Opciones del menu: 8 modos en 2 filas de 4, igual que ClassWiz.
# Fila 1: 1:COMP   2:CMPLX  3:STAT   4:BASE-N
# Fila 2: 5:EQN    6:MATRIX 7:TABLE  8:VECTOR

_OPCIONES_MODE = [
    (1, "COMP"),
    (2, "CMPLX"),
    (3, "STAT"),
    (4, "BASE-N"),
    (5, "EQN"),
    (6, "MATRIX"),
    (7, "TABLE"),
    (8, "VECTOR"),
]

def renderizar_menu_mode(seleccion=None):
    """Muestra el menu MODE en pantalla al estilo Casio fx-991.
    seleccion: numero del modo resaltado (1-8), o None para resaltar
    el modo activo actual (MODO_CALC).
    En OLED: 4 lineas = encabezado + fila1 + fila2 + indicador.
    En consola PC: caja con los 8 modos y el modo activo marcado."""
    sel = seleccion if seleccion is not None else MODO_CALC

    # Construir las dos filas con marcador ">" en el seleccionado
    def _celda(num, nombre):
        marca = ">" if num == sel else " "
        return f"{marca}{num}:{nombre:<7}"

    fila1 = "".join(_celda(n, nm) for n, nm in _OPCIONES_MODE[:4])
    fila2 = "".join(_celda(n, nm) for n, nm in _OPCIONES_MODE[4:])

    if ENTORNO_PICO and display:
        ANCHO = 16
        display.fill(0)
        display.text("===  MODE  ===", 0, 2, 1)
        # En OLED 128px (16 chars) mostramos 2 opciones por fila
        fila1_oled = f"{_celda(1,'COMP')[:8]}{_celda(2,'CMPLX')[:8]}"
        fila2_oled = f"{_celda(3,'STAT')[:8]}{_celda(4,'BASN')[:8]}"
        fila3_oled = f"{_celda(5,'EQN')[:8]}{_celda(6,'MATRX')[:8]}"
        fila4_oled = f"{_celda(7,'TABLE')[:8]}{_celda(8,'VECT')[:8]}"
        display.text(fila1_oled[:ANCHO], 0, 14, 1)
        display.text(fila2_oled[:ANCHO], 0, 26, 1)
        display.text(fila3_oled[:ANCHO], 0, 38, 1)
        display.text(fila4_oled[:ANCHO], 0, 50, 1)
        display.show()
    else:
        activo = MODO_CALC_NOMBRES.get(MODO_CALC, "?")
        print("\n" + "=" * 36)
        print("|        [MENU MODE]               |")
        print("-" * 36)
        for num, nombre in _OPCIONES_MODE:
            marca = ">>" if num == sel else "  "
            activo_txt = " <- ACTIVO" if num == MODO_CALC else ""
            print(f"| {marca} {num}:{nombre:<8}{activo_txt:<14}|")
        print("-" * 36)
        print("|  Digita numero (1-8) o AC=salir  |")
        print("=" * 36)

def aplicar_modo(num):
    """Aplica el modo seleccionado del menu MODE y devuelve mensaje
    de confirmacion al estilo Casio (ej: 'COMP Mode').

    NUEVO 3 (v5.2): si num==5 (EQN), en vez de confirmar directamente
    se abre el submenu EN_MENU_EQN (2x2/3x3/Cuadratica/Cubica), igual
    que la fx-991 real pide el tipo de ecuacion al entrar a EQN."""
    global MODO_CALC, MODO_COMPLEJO, EN_MENU_MODE, EN_MENU_EQN
    if num not in MODO_CALC_NOMBRES:
        return "Opcion invalida"
    MODO_CALC = num
    nombre = MODO_CALC_NOMBRES[num]
    # Efectos secundarios segun el modo (igual que la fx-991)
    if num == 2:
        MODO_COMPLEJO = True
    else:
        # Modos 1,3-8 desactivan CMPLX salvo que el usuario lo reactiva
        if num == 1:
            MODO_COMPLEJO = False
    EN_MENU_MODE = False
    if num == 5:
        EN_MENU_EQN = True
    return f"{nombre} Mode"


# ── 11b-2. SUBMENU EQN (v5.2) - tipo de ecuacion ───
_OPCIONES_EQN = [
    (1, "Sist. 2x2", "MAT2("),
    (2, "Sist. 3x3", "MAT3("),
    (3, "Cuadratica", "CUAD("),
    (4, "Cubica", "CUB("),
]

def renderizar_menu_eqn():
    """Muestra el submenu EQN: tipo de ecuacion a resolver.
    Elegir una opcion precarga su token en ENTRADA_TOKENS, listo
    para que el usuario complete los argumentos (coeficientes)."""
    if ENTORNO_PICO and display:
        display.fill(0)
        display.text("=== EQN ===", 0, 2, 1)
        display.text("1:Sist 2x2", 0, 16, 1)
        display.text("2:Sist 3x3", 0, 28, 1)
        display.text("3:Cuad 4:Cubica", 0, 40, 1)
        display.text("AC=salir", 0, 52, 1)
        display.show()
    else:
        print("\n" + "=" * 36)
        print("|        [MENU EQN]                |")
        print("-" * 36)
        for num, nombre, _tok in _OPCIONES_EQN:
            print(f"|  {num}: {nombre:<28}|")
        print("-" * 36)
        print("|  Digita numero (1-4) o AC=salir   |")
        print("=" * 36)

def aplicar_eqn(num):
    """Precarga ENTRADA_TOKENS con el token de la ecuacion elegida
    (MAT2(, MAT3(, CUAD(, CUB() y posiciona el cursor al final, listo
    para que el usuario escriba los coeficientes. Devuelve True si
    'num' fue una opcion valida (1-4), False en caso contrario."""
    global ENTRADA_TOKENS, CURSOR_POS, EN_MENU_EQN
    opciones = {n: tok for n, _nm, tok in _OPCIONES_EQN}
    if num not in opciones:
        return False
    ENTRADA_TOKENS = [opciones[num]]
    CURSOR_POS = len(ENTRADA_TOKENS)
    EN_MENU_EQN = False
    return True

# NUEVO 4 (v5.2): recordatorio rapido de comandos al confirmar un modo
# desde el menu MODE (tercera linea de pantalla).
SUGERENCIAS_MODO = {
    1: "Calculo normal",
    2: "I=imag CONJ() ARG()",
    3: "ADD:v STATX x,y CALC DIST",
    4: "BIN OCT HEX AND OR",
    5: "",  # EQN abre su propio submenu
    6: "MATDEF MATMUL MATDET",
    7: "TABLE f,ini,fin,paso TABLE2",
    8: "VEC2() VEC3() DOT() CROSS()",
}


# ── 12. PROCESADOR DE COMANDOS GENERAL ─────────────

# ══════════════════════════════════════════════════════════════════════
# MÓDULOS NUEVOS v5.6
# ══════════════════════════════════════════════════════════════════════

# ── NUEVO 1: HISTORIAL ────────────────────────────────────────────────
def _hist_guardar(expr, resultado):
    """Agrega entrada al historial (FIFO, maximo HIST_MAX)."""
    global HISTORIAL
    if HISTORIAL and HISTORIAL[-1]["expr"] == expr:
        return
    HISTORIAL.append({"expr": expr, "res": resultado})
    if len(HISTORIAL) > HIST_MAX:
        HISTORIAL.pop(0)

def renderizar_hist_entrada(idx):
    n = len(HISTORIAL)
    if n == 0:
        renderizar_pantalla("Historial vacio", "AC=salir")
        return
    i = idx % n
    e = HISTORIAL[-(i + 1)]   # mas reciente primero
    renderizar_pantalla(
        f"[{i+1}/{n}] {e['expr'][-14:]}",
        f"= {e['res'][:28]}",
        "IGUAL=recargar",
        "IZQ/DER  AC=salir",
    )


# ── NUEVO 2: RANINT#(a,b) ─────────────────────────────────────────────
# RAN# ya existia como "RAND" (time.time() % 1). Se agrega RANINT.
def cmd_ranint(cmd):
    nums = extraer_numeros(cmd, "RANINT")
    if len(nums) < 2:
        return "Use RANINT(a,b)", "", ""
    a, b = int(round(nums[0])), int(round(nums[1]))
    if a > b:
        a, b = b, a
    import time as _t
    # Generador LCG simple, compatible con MicroPython (sin random).
    seed = int(_t.time() * 1000) & 0xFFFFFFFF
    val  = ((seed * 1664525 + 1013904223) & 0xFFFFFFFF)
    result = a + (val % (b - a + 1))
    return f"RanInt({a},{b})", f"= {result}", ""


# ── NUEVO 3: MOD(a,b) ─────────────────────────────────────────────────
def cmd_mod(cmd):
    """MOD(a,b): resto de la division a % b.
    Los argumentos pueden ser expresiones completas (ej: MOD(A^2,7))."""
    try:
        resto = cmd.split("MOD", 1)[-1].strip().strip("()")
        # Dividir por la ULTIMA coma de nivel 0 para soportar expresiones con comas
        nivel, split_idx = 0, -1
        for i, ch in enumerate(resto):
            if ch == "(": nivel += 1
            elif ch == ")": nivel -= 1
            elif ch == "," and nivel == 0: split_idx = i
        if split_idx < 0:
            return "Use MOD(a,b)", "", ""
        expr_a = resto[:split_idx].strip()
        expr_b = resto[split_idx+1:].strip()
        va = evaluar_expresion(expr_a.upper(), variables_actuales())
        vb = evaluar_expresion(expr_b.upper(), variables_actuales())
        if vb == 0:
            return "Division por cero", "", ""
        result = va % vb
        return f"MOD({va},{vb})", f"= {decimal_a_fraccion(result)}", ""
    except Exception as ex:
        return f"Error MOD: {ex}"[:16], "", ""


# ── NUEVO 4: ENG (notacion de ingenieria) ─────────────────────────────
FORMATO_ENG = False   # activado por SETUPENG

def _fmt_eng(val):
    """Formato de ingenieria: exponente multiplo de 3 (kilo/mega/mili…)."""
    if val == 0:
        return "0"
    neg = val < 0
    v = abs(val)
    exp3 = int(math.floor(math.log10(v) / 3)) * 3
    mantisa = v / (10 ** exp3)
    s = f"{mantisa:.{FORMATO_DECIMALES}f}E{exp3:+d}"
    return ("-" + s) if neg else s


# ── NUEVO 5: AFRAC(x) — S<->D automatico ─────────────────────────────
def cmd_afrac(cmd):
    """Intenta representar x como fraccion exacta o raiz simple.
    Replica el boton S<->D de la fx-991."""
    nums = extraer_numeros(cmd, "AFRAC")
    if not nums:
        return "Use AFRAC(x)", "", ""
    val = nums[0]
    # 1) ¿Es entero?
    r = round(val, 10)
    if r == int(r):
        return f"AFRAC({val})", f"= {int(r)}", "(entero)"
    # 2) ¿Es fraccion exacta (denominador <= 1000)?
    for den in range(2, 1001):
        num = round(val * den)
        if abs(num / den - val) < 1e-9:
            from math import gcd as _gcd
            g = _gcd(abs(int(num)), den)
            return f"AFRAC({val})", f"= {int(num)//g}/{den//g}", "(fraccion)"
    # 3) ¿Es raiz de entero pequeño?
    for k in (2, 3, 4, 5, 6):
        potencia = round(val ** k)
        if potencia > 0 and abs(potencia ** (1/k) - val) < 1e-7:
            return f"AFRAC({val})", f"= {potencia}^(1/{k})", "(radical)"
    return f"AFRAC({val})", f"= {val:.8f}", "(sin forma exacta)"


# ── NUEVO 6: SUM(expr,var,ini,fin) ───────────────────────────────────
def cmd_sum(cmd):
    if MODO_EXAMEN:
        return _E_NODISP, "", ""
    try:
        resto = cmd.split("SUM", 1)[-1].strip().strip("()")
        partes = [p.strip() for p in resto.split(",")]
        if len(partes) < 4:
            return "Use SUM(expr,var,", "ini,fin)", ""
        expr, var = partes[0].upper(), partes[1].upper().strip()
        ini  = int(round(evaluar_expresion(partes[2], variables_actuales())))
        fin  = int(round(evaluar_expresion(partes[3], variables_actuales())))
        if abs(fin - ini) > 9999:
            return "Error: rango >9999", "", ""
        total = 0.0
        paso  = 1 if fin >= ini else -1
        for i in range(ini, fin + paso, paso):
            total += evaluar_expresion(expr, variables_actuales({var: float(i)}))
        return f"SUM {var}={ini}..{fin}", f"= {decimal_a_fraccion(total)}", ""
    except Exception as ex:
        return f"Error SUM: {ex}"[:16], "", ""


# ── NUEVO 7: PROD(expr,var,ini,fin) ──────────────────────────────────
def cmd_prod(cmd):
    if MODO_EXAMEN:
        return _E_NODISP, "", ""
    try:
        resto = cmd.split("PROD", 1)[-1].strip().strip("()")
        partes = [p.strip() for p in resto.split(",")]
        if len(partes) < 4:
            return "Use PROD(expr,var,", "ini,fin)", ""
        expr, var = partes[0].upper(), partes[1].upper().strip()
        ini  = int(round(evaluar_expresion(partes[2], variables_actuales())))
        fin  = int(round(evaluar_expresion(partes[3], variables_actuales())))
        if abs(fin - ini) > 999:
            return "Error: rango >999", "", ""
        total = 1.0
        paso  = 1 if fin >= ini else -1
        for i in range(ini, fin + paso, paso):
            total *= evaluar_expresion(expr, variables_actuales({var: float(i)}))
        return f"PROD {var}={ini}..{fin}", f"= {decimal_a_fraccion(total)}", ""
    except Exception as ex:
        return f"Error PROD: {ex}"[:16], "", ""


# ── NUEVO 8: Distribucion hipergeometrica ─────────────────────────────
def _hg_pmf(k, N, K, n):
    """P(X=k) para X ~ HiperGeom(N, K, n).
    k=exitos en muestra, N=poblacion, K=exitos en poblacion, n=muestra."""
    from math import comb
    k, N, K, n = int(k), int(N), int(K), int(n)
    if k < max(0, n+K-N) or k > min(n, K):
        return 0.0
    return comb(K, k) * comb(N-K, n-k) / comb(N, n)

def _hg_cdf(k_max, N, K, n):
    return sum(_hg_pmf(k, N, K, n) for k in range(k_max + 1))


# ── NUEVO 9: Distribucion t-Student (CDF por Gauss-Legendre 16 pts) ──
_GL_X = [
    -0.9894009350, -0.9445750231, -0.8656312024, -0.7554044084,
    -0.6178762444, -0.4580167777, -0.2816035508, -0.0950125098,
     0.0950125098,  0.2816035508,  0.4580167777,  0.6178762444,
     0.7554044084,  0.8656312024,  0.9445750231,  0.9894009350,
]
_GL_W = [
    0.0271524594, 0.0622535239, 0.0951585117, 0.1246289713,
    0.1495959889, 0.1691565194, 0.1826034150, 0.1894506105,
    0.1894506105, 0.1826034150, 0.1691565194, 0.1495959889,
    0.1246289713, 0.0951585117, 0.0622535239, 0.0271524594,
]

def _pdf_t(t, nu):
    c = math.lgamma((nu+1)/2) - math.lgamma(nu/2) - 0.5*math.log(nu*math.pi)
    return math.exp(c) * (1 + t*t/nu) ** (-(nu+1)/2)

def _cdf_t(x, nu):
    """CDF t-Student: P(T <= x) para nu grados de libertad."""
    if math.isinf(x):
        return 1.0 if x > 0 else 0.0
    a, b = -10.0, min(x, 10.0)
    mid, half = (a+b)/2, (b-a)/2
    cdf = sum(w * _pdf_t(mid + half*xi, nu) for xi, w in zip(_GL_X, _GL_W)) * half
    if x > 10.0:
        cdf += 1.0 - _cdf_t(10.0, nu)
    return max(0.0, min(1.0, cdf))

def _inv_t(p, nu, tol=1e-9):
    """Inversa t-Student por biseccion."""
    if p <= 0: return float('-inf')
    if p >= 1: return float('inf')
    lo, hi = -30.0, 30.0
    for _ in range(80):
        mid = (lo + hi) / 2
        (_cdf_t(mid, nu) < p and (lambda: None)()) or None
        if _cdf_t(mid, nu) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


# ── NUEVO 10: Distribucion Chi-cuadrado ───────────────────────────────
def _gamma_inc_lower(a, x, terms=200):
    """Funcion gamma incompleta inferior regularizada P(a,x).
    Usa la serie de Taylor para x < a+1, y la fraccion continua (Lentz)
    para x >= a+1, igual que las implementaciones numericas de referencia.
    Resultado siempre en [0, 1]."""
    if x <= 0:
        return 0.0
    if x < a + 1:
        # Serie de Taylor: convergencia garantizada para x < a+1
        total, term = 1.0, 1.0
        for n in range(1, terms):
            term *= x / (a + n)
            total += term
            if abs(term) < 1e-14 * total:
                break
        val = math.exp(-x + a * math.log(x) - math.lgamma(a + 1)) * total
    else:
        # Fraccion continua de Legendre (algoritmo de Lentz modificado)
        # Q(a,x) = 1 - P(a,x)  via CF
        f, C, D = 1e-30, 1e-30, 0.0
        for i in range(terms):
            # Coeficientes del CF de Abramowitz & Stegun 6.5.31
            if i == 0:
                an, bn = 1.0, x + 1.0 - a
            elif i % 2 == 1:
                m = (i + 1) // 2
                an = m * (a - m)
                bn += 2.0
            else:
                m = i // 2
                an = m
                bn += 2.0
            if i == 0:
                an = 1.0
                bn = x + 1.0 - a
            else:
                k = (i + 1) / 2
                an = k * (a - k) if i % 2 == 1 else k
                bn += 2.0
            D = bn + an * D
            if abs(D) < 1e-30: D = 1e-30
            C = bn + an / C
            if abs(C) < 1e-30: C = 1e-30
            D = 1.0 / D
            delta = C * D
            f *= delta
            if abs(delta - 1.0) < 1e-14:
                break
        Q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * f
        val = 1.0 - Q
    return max(0.0, min(1.0, val))

def _cdf_chi2(x, nu):
    """CDF de chi-cuadrado con nu grados de libertad: P(X <= x)."""
    if x <= 0:
        return 0.0
    return _gamma_inc_lower(nu/2, x/2)

def _pdf_chi2(x, nu):
    if x <= 0:
        return 0.0
    return math.exp((nu/2-1)*math.log(x) - x/2 - (nu/2)*math.log(2) - math.lgamma(nu/2))


# ── NUEVO 11: Distribucion F de Snedecor ─────────────────────────────
def _cdf_f(x, d1, d2):
    """CDF de F(d1,d2): usa la relacion con chi-sq via la beta incompleta.
    P(F<=x) = I_{d1*x/(d1*x+d2)}(d1/2, d2/2) — aproximado via _gamma_inc_lower."""
    if x <= 0:
        return 0.0
    # Transformacion a chi-sq equivalente (solo aprox. para d2 grande)
    t = d1 * x / (d1 * x + d2)
    # Usamos la serie de beta incompleta via relacion directa
    # I_t(a,b) = sum_{j=a}^{a+b-1} C(a+b-1,j) t^j (1-t)^(a+b-1-j)   [solo entero]
    # Para valores continuos usamos la aproximacion por chi-sq:
    chi2_equiv = d1 * x * d2 / (d1 * x + d2)   # aprox. chi-sq transformada
    return min(1.0, _gamma_inc_lower(d1/2, d1*x/2))


# ── Dispatcher DIST extendido (v5.6) ─────────────────────────────────
def cmd_conv(cmd):
    if MODO_EXAMEN:
        return _E_NODISP, "", ""
    try:
        resto = cmd.split("CONV", 1)[-1].strip().strip("()")
        partes = [p.strip() for p in resto.split(",")]
        if len(partes) < 3:
            return "Use CONV(val,DE,A)", "", ""
        valor = evaluar_expresion(partes[0], variables_actuales())
        de    = partes[1].upper()
        a     = partes[2].upper()

        # Temperatura (conversion no lineal)
        if de in _TEMP_UNIDADES or a in _TEMP_UNIDADES:
            # Convertir DE -> Celsius primero
            if de == "C":   c = valor
            elif de == "F": c = (valor - 32) * 5/9
            elif de == "K": c = valor - 273.15
            else: return f"Unidad desconocida: {de}", "", ""
            # Celsius -> A
            if a == "C":   res = c
            elif a == "F": res = c * 9/5 + 32
            elif a == "K": res = c + 273.15
            else: return f"Unidad desconocida: {a}", "", ""
            return f"{valor}{de} -> {a}", f"= {decimal_a_fraccion(round(res,6))}", ""

        # Otras unidades (base comun)
        if de not in _CONV_GRUPOS:
            return f"Unidad desconocida:", f"{de}", ""
        if a not in _CONV_GRUPOS:
            return f"Unidad desconocida:", f"{a}", ""
        base = valor * _CONV_GRUPOS[de]
        res  = base / _CONV_GRUPOS[a]
        return f"{valor} {de} -> {a}", f"= {decimal_a_fraccion(round(res,8))}", ""
    except Exception as ex:
        return f"Error CONV: {ex}"[:16], "", ""


# ═════════════════════════════════════════════════════════════════════
def procesar_todo(entrada_cruda):
    """Recibe el string ya con multiplicacion implicita resuelta
    (salida de construir_expresion) y despacha al modulo correcto."""
    global ANS
    cmd = entrada_cruda.upper()

    try:
        # ---- MEMORIA: STO / RCL ----
        if "STO" in cmd:
            return comando_sto(cmd), "", ""
        if "RCL" in cmd:
            return comando_rcl(cmd), "", ""

        # ---- ESTADISTICA ----
        # Carga dinámica de módulos pesados (libera RAM al salir del modo)
        if "STAT" in cmd:
            return procesar_estadistica(cmd.split("STAT")[-1])

        # ---- ALGEBRA Y CALCULO ----
        if "SOLVE" in cmd:
            return resolver_ecuacion_lineal(cmd.split("SOLVE")[-1]), "", ""
        if "MAT2" in cmd or "MAT3" in cmd or "DOT" in cmd or "CROSS" in cmd:
            return resolver_sistema_matrices(cmd)
        # NUEVO 2 (v5.2): modo VECTOR real (modulo + angulos de un vector)
        if "VEC2" in cmd or "VEC3" in cmd:
            return cmd_vector(cmd)
        if "DERIV" in cmd:
            # FIX v3.2: separador "," en vez de ";" (la coma SI existe en el
            # teclado fisico; el punto y coma no tiene tecla asignada).
            # Uso en placa: DERIV <funcion> , <punto>  ej: DERIVSIN(X),2
            partes = cmd.split("DERIV")[-1].split(",")
            return calcular_derivada(partes[0], partes[1]), "", ""
        if "INT" in cmd:
            # FIX v3.2: idem. Uso: INT<funcion>,<lim_inf>,<lim_sup>
            # calcular_integral espera limites_str="lim_inf,lim_sup", por eso
            # reconstruimos las dos partes de limite uniendo partes[1] y [2].
            partes = cmd.split("INT")[-1].split(",")
            limites = f"{partes[1]},{partes[2]}" if len(partes) >= 3 else partes[1]
            return calcular_integral(partes[0], limites), "", ""
        if "PRIMOS" in cmd:
            return f"Fact: {factorizar_primos(cmd.split('PRIMOS')[-1])}", "", ""
        if "MCD" in cmd:
            # FIX v3.2: evaluar argumentos antes de convertir a int, para que
            # MCD(A,B) o MCD(X,12) funcionen usando las variables de memoria.
            p = cmd.split("MCD")[-1].split(",")
            val1 = int(evaluar_expresion(p[0].strip("() "), variables_actuales()))
            val2 = int(evaluar_expresion(p[1].strip("() "), variables_actuales()))
            return f"MCD = {mcd(val1, val2)}", "", ""
        if "MCM" in cmd:
            p = cmd.split("MCM")[-1].split(",")
            val1 = int(evaluar_expresion(p[0].strip("() "), variables_actuales()))
            val2 = int(evaluar_expresion(p[1].strip("() "), variables_actuales()))
            return f"MCM = {mcm(val1, val2)}", "", ""

        # ---- NUEVO 1 (v5.0): NPR / NCR (permutaciones / combinaciones) ----
        # NPR(n,r) y NCR(n,r) (orden de chequeo: NPR antes que NCR no es
        # relevante, los nombres no se superponen). Igual que MCD/MCM,
        # se evaluan los argumentos para soportar variables (NPR(A,2)).
        if "NPR" in cmd:
            p = cmd.split("NPR")[-1].split(",")
            n = evaluar_expresion(p[0].strip("() "), variables_actuales())
            r = evaluar_expresion(p[1].strip("() "), variables_actuales())
            return f"NPR = {decimal_a_fraccion(calcular_npr(n, r))}", "", ""
        if "NCR" in cmd:
            p = cmd.split("NCR")[-1].split(",")
            n = evaluar_expresion(p[0].strip("() "), variables_actuales())
            r = evaluar_expresion(p[1].strip("() "), variables_actuales())
            return f"NCR = {decimal_a_fraccion(calcular_ncr(n, r))}", "", ""

        # ---- v4.0: NUEVAS FUNCIONES ----
        if "CMPLX" in cmd:
            return toggle_cmplx(), f"MODO_CMPLX={'ON' if MODO_COMPLEJO else 'OFF'}", ""
        if "CUAD" in cmd:
            return cmd_cuad(cmd)
        # NUEVO 6 (v5.5): CUART debe chequearse ANTES de CUB, porque
        # "CUB" no es substring de "CUART" pero por claridad y para
        # evitar futuros choques de nombre se ordena explicitamente
        # del mas especifico al mas general.
        if "CUART" in cmd:
            return cmd_cuart(cmd)
        if "CUB" in cmd and "COSH" not in cmd and "CROSS" not in cmd:
            return cmd_cub(cmd)
        # NUEVO 2 (v5.5): TABLE2 se chequea ANTES de TABLE, porque
        # "TABLE" SI es substring de "TABLE2" (TABLE2(...) contiene TABLE).
        if "TABLE2" in cmd:
            return cmd_table2(cmd)
        if "TABLE" in cmd:
            return cmd_table(cmd)
        if any(cmd.startswith(k) for k in ("BIN", "OCT", "HEX", "AND", "OR", "XOR", "NOT")):
            return cmd_basen(cmd)
        if "MATDEF" in cmd:
            return cmd_matdef(cmd)
        if "MATADD" in cmd:
            return cmd_matadd(cmd)
        if "MATMUL" in cmd:
            return cmd_matmul(cmd)
        if "MATTRANS" in cmd:
            return cmd_mattrans(cmd)
        if "MATDET" in cmd:
            return cmd_matdet(cmd)
        if "MATINV" in cmd:
            return cmd_matinv(cmd)

        # ---- CONVERSIONES POLARES / RECTANGULARES (NUEVO 3 - v5.3) ----
        # POL/REC ahora respetan MODO_ANGULOS (DEG/RAD) via cmd_pol/cmd_rec.
        if "POL" in cmd:
            return cmd_pol(cmd)
        if "REC" in cmd:
            return cmd_rec(cmd)

        # ---- CONVERSION SEXAGESIMAL DMS (NUEVO 4 - v5.5) ----
        # TODMS se chequea antes de DMS porque "DMS" es substring de "TODMS".
        if "TODMS" in cmd:
            return cmd_todms(cmd)
        if "DMS" in cmd:
            return cmd_dms(cmd)

        # ---- ALEATORIO Y RAIZ ANALITICA ----
        if "RAND" in cmd:
            return f"Rand: {time.time() % 1:.5f}", "", ""
        # NUEVO 7 (v5.5): RAIZN se chequea antes de RAIZ porque "RAIZ"
        # es substring de "RAIZN".
        if "RAIZN" in cmd:
            return cmd_raizn(cmd)
        if "RAIZ" in cmd:
            return calcular_raiz_analitica(cmd.split("RAIZ")[-1]), "", ""

        # ---- ECUACIONES SIMULTANEAS (NUEVO 1 - v5.3) ----
        if "SIMU" in cmd:
            return cmd_simu(cmd)

        # ---- EDITOR DE MATRICES (NUEVO 4 - v5.3) ----
        if "MATEDIT" in cmd:
            return cmd_matedit(cmd)

        # ---- DISTRIBUCIONES ESTADISTICAS (NUEVO 1 - v5.5) ----
        if "DIST" in cmd:
            return cmd_dist(cmd)

        # ---- MODO SHEET (NUEVO 5 - v5.5) ----
        if cmd == "SHEET":
            return cmd_sheet(cmd)

        # ---- v4.5: PERSISTENCIA, SETUP, TESTS ----
        if cmd == "SAVE":
            return guardar_estado(), "", ""
        if cmd.startswith("SETUP"):
            return cmd_setup(cmd)
        if cmd == "TEST":
            return run_tests()

        # ── NUEVO v5.6: comandos nuevos ──────────────────────────────
        if "RANINT" in cmd:
            r = cmd_ranint(cmd)
            _hist_guardar(entrada_cruda[:20], str(r[1])[:28])
            return r
        if cmd.startswith("MOD"):
            return cmd_mod(cmd)
        if cmd.startswith("SUM"):
            r = cmd_sum(cmd)
            if not r[0].startswith("Err"): _hist_guardar(entrada_cruda[:20], r[1][:28])
            return r
        if cmd.startswith("PROD"):
            r = cmd_prod(cmd)
            if not r[0].startswith("Err"): _hist_guardar(entrada_cruda[:20], r[1][:28])
            return r
        if cmd.startswith("CONV"):
            return cmd_conv(cmd)
        if cmd.startswith("AFRAC"):
            return cmd_afrac(cmd)
        if any(cmd.startswith(k) for k in ("DISTT", "DISTCHI", "DISTF", "DISTHG", "INVT")):
            r = cmd_dist_ext(cmd)
            if not r[0].startswith("Err"): _hist_guardar(entrada_cruda[:20], r[1][:28])
            return r

        # ---- EVALUACION GENERAL (Shunting-yard + RPN, sin eval) ----
        res_num = evaluar_expresion(cmd, variables_actuales())
        ANS = res_num
        res_str = decimal_a_fraccion(res_num)
        # NUEVO 14 (v5.6): guardar en historial resultados validos
        if not str(res_str).startswith("Err"):
            _hist_guardar(entrada_cruda[:20], str(res_str)[:28])
        return res_str, "", ""
    except (ValueError, ZeroDivisionError) as e:
        # FIX 6 (v4.4): mostrar el mensaje real del error al usuario.
        # "Division por cero", "Token desconocido: X", "Numero invalido: 1.2.3", etc.
        msg = str(e)
        return msg[:16] if len(msg) > 16 else msg, "", ""
    except Exception as e:
        # Error inesperado (bug real): mostrar tipo para facilitar debugging
        return f"Err:{type(e).__name__}", "", ""


# ── 13. BUCLE DE EJECUCION (PC / PICO)  -  v4.3 ────
INSTRUCCIONES = (
    "PiCalc OS v5.6 - Cada linea = un TOKEN (un boton).\n"
    "Numeros/operadores: 0-9 . + - * / ^ % ( ) , =\n"
    "Funciones: SIN COS TAN ASIN ACOS ATAN SINH COSH TANH LN LOG EXP SQRT RAIZ ABS\n"
    "Combinatoria: FACT(n)  NPR(n,r)  NCR(n,r)\n"
    "Complejo: CMPLX  CONJ(z)  ARG(z)\n"
    "Vectores: VEC2(x,y)  VEC3(x,y,z)  DOT(...)  CROSS(...)\n"
    "Memoria: A-Z (sin E,I) + ANS  |  STO RCL\n"
    "Calculo: SOLVE  DERIV<f>,<x>  INT<f>,<a>,<b>  MCD MCM PRIMOS\n"
    "Sumatorias: SUM(expr,var,ini,fin)  PROD(expr,var,ini,fin)\n"
    "Aleatorio: RAND (uniform)  RANINT(a,b) (entero)\n"
    "Resto: MOD(a,b)   Conversion S<->D: AFRAC(x)\n"
    "Sistemas: SIMU2 SIMU3 SIMU4  |  Matrices: MAT2 MAT3 DOT CROSS\n"
    "Algebra matricial: MATDEF MATADD MATMUL MATTRANS MATDET MATINV\n"
    "Editor matrices: MATEDIT<A>,<f>,<c>\n"
    "Polinomios: CUAD  CUB  CUART\n"
    "Tabla: TABLE<f>,<ini>,<fin>,<paso>  TABLE2<f>,<g>,<ini>,<fin>,<paso>\n"
    "  Tras TABLE: IZQ/DER navega filas\n"
    "Base-N: BIN OCT HEX AND OR XOR NOT\n"
    "Estadistica: STATADD:<v>  STATX<x>,<y>  STATCALC  STATCLEAR\n"
    "  Regresiones: STATLIN STATCUAD STATEXP STATLOG STATPOT\n"
    "Distribuciones (2ND->DIST): 1NPD 2NCD 3BIN 4POI 5t 6Chi2 7F 8HG\n"
    "  DISTNPD(x,mu,s)  DISTNCD(a,b,mu,s)  DISTBIN(k,n,p)  DISTPOI(k,lam)\n"
    "  DISTT(x,nu)  DISTCHI(x,nu)  DISTF(x,d1,d2)  DISTHG(k,N,K,n)  INVT(p,nu)\n"
    "Conversiones: CONV(val,DE,A)  DMS(g,m,s)  TODMS(val)  POL  REC\n"
    "  Unidades: M KM MI FT IN CM | KG G LB OZ | L ML GAL | C F K | J KJ CAL\n"
    "  Presion: PA KPA ATM PSI | Velocidad: MS KMH MPH | Energia: WH KWH EV BTU\n"
    "SETUP: SETUPDEG/RAD  SETUPFIX<n>  SETUPSCI<n>  SETUPNORM  SETUPENG\n"
    "Historial: 2ND->HIST  IZQ/DER navega  IGUAL=recargar  AC=salir\n"
    "Hoja de calculo: SHEET  SHEETUP  SHEETDOWN  | tipea =formula e IGUAL\n"
    "Radicales: RAIZ(n)  RAIZN(n,k)\n"
    "Control: AC DEL IGUAL BYPASS SAVE MODE(1-8)\n"
    "Cursor IZQ/DER para editar | 2ND activa capa secundaria del teclado"
)

def _pos_caracter_cursor(tokens, cursor_pos):
    """Convierte CURSOR_POS (indice de token) en indice de caracter
    dentro del string 'join(tokens)', para que el cursor visual '|'
    aparezca en el lugar correcto."""
    return sum(len(t) for t in tokens[:cursor_pos])


# Registrar funciones del núcleo en el puente de módulos.
# Debe ejecutarse ANTES de cualquier _cargar_*() call.
def _registrar_bridge():
    pc_bridge.registrar(
        evaluar_fn  = evaluar_expresion,
        decimal_fn  = decimal_a_fraccion,
        variables_fn = variables_actuales,
        extraer_fn  = extraer_numeros,
        matrices_dict = MATRICES,
    )

def iniciar():
    _registrar_bridge()  # conectar módulos externos
    gc.collect()  # limpiar RAM post-import
    global MODO_EXAMEN, ENTRADA_TOKENS, CURSOR_POS, EN_MENU_MODE, _SELECCION_MENU
    global TABLA_INDICE, EN_MENU_EQN, EN_MODO_SHEET
    global EN_HIST, HIST_INDICE, EN_MENU_DIST

    # NUEVO 1 (v4.5): cargar estado guardado en flash al arrancar.
    # En primer arranque el archivo no existe y cargar_estado devuelve False.
    estado_cargado = cargar_estado()

    renderizar_pantalla("PiCalc OS v5.7", f"Examen: {'ACTIVO' if MODO_EXAMEN else 'INACTIVO'}",
                        "AC/DEL/IGUAL", "BYPASS = modo")

    if not ENTORNO_PICO:
        print(INSTRUCCIONES)

    while True:
        if ENTORNO_PICO:
            accion = escanear_teclado()
            if accion is None:
                time.sleep(0.02)
                continue
        else:
            accion = input("\nToken/Comando > ").strip()
            if accion == "":
                continue

        accion_u = accion.upper()

        if EN_MENU_MODE:
            if accion_u == "AC":
                EN_MENU_MODE = False
                expr_actual = "".join(ENTRADA_TOKENS) or "0"
                cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
                renderizar_pantalla(expr_actual, cursor_pos=cur_ch)
            elif accion_u in ("IZQ", "DER"):
                # FIX 4 (v4.4): IZQ/DER mueven _SELECCION_MENU sin pisar MODO_CALC.
                # El modo confirmado no cambia hasta que el usuario presione IGUAL
                # o un digito. Esto replica el comportamiento de la Casio fx-991:
                # el resaltado se mueve pero nada se aplica hasta la confirmacion.
                delta = -1 if accion_u == "IZQ" else 1
                _SELECCION_MENU = ((_SELECCION_MENU - 1 + delta) % 8) + 1
                renderizar_menu_mode(_SELECCION_MENU)
            elif accion_u == "IGUAL":
                # Confirmar la seleccion resaltada por IZQ/DER
                msg = aplicar_modo(_SELECCION_MENU)
                if EN_MENU_EQN:
                    renderizar_menu_eqn()
                else:
                    renderizar_pantalla(msg, f"Modo: {MODO_CALC_NOMBRES[MODO_CALC]}",
                                         SUGERENCIAS_MODO.get(MODO_CALC, ""))
            elif accion_u.isdigit() and 1 <= int(accion_u) <= 8:
                num = int(accion_u)
                _SELECCION_MENU = num
                msg = aplicar_modo(num)
                if EN_MENU_EQN:
                    renderizar_menu_eqn()
                else:
                    renderizar_pantalla(msg, f"Modo: {MODO_CALC_NOMBRES[MODO_CALC]}",
                                         SUGERENCIAS_MODO.get(MODO_CALC, ""))
            else:
                renderizar_menu_mode(_SELECCION_MENU)
            continue

        if EN_MENU_EQN:
            if accion_u == "AC":
                EN_MENU_EQN = False
                expr_actual = "".join(ENTRADA_TOKENS) or "0"
                cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
                renderizar_pantalla(expr_actual, cursor_pos=cur_ch)
            elif accion_u.isdigit() and aplicar_eqn(int(accion_u)):
                expr_actual = "".join(ENTRADA_TOKENS)
                cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
                renderizar_pantalla(expr_actual, "Completa los datos",
                                    "e IGUAL", cursor_pos=cur_ch)
            else:
                renderizar_menu_eqn()
            continue

        # ==================================================
        # MODO SHEET (NUEVO 5 - v5.5): captura IZQ/DER/AC/IGUAL
        # de forma distinta mientras esta activo. IZQ/DER mueven
        # columna; SHEETUP/SHEETDOWN mueven fila (no hay mas teclas
        # de flecha fisicas disponibles en el layout de 6x8).
        # IGUAL confirma el contenido tipeado en ENTRADA_TOKENS como
        # el valor/formula de la celda actual. AC sale del modo SHEET.
        # ==================================================
        if EN_MODO_SHEET:
            if accion_u == "AC":
                if ENTRADA_TOKENS:
                    # Primer AC: solo limpia el buffer de edicion de la celda
                    ENTRADA_TOKENS = []
                    CURSOR_POS = 0
                    renderizar_sheet()
                else:
                    # Buffer ya vacio: AC sale del modo SHEET
                    EN_MODO_SHEET = False
                    expr_actual = "0"
                    renderizar_pantalla(expr_actual, cursor_pos=0)
                continue
            if accion_u == "IZQ":
                sheet_mover("IZQ")
                continue
            if accion_u == "DER":
                sheet_mover("DER")
                continue
            if accion_u == "SHEETUP":
                sheet_mover("ARRIBA")
                continue
            if accion_u == "SHEETDOWN":
                sheet_mover("ABAJO")
                continue
            if accion_u == "IGUAL":
                # FIX (v5.5): NO usar construir_expresion() aqui, porque
                # insertaria multiplicacion implicita entre referencias de
                # celda como "A1" (token "A" + token "1" -> "A*1"), rompiendo
                # el regex de _evaluar_celda. Las celdas se unen tal cual.
                texto = "".join(ENTRADA_TOKENS) if ENTRADA_TOKENS else ""
                sheet_ingresar_celda(texto)
                ENTRADA_TOKENS = []
                CURSOR_POS = 0
                continue
            if accion_u == "DEL":
                if CURSOR_POS > 0:
                    ENTRADA_TOKENS.pop(CURSOR_POS - 1)
                    CURSOR_POS -= 1
                col, fila = SHEET_CURSOR
                renderizar_pantalla(f"{col}{fila}: " + "".join(ENTRADA_TOKENS),
                                    cursor_pos=_pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS) + len(f"{col}{fila}: "))
                continue
            # Cualquier otro token (numeros, operadores, "=") se acumula
            # en ENTRADA_TOKENS igual que en modo normal, para despues
            # confirmarlo con IGUAL.
            token = ALIAS_TOKENS.get(accion_u, None)
            if token is None:
                token = accion_u if accion_u in ALIAS_TOKENS.values() else accion
            ENTRADA_TOKENS.insert(CURSOR_POS, token)
            CURSOR_POS += 1
            col, fila = SHEET_CURSOR
            prefijo = f"{col}{fila}: "
            renderizar_pantalla(prefijo + "".join(ENTRADA_TOKENS),
                                cursor_pos=_pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS) + len(prefijo))
            continue

        # ==================================================
        # TECLAS DE CONTROL PRINCIPALES
        # ==================================================

        # ---- BYPASS: toggle modo examen ----
        if accion_u == "BYPASS":
            MODO_EXAMEN = not MODO_EXAMEN
            # FIX 3 (v5.2): texto legible en vez del booleano crudo
            # "Modo Examen: True/False".
            estado = "ACTIVO" if MODO_EXAMEN else "INACTIVO"
            expr_actual = "".join(ENTRADA_TOKENS) or "0"
            cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
            renderizar_pantalla(expr_actual, f"Examen: {estado}",
                                cursor_pos=cur_ch)
            continue

        # ── NUEVO v5.6: HISTORIAL ────────────────────────────────────
        if EN_HIST:
            if accion_u == "AC":
                EN_HIST = False
                renderizar_pantalla("".join(ENTRADA_TOKENS) or "0",
                                    cursor_pos=_pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS))
            elif accion_u in ("IZQ", "DER"):
                delta = 1 if accion_u == "IZQ" else -1
                HIST_INDICE = (HIST_INDICE + delta) % max(1, len(HISTORIAL))
                renderizar_hist_entrada(HIST_INDICE)
            elif accion_u == "IGUAL" and HISTORIAL:
                expr_h = HISTORIAL[-(HIST_INDICE+1)]["expr"]
                ENTRADA_TOKENS = list(expr_h)
                CURSOR_POS = len(ENTRADA_TOKENS)
                EN_HIST = False
                renderizar_pantalla("".join(ENTRADA_TOKENS), "Recargado",
                                    cursor_pos=_pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS))
            else:
                renderizar_hist_entrada(HIST_INDICE)
            continue

        # ── NUEVO v5.6: SUBMENU DIST ─────────────────────────────────
        if EN_MENU_DIST:
            _DIST_OPTS = {
                "1":"DISTNPD(", "2":"DISTNCD(", "3":"DISTBIN(",
                "4":"DISTPOI(", "5":"DISTT(", "6":"DISTCHI(",
                "7":"DISTF(", "8":"DISTHG(",
            }
            if accion_u == "AC":
                EN_MENU_DIST = False
                renderizar_pantalla("".join(ENTRADA_TOKENS) or "0",
                                    cursor_pos=_pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS))
            elif accion_u in _DIST_OPTS:
                ENTRADA_TOKENS = [_DIST_OPTS[accion_u]]
                CURSOR_POS = 1
                EN_MENU_DIST = False
                renderizar_pantalla("".join(ENTRADA_TOKENS), "Completa args e IGUAL")
            else:
                renderizar_pantalla(
                    "=== DIST ===",
                    "1NPD 2NCD 3BIN 4POI",
                    "5t  6Chi2 7F  8HG",
                    "AC=salir")
            continue

        # ---- MODE: abrir menu de modos (v4.3) ----
        if accion_u == "MODE":
            EN_MENU_MODE = True
            renderizar_menu_mode()
            continue

        # ---- HIST: abrir vista de historial (v5.6) ----
        if accion_u == "HIST":
            EN_HIST = True
            HIST_INDICE = 0
            renderizar_hist_entrada(0)
            continue

        # ---- DIST: abrir submenu de distribuciones (v5.6) ----
        if accion_u == "DIST":
            EN_MENU_DIST = True
            renderizar_pantalla(
                "=== DIST ===",
                "1NPD 2NCD 3BIN 4POI",
                "5t  6Chi2 7F  8HG",
                "AC=salir")
            continue

        # ---- AC: limpiar todo y resetear cursor ----
        if accion_u == "AC":
            ENTRADA_TOKENS = []
            CURSOR_POS = 0
            renderizar_pantalla("0", cursor_pos=0)
            continue

        # ---- DEL: borrar token a la IZQUIERDA del cursor (v4.3) ----
        if accion_u == "DEL":
            if CURSOR_POS > 0:
                ENTRADA_TOKENS.pop(CURSOR_POS - 1)
                CURSOR_POS -= 1
            expr_actual = "".join(ENTRADA_TOKENS) or "0"
            cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
            renderizar_pantalla(expr_actual, cursor_pos=cur_ch)
            continue

        # ---- IZQ: mover cursor a la izquierda, o retroceder en TABLE (v5.2) ----
        if accion_u == "IZQ":
            # NUEVO 1 (v5.2): si el buffer esta vacio y hay una TABLE
            # generada, IZQ/DER navegan filas en vez de mover el cursor
            # (que no tiene nada para mover en un buffer vacio).
            if not ENTRADA_TOKENS and TABLA_RESULTADO:
                TABLA_INDICE = (TABLA_INDICE - 1) % len(TABLA_RESULTADO)
                renderizar_tabla_fila()
                continue
            if CURSOR_POS > 0:
                CURSOR_POS -= 1
            expr_actual = "".join(ENTRADA_TOKENS) or "0"
            cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
            renderizar_pantalla(expr_actual, cursor_pos=cur_ch)
            continue

        # ---- DER: mover cursor a la derecha, o avanzar en TABLE (v5.2) ----
        if accion_u == "DER":
            if not ENTRADA_TOKENS and TABLA_RESULTADO:
                TABLA_INDICE = (TABLA_INDICE + 1) % len(TABLA_RESULTADO)
                renderizar_tabla_fila()
                continue
            if CURSOR_POS < len(ENTRADA_TOKENS):
                CURSOR_POS += 1
            expr_actual = "".join(ENTRADA_TOKENS) or "0"
            cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
            renderizar_pantalla(expr_actual, cursor_pos=cur_ch)
            continue

        # ---- IGUAL: calcular ----
        if accion_u == "IGUAL":
            # NUEVO 4 (v5.3): si el editor de matrices esta activo,
            # IGUAL confirma el valor de la celda actual en vez de
            # evaluar la expresion como calculo normal.
            if _MATEDIT_ESTADO["activo"] and ENTRADA_TOKENS:
                valor_str = construir_expresion(ENTRADA_TOKENS)
                l1, l2, l3 = matedit_ingresar(valor_str)
                renderizar_pantalla(l1, l2, l3)
                ENTRADA_TOKENS = []
                CURSOR_POS = 0
                continue

            if ENTRADA_TOKENS:
                expr = construir_expresion(ENTRADA_TOKENS)
                texto_anterior = "".join(ENTRADA_TOKENS)
                l1, l2, l3 = procesar_todo(expr)
                # Mostrar resultado SIN cursor (igual que la Casio fisica
                # al mostrar el resultado: el cursor desaparece hasta que
                # el usuario empiece a escribir de nuevo).
                renderizar_pantalla(texto_anterior, l1, l2, l3)
                # FIX v3.2: solo limpiamos si no hubo error.
                if l1 != _E_SIN:
                    ENTRADA_TOKENS = []
                    CURSOR_POS = 0
            continue

        token = ALIAS_TOKENS.get(accion_u, None)
        if token is None:
            token = accion_u if accion_u in ALIAS_TOKENS.values() else accion

        # NEW v4.3: insertar en CURSOR_POS en vez de al final
        ENTRADA_TOKENS.insert(CURSOR_POS, token)
        CURSOR_POS += 1

        expr_actual = "".join(ENTRADA_TOKENS)
        cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
        renderizar_pantalla(expr_actual, cursor_pos=cur_ch)

if __name__ == "__main__":
    iniciar()
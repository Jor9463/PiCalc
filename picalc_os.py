import time
import math
import cmath
import json  # persistencia en flash (Pico usa ujson; mismo API)

# ==========================================================
# PiCalc OS v5.0  –  Changelog desde v4.5
# ----------------------------------------------------------
# NUEVO 1 (FACT/NPR/NCR - CRITICO):
#   Se agregan FACT(n) (n!), NPR(n,r) (permutaciones) y
#   NCR(n,r) (combinaciones) como funciones de teclado (capa 2ND).
#   FACT acepta enteros no negativos hasta 170 (limite de float
#   antes de overflow). NPR/NCR validan 0<=r<=n.
#
# NUEVO 2 (CONJ/ARG en CMPLX):
#   CONJ(a+bi) devuelve el conjugado a-bi. ARG(a+bi) devuelve el
#   angulo (en DEG o RAD segun MODO_ANGULOS) del numero complejo.
#   Ambas solo tienen sentido con MODO_COMPLEJO activo; si se
#   usan sobre un real, ARG da 0 y CONJ da el mismo numero.
#
# NUEVO 3 (SETUP completo: FIX/SCI/NORM + RAD real):
#   - FIX 0 (V4.5 BUG): MODO_ANGULOS="RAD" se guardaba pero NUNCA
#     se usaba en evaluar_rpn(), que siempre convertia grados<->rad
#     sin importar el modo. Ahora SIN/COS/TAN/ASIN/ACOS/ATAN
#     respetan MODO_ANGULOS=DEG/RAD (en RAD no se hace conversion).
#   - SETUPFIX<n> fija decimales (FIX 0-9). SETUPSCI activa
#     notacion cientifica. SETUPNORM vuelve al formato automatico
#     (fracciones + 5 decimales, comportamiento v4.x). Estos
#     formatos se aplican en decimal_a_fraccion() para numeros
#     reales (no afectan fracciones exactas en NORM).
#
# NUEVO 4 (STAT con regresion lineal):
#   STATX<x>,<y> agrega un par (x,y) a dos listas paralelas.
#   STATCALC ahora, si hay datos pareados, ademas de N/Media/Var
#   devuelve "a=...  b=..." (y=a+bx) y el coeficiente "r=...".
#   STATCLEAR limpia ambas listas. El modo de 1 variable (ADD:v)
#   sigue funcionando igual que en v4.5.
# ==========================================================
# ==========================================================
# PiCalc OS v4.5  –  Changelog desde v4.4 (historico)
# ----------------------------------------------------------
# FIX 1 (CRITICO - _evaluar_entero en BASE-N):
#   Ahora valida que el resultado no sea complex ni NaN antes
#   de convertir a int. BIN(3+2I) antes daba comportamiento
#   indefinido; ahora devuelve "No soporta complejos en BASE-N".
#
# FIX 2 (COSMÉTICA - comentarios de version obsoletos):
#   Referencias a "FIX v4.2", "FIX v3.2" etc. en el codigo
#   ahora indican la version original de aplicacion, sin
#   confusion con el numero de version actual v4.5.
#
# FIX 3 (COSMÉTICA - cmd_table con paso negativo documentado):
#   Los dos branches del bucle TABLE tienen comentarios que
#   explican la logica del rango para paso positivo y negativo.
#
# FIX 4 (COSMÉTICA - SETUP reconocido y procesado):
#   cmd_setup() atiende la tecla SETUP del teclado fisico:
#   muestra angulos DEG/RAD, decimales FIX 0-9 y estado RAM.
#   Ya no pasa silenciosa sin feedback al usuario.
#
# NUEVO 1 (PERSISTENCIA EN FLASH):
#   guardar_estado() y cargar_estado() usan json (PC) o ujson
#   (MicroPython) para guardar MEMORIA, ANS, MODO_CALC,
#   MODO_COMPLEJO y MATRICES en /picalc_state.json (Pico) o
#   ./picalc_state.json (PC) entre reinicios. Se cargan al
#   arrancar y se guardan con el token SAVE (capa 2ND).
#
# NUEVO 2 (VARIABLES COMPLEJAS EN MEMORIA - documentado):
#   MEMORIA["A"] puede guardar un valor complex (3+2i).
#   Comportamiento intencional, identico a la fx-991 en CMPLX
#   mode. BASE-N rechaza valores complejos (ver FIX 1).
#
# NUEVO 3 (TEST SUITE integrada):
#   run_tests() ejecuta casos edge criticos en consola PC:
#   raices negativas sin CMPLX, division por cero, "1.2.3",
#   parentesis desbalanceados, TABLE overflow, MCD con vars.
#   Token "TEST" en consola (bloqueado en MODO_EXAMEN).
# ==========================================================

# ==========================================================
# 1. DETECCION DE ENTORNO Y HARDWARE
# ==========================================================
try:
    import machine
    import sh1106
    ENTORNO_PICO = True
except ImportError:
    ENTORNO_PICO = False

# ---- Estado global ----
MODO_EXAMEN = True  # True = Modo bloqueado (Clase) | False = CAS / ClassWiz completo
MEMORIA = {"A": 0.0, "B": 0.0, "C": 0.0, "X": 0.0, "Y": 0.0}
ANS = 0.0
ESTADISTICA_LISTA = []
# NUEVO 4 (v5.0): segunda lista paralela para datos pareados (x,y),
# usada por STATX para regresion lineal. len() siempre igual a
# ESTADISTICA_LISTA si hay datos pareados; vacia en modo 1-variable.
ESTADISTICA_LISTA_Y = []
ENTRADA_TOKENS = []
CURSOR_POS = 0          # NEW v4.3: indice de insercion dentro de ENTRADA_TOKENS
LIMITE_ESTADISTICA = 50  # cuida la RAM de la Pico

# ---- Estado v4.0 ----
MODO_COMPLEJO = False
MATRICES = {"A": None, "B": None, "C": None}
TABLA_RESULTADO = []

# ---- Estado v4.3: Modo de calculadora (menu MODE) ----
# 1=COMP, 2=CMPLX, 3=STAT, 4=BASE-N, 5=EQN, 6=MATRIX, 7=TABLE, 8=VECTOR
MODO_CALC = 1
MODO_CALC_NOMBRES = {
    1: "COMP", 2: "CMPLX", 3: "STAT",  4: "BASE-N",
    5: "EQN",  6: "MATRIX", 7: "TABLE", 8: "VECTOR",
}
EN_MENU_MODE = False

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
    "PRIMOS", "CUAD", "CUB", "TABLE", "BIN", "OCT", "HEX",
    "AND", "OR", "XOR", "NOT", "CMPLX", "DIST",
})

display = None
if ENTORNO_PICO:
    try:
        i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
        display = sh1106.SH1106_I2C(128, 64, i2c)
        display.sleep(False)
    except Exception:
        pass


# ==========================================================
# 2. MATRIZ DE TECLADO FISICO (6 filas x 8 columnas = 48 teclas)
# ==========================================================
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
    ["IZQ", "DER", "MODE", "SETUP", "", "", "", ""],
]

# Capa secundaria (tecla 2ND/SHIFT): funciones avanzadas poco usadas.
LAYOUT_TECLADO_2ND = [
    ["SOLVE", "DERIV", "INT", "STAT", "MAT2(", "MAT3(", "DOT(", "CROSS("],
    ["POL(", "REC(", "PRIMOS", "MCD", "MCM", "RAND", "SINH(", "COSH("],
    ["TANH(", "CMPLX", "CUAD(", "CUB(", "TABLE", "BIN(", "OCT(", "HEX("],
    ["MATDEF", "MATADD", "MATMUL", "MATTRANS", "MATDET", "MATINV", "SAVE", "TEST"],
    # NUEVO (v5.0): FACT(n!), NPR/NCR (permutaciones/combinaciones),
    # CONJ/ARG (numeros complejos), STATX (regresion lineal pareada).
    ["FACT(", "NPR(", "NCR(", "CONJ(", "ARG(", "STATX", "STATCLEAR", ""],
    ["", "", "", "", "", "", "", ""],
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


# ==========================================================
# 3. CAPA DE SALIDA / RENDERIZADO VISUAL
# ==========================================================
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


# ==========================================================
# 4. AYUDANTES MATEMATICOS Y ALGEBRA BASICA
# ==========================================================
def mcd(a, b):
    while b:
        a, b = b, a % b
    return a


def mcm(a, b):
    return abs(a * b) // mcd(a, b) if (a and b) else 0


def factorizar_primos(n):
    if MODO_EXAMEN:
        return "Error: No disp"
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


# ==========================================================
# 4b. COMBINATORIA: FACT (n!), NPR (permutaciones), NCR (combinaciones)
#     (NUEVO 1 - v5.0)
# ==========================================================
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


# ==========================================================
# 5. MOTOR DE EXPRESIONES (SHUNTING-YARD + RPN)
# ==========================================================
# Reemplaza por completo el uso de eval(). Convierte un string infijo
# (ej: "SIN(30)+2^3") en una lista RPN mediante el algoritmo de Dijkstra
# y la evalua con una pila, sin pasar nunca por el interprete de Python.
#
# Modo de angulos (DEG):
#   - SIN/COS/TAN    -> convierten el argumento de grados a radianes
#   - ASIN/ACOS/ATAN -> convierten el resultado de radianes a grados
#   - El resto de funciones (hiperbolicas, logaritmos, raiz, exp) no
#     dependen del modo de angulo.
#
# Variables reconocidas: A, B, C, X, Y (memoria) y ANS (ultimo resultado).
#
# NOTA (v4.2):
#   El menos unario ahora tiene dos comportamientos segun el contexto
#   (ver FIX 6 arriba): "-3^2" = -(3^2) = -9 (convencion estandar) y
#   "2^-2" = 2^(-2) = 0.25 (exponente negativo). Ambos casos frecuentes
#   funcionan correctamente sin necesidad de parentesis adicionales.

FUNC_MAP = {
    "SIN":  (math.sin,  "deg_in"),
    "COS":  (math.cos,  "deg_in"),
    "TAN":  (math.tan,  "deg_in"),
    "ASIN": (math.asin, "deg_out"),
    "ACOS": (math.acos, "deg_out"),
    "ATAN": (math.atan, "deg_out"),
    "SINH": (math.sinh, None),
    "COSH": (math.cosh, None),
    "TANH": (math.tanh, None),
    "LN":   (math.log,   None),
    "LOG":  (math.log10, None),
    "EXP":  (math.exp,   None),
    "SQRT": (math.sqrt,  None),
    "RAIZ": (math.sqrt,  None),
    "ABS":  (abs,        None),
    # NUEVO 1 (v5.0): factorial. modo="fact" -> manejo especial en
    # evaluar_rpn (valida entero >=0, usa calcular_factorial).
    "FACT": (calcular_factorial, "fact"),
    # NUEVO 2 (v5.0): CONJ y ARG para numeros complejos. modo="cplx_*"
    # -> manejo especial en evaluar_rpn (funcionan en real Y complejo).
    "CONJ": (lambda x: x, "cplx_conj"),
    "ARG":  (lambda x: 0.0, "cplx_arg"),
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
                # Menos unario -> token especial NEG (o NEGL)
                # FIX v4.2: distinguimos dos casos de menos unario mediante
                # dos tokens de pila distintos, para que la comparacion de
                # precedencias en _debe_pop funcione correctamente:
                #  - NEG  (precedencia maxima): el "-" viene justo despues
                #    de "^", ej "2^-2" = 2^(-2) = 0.25
                #  - NEGL (precedencia baja, "Leading"): cualquier otro
                #    menos unario, ej "-3^2" = -(3^2) = -9 (convencion
                #    matematica estandar)
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

            # NUEVO 1 (v5.0): FACT - factorial, siempre real, valida entero.
            if val == "FACT":
                if isinstance(arg, complex):
                    raise ValueError("FACT: no soporta complejos")
                pila.append(calcular_factorial(arg))
                continue

            # NUEVO 2 (v5.0): CONJ y ARG - operan sobre real O complejo.
            if val == "CONJ":
                pila.append(arg.conjugate() if isinstance(arg, complex) else arg)
                continue
            if val == "ARG":
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

            if MODO_COMPLEJO and val in FUNC_MAP_CMPLX:
                fn = FUNC_MAP_CMPLX[val]
                # grados -> radianes para trig en modo complejo (solo si DEG)
                if FUNC_MAP[val][1] == "deg_in" and usar_grados:
                    arg = cmath.pi * arg / 180
                resultado = fn(arg)
                if FUNC_MAP[val][1] == "deg_out" and usar_grados:
                    resultado = cmath.phase(resultado) * 180 / cmath.pi
                elif FUNC_MAP[val][1] == "deg_out":
                    resultado = cmath.phase(resultado)
            else:
                fn, modo = FUNC_MAP[val]
                if modo == "deg_in" and usar_grados:
                    arg = math.radians(arg)
                resultado = fn(arg)
                if modo == "deg_out" and usar_grados:
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


# ==========================================================
# 6. NUCLEO MATEMATICO AVANZADO
# ==========================================================
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

    # NUEVO 3 (v5.0): FIX/SCI fuerzan un formato fijo, salteando el
    # chequeo de entero y la aproximacion a fraccion de NORM. Los
    # complejos arriba NO se ven afectados (siempre usan el estilo
    # Casio "a+bi"); FIX/SCI son solo para el camino "real" de abajo.
    if FORMATO_NUM == "FIX":
        try:
            return f"{val:.{FORMATO_DECIMALES}f}"
        except Exception:
            return f"{val:.5f}"
    if FORMATO_NUM == "SCI":
        try:
            return f"{val:.{FORMATO_DECIMALES}e}"
        except Exception:
            return f"{val:.5e}"

    # FIX v4.2: el chequeo de entero y la aproximacion a fraccion se aplican
    # SIEMPRE, incluso en MODO_EXAMEN. Antes, en examen (modo por defecto),
    # todo numero real pasaba directo a "{val:.5f}" sin filtrar los .0 ni
    # intentar fraccion, por lo que 2+3*4 mostraba "14.00000" en vez de "14".
    try:
        val = round(val, 10)
        if isinstance(val, int) or val.is_integer():
            return str(int(val))

        # FIX v4.2: aproximacion por fracciones continuas.
        # El metodo anterior (val*100000 / mcd con 100000) casi nunca
        # encontraba fracciones simples: 1/3 = 0.3333333333 ->
        # mcd(33333,100000)=1, asi que 1/3 nunca se reconstruia como
        # "1/3". El algoritmo de fracciones continuas SI encuentra
        # 1/3, 2/3, 1/7, 22/7, etc. con denominador < 1000.
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


# ==========================================================
# 7. SOLVER, MATRICES Y VECTORES (ALGEBRA REAL)
# ==========================================================
def resolver_ecuacion_lineal(eq_str):
    """Resuelve f(x) = 0 o f(x) = g(x) mediante Newton-Raphson (25 iter max).

    FIX v3.1 - Transformación segura de la ecuación:
      En vez de eq.replace("=", "-(") + ")" que corrompe paréntesis internos
      (ej: SIN(X)=0.5 → SIN(X-(0.5) — paréntesis del seno queda abierto),
      buscamos el índice EXACTO del "=" de igualdad y construimos la expresión
      como  lhs-(rhs)  respetando la estructura original de ambos lados.
    """
    if MODO_EXAMEN:
        return "Error: No disp"
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
            nums = extraer_numeros(cmd, "MAT2")
            if len(nums) != 6:
                return "Use MAT2(", "a1,b1,c1,a2,b2,c2)", ""
            sol = resolver_sistema_2x2(nums)
            if sol is None:
                return "Sistema sin", "solucion unica", ""
            x, y = (round(v, 10) for v in sol)
            return f"X = {x:.5f}", f"Y = {y:.5f}", ""

        if "MAT3" in cmd:
            nums = extraer_numeros(cmd, "MAT3")
            if len(nums) != 12:
                return "Use MAT3(12 val.)", "a1,b1,c1,d1,...,d3", ""
            sol = resolver_sistema_3x3(nums)
            if sol is None:
                return "Sistema sin", "solucion unica", ""
            x, y, z = (round(v, 10) for v in sol)
            return f"X={x:.4f} Y={y:.4f}", f"Z = {z:.4f}", ""

        if "DOT" in cmd:
            nums = extraer_numeros(cmd, "DOT")
            if len(nums) != 6:
                return "Use DOT(", "ax,ay,az,bx,by,bz)", ""
            a, b = nums[0:3], nums[3:6]
            punto = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
            return f"A . B = {punto:.5f}", "", ""

        if "CROSS" in cmd:
            nums = extraer_numeros(cmd, "CROSS")
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


# ==========================================================
# 8. CALCULO DIFERENCIAL E INTEGRAL NUMERICO
# ==========================================================
def calcular_derivada(eq, punto_str):
    if MODO_EXAMEN:
        return "Error: No disp"
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
        return "Error: No disp"
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


# ==========================================================
# 9. ESTADISTICA BASADA EN LISTAS (STAT)
# ==========================================================
def procesar_estadistica(comando):
    """Maneja el ingreso de datos en lista y los calculos STATCALC.

    NUEVO 4 (v5.0): comando "X<x>,<y>" agrega un par (x,y) a dos listas
    paralelas (ESTADISTICA_LISTA / ESTADISTICA_LISTA_Y) para regresion
    lineal. Si hay datos pareados, CALC ademas devuelve la pendiente
    "a" y ordenada "b" de y=a+bx, y el coeficiente de correlacion "r".
    "CLEAR" limpia ambas listas (1-variable y pareada)."""
    global ESTADISTICA_LISTA, ESTADISTICA_LISTA_Y
    try:
        # NUEVO 4 (v5.0): datos pareados "X<x>,<y>" -> regresion lineal
        if comando.startswith("X") or comando.startswith(":X"):
            if len(ESTADISTICA_LISTA) >= LIMITE_ESTADISTICA:
                return f"Lista llena (max {LIMITE_ESTADISTICA})", "", ""
            cuerpo = comando.lstrip(":").lstrip("X")
            partes = cuerpo.split(",")
            if len(partes) < 2:
                return "Error: use STATX<x>,<y>", "", ""
            x_val = float(partes[0])
            y_val = float(partes[1])
            ESTADISTICA_LISTA.append(x_val)
            ESTADISTICA_LISTA_Y.append(y_val)
            return (f"N = {len(ESTADISTICA_LISTA)}",
                    f"Par: ({x_val}, {y_val})", "")

        if comando.startswith("ADD:") or "ADD:" in comando:
            if len(ESTADISTICA_LISTA) >= LIMITE_ESTADISTICA:
                return f"Lista llena (max {LIMITE_ESTADISTICA})", "", ""
            val = float(comando.split(":")[-1])
            ESTADISTICA_LISTA.append(val)
            return f"N = {len(ESTADISTICA_LISTA)}", f"Ultimo: {val}", ""

        if "CLEAR" in comando:
            ESTADISTICA_LISTA = []
            ESTADISTICA_LISTA_Y = []
            return "Lista limpia", "N = 0", ""

        if "CALC" in comando:
            if not ESTADISTICA_LISTA:
                return "Lista vacia", "", ""
            n = len(ESTADISTICA_LISTA)
            media = sum(ESTADISTICA_LISTA) / n
            varianza = sum((v - media) ** 2 for v in ESTADISTICA_LISTA) / n
            desviacion = varianza ** 0.5
            l1 = f"N = {n}  Media={media:.4f}"
            l2 = f"Var(s2) = {varianza:.4f}"
            l3 = f"StdDev(s) = {desviacion:.4f}"

            # NUEVO 4 (v5.0): si hay datos pareados (x,y), calcular
            # regresion lineal y=a+bx por minimos cuadrados, y el
            # coeficiente de correlacion de Pearson "r". Reemplaza l3
            # (StdDev) por la pendiente/ordenada y agrega r en su lugar
            # -- la fx-991 tambien prioriza la regresion sobre StdDev
            # cuando hay datos pareados en modo Reg-Lineal.
            if len(ESTADISTICA_LISTA_Y) == n and n >= 2:
                xs, ys = ESTADISTICA_LISTA, ESTADISTICA_LISTA_Y
                media_y = sum(ys) / n
                sxx = sum((x - media) ** 2 for x in xs)
                syy = sum((y - media_y) ** 2 for y in ys)
                sxy = sum((x - media) * (y - media_y) for x, y in zip(xs, ys))
                if sxx == 0:
                    return l1, l2, "Error: x constante"
                b = sxy / sxx          # pendiente
                a = media_y - b * media  # ordenada al origen
                if sxx == 0 or syy == 0:
                    r = 0.0
                else:
                    r = sxy / (sxx ** 0.5 * syy ** 0.5)
                l2 = f"a={decimal_a_fraccion(a)}  b={decimal_a_fraccion(b)}"
                l3 = f"r = {r:.4f}"

            return l1, l2, l3
    except Exception:
        pass
    return "Error Estad.", "", ""


# ==========================================================
# 10. MEMORIA: STO / RCL / ANS
# ==========================================================
def comando_sto(cmd):
    """'<expr>STOA' guarda el valor de <expr> (o de ANS si esta vacio) en A."""
    global ANS
    partes = cmd.split("STO")
    expr_part = partes[0].strip()
    resto = partes[1].strip() if len(partes) > 1 else ""
    var = resto[0:1]
    if var not in MEMORIA:
        return "Error: use STO A/B/C/X/Y"
    try:
        valor = ANS if expr_part == "" else evaluar_expresion(expr_part, variables_actuales())
        MEMORIA[var] = valor
        ANS = valor
        return f"{var} = {decimal_a_fraccion(valor)}"
    except Exception:
        return "Error Sintaxis"


def comando_rcl(cmd):
    """'RCLA' recupera el valor guardado en A y lo deja como resultado/ANS."""
    global ANS
    partes = cmd.split("RCL")
    resto = partes[1].strip() if len(partes) > 1 else ""
    var = resto[0:1]
    if var not in MEMORIA:
        return "Error: use RCL A/B/C/X/Y"
    ANS = MEMORIA[var]
    return f"{var} = {decimal_a_fraccion(MEMORIA[var])}"




# ==========================================================
# 10v4.5-A. PERSISTENCIA EN FLASH (NUEVO 1 - v4.5)
# ==========================================================
# Archivo de estado: /picalc_state.json en la Pico (raiz de la
# flash), o ./picalc_state.json en PC para desarrollo.
# Formato JSON: { "memoria": {...}, "ans": 0.0, "modo_calc": 1,
#                 "modo_complejo": false, "matrices": {...} }
# Los valores complex se serializan como [real, imag] y se
# reconstruyen al cargar (comportamiento intencional, ver NUEVO 2).
_RUTA_ESTADO = "/picalc_state.json" if True else "./picalc_state.json"
# En la Pico SIEMPRE es /picalc_state.json. En PC se puede
# cambiar a "./" manualmente para desarrollo local.

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
    """Guarda MEMORIA, ANS, modos y matrices en flash/disco.
    Llamar con el token SAVE (capa 2ND del teclado) o al apagar."""
    try:
        estado = {
            "memoria": {k: _serializar_valor(v) for k, v in MEMORIA.items()},
            "ans": _serializar_valor(ANS),
            "modo_calc": MODO_CALC,
            "modo_complejo": MODO_COMPLEJO,
            "matrices": {
                nombre: {
                    "data": [_serializar_valor(x) for x in m["data"]],
                    "filas": m["filas"],
                    "cols": m["cols"],
                } if m is not None else None
                for nombre, m in MATRICES.items()
            },
        }
        with open(_RUTA_ESTADO, "w") as f:
            _json_mod.dump(estado, f)
        return "Estado guardado"
    except Exception as ex:
        return f"Error save: {ex}"


def cargar_estado():
    """Carga el estado guardado previamente. Se llama al arrancar."""
    global ANS, MODO_CALC, MODO_COMPLEJO
    try:
        with open(_RUTA_ESTADO, "r") as f:
            estado = _json_mod.load(f)
        for k, v in estado.get("memoria", {}).items():
            if k in MEMORIA:
                MEMORIA[k] = _deserializar_valor(v)
        ANS = _deserializar_valor(estado.get("ans", 0.0))
        MODO_CALC = int(estado.get("modo_calc", 1))
        MODO_COMPLEJO = bool(estado.get("modo_complejo", False))
        for nombre, m in estado.get("matrices", {}).items():
            if nombre in MATRICES and m is not None:
                MATRICES[nombre] = {
                    "data": [_deserializar_valor(x) for x in m["data"]],
                    "filas": m["filas"],
                    "cols": m["cols"],
                }
        return True
    except OSError:
        return False  # archivo no existe todavia (primer arranque)
    except Exception:
        return False


# ==========================================================
# 10v4.5-B. SETUP (FIX 4 - v4.5, completado en v5.0)
# ==========================================================
# En v4.3 la tecla SETUP del layout fisico se definia pero nunca
# se procesaba: el token pasaba al buffer y se evaluaba como
# expresion desconocida. v4.5 agrego cmd_setup() con DEG/RAD;
# v5.0 completa FIX/SCI/NORM (NUEVO 3) y conecta MODO_ANGULOS al
# motor matematico (FIX 0, ver evaluar_rpn).
MODO_ANGULOS = "DEG"  # "DEG" o "RAD" — usado por el motor trig

# NUEVO 3 (v5.0): formato de presentacion numerica.
#  - "NORM": comportamiento v4.x (entero limpio, fraccion continua si
#            es exacta, sino 5 decimales). Por defecto.
#  - "FIX":  siempre N decimales fijos (FORMATO_DECIMALES, 0-9), sin
#            intentar fracciones. Ej: FIX 2 -> "3.14".
#  - "SCI":  notacion cientifica con FORMATO_DECIMALES cifras
#            significativas tras la coma. Ej: "3.14e+00".
FORMATO_NUM = "NORM"
FORMATO_DECIMALES = 4  # 0-9, usado por FIX y SCI


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
        try:
            n = int(resto[0]) if resto and resto[0].isdigit() else FORMATO_DECIMALES
        except (ValueError, IndexError):
            n = FORMATO_DECIMALES
        n = max(0, min(9, n))
        FORMATO_NUM = "FIX"
        FORMATO_DECIMALES = n
        return f"Formato: FIX {n}", f"{n} decimales fijos", ""

    # NUEVO 3 (v5.0): SETUPSCI -- notacion cientifica
    if "SCI" in cmd_u:
        resto = cmd_u.split("SCI")[-1].strip()
        try:
            n = int(resto[0]) if resto and resto[0].isdigit() else FORMATO_DECIMALES
        except (ValueError, IndexError):
            n = FORMATO_DECIMALES
        n = max(0, min(9, n))
        FORMATO_NUM = "SCI"
        FORMATO_DECIMALES = n
        return f"Formato: SCI {n}", "Notacion cientif.", ""

    # NUEVO 3 (v5.0): SETUPNORM -- vuelve al formato automatico v4.x
    if "NORM" in cmd_u:
        FORMATO_NUM = "NORM"
        return "Formato: NORM", "Fraccion/5 dec.", ""

    # Sin argumento: mostrar estado del sistema
    mats_def = sum(1 for m in MATRICES.values() if m is not None)
    fmt_txt = FORMATO_NUM if FORMATO_NUM == "NORM" else f"{FORMATO_NUM}{FORMATO_DECIMALES}"
    return (f"Ang:{MODO_ANGULOS} Fmt:{fmt_txt}",
            f"Cmplx:{'SI' if MODO_COMPLEJO else 'NO'} Mat:{mats_def}/3",
            f"TABLE max:{TABLA_MAX_FILAS} Den<{FRACCION_DEN_MAX}")



# ==========================================================
# 10v4.5-C. TEST SUITE INTEGRADA (NUEVO 3 - v4.5)
# ==========================================================
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
        evaluar_expresion("SQRT(-1)", variables_actuales())
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
    check("fraccion 1/3", decimal_a_fraccion(1/3), "1/3")
    check("fraccion 2/3", decimal_a_fraccion(2/3), "2/3")
    check("entero 14", decimal_a_fraccion(14.0), "14")

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
    check("5! = 120", decimal_a_fraccion(calcular_factorial(5)), "120")
    check("0! = 1", decimal_a_fraccion(calcular_factorial(0)), "1")
    check("NPR(5,2) = 20", decimal_a_fraccion(calcular_npr(5, 2)), "20")
    check("NCR(5,2) = 10", decimal_a_fraccion(calcular_ncr(5, 2)), "10")
    check("NCR(170,2) sin overflow", decimal_a_fraccion(calcular_ncr(170, 2)), "14365")
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
    check("123456 en SCI3 = 1.235e+05", r, "1.235e+05")
    cmd_setup("SETUPNORM")
    r, *_ = procesar_todo("1/3")
    check("1/3 en NORM = 1/3", r, "1/3")
    globals()["FORMATO_NUM"] = prev_fmt
    globals()["FORMATO_DECIMALES"] = prev_dec

    # --- NUEVO 4 (v5.0): STAT regresion lineal y=2x+1 ---
    prev_x = list(globals()["ESTADISTICA_LISTA"])
    prev_y = list(globals()["ESTADISTICA_LISTA_Y"])
    procesar_estadistica("CLEAR")
    for x, y in [(1, 3), (2, 5), (3, 7), (4, 9)]:
        procesar_estadistica(f"X{x},{y}")
    l1, l2, l3 = procesar_estadistica("CALC")
    check("STAT regresion y=2x+1 -> a=1 b=2", l2, "a=1  b=2")
    check("STAT regresion y=2x+1 -> r=1", l3, "r = 1.0000")
    procesar_estadistica("CLEAR")
    globals()["ESTADISTICA_LISTA"] = prev_x
    globals()["ESTADISTICA_LISTA_Y"] = prev_y

    total = pasados + fallados
    print(f"\n=== TEST SUITE PiCalc v5.0 ===")
    for l in log:
        print(l)
    print(f"\nResultado: {pasados}/{total} pasados")
    return (f"Tests: {pasados}/{total}",
            "OK" if fallados == 0 else f"{fallados} fallaron",
            "Ver consola" if not ENTORNO_PICO else "")


# ==========================================================
# 11v4-A. MODULO CMPLX: NUMEROS COMPLEJOS
# ==========================================================
def toggle_cmplx():
    """Activa/desactiva el modo numeros complejos."""
    global MODO_COMPLEJO
    MODO_COMPLEJO = not MODO_COMPLEJO
    return f"Modo CMPLX: {'ON' if MODO_COMPLEJO else 'OFF'}"


# ==========================================================
# 11v4-B. MODULO MAT: MATRICES INDEPENDIENTES (hasta 4x4)
# ==========================================================
def _fmt_mat(m, filas, cols):
    """Formatea una matriz plana para la pantalla OLED (multi-linea)."""
    lineas = []
    for f in range(filas):
        fila = [f"{m[f * cols + c]:.3f}" for c in range(cols)]
        lineas.append(" ".join(fila))
    return lineas


def cmd_matdef(cmd):
    """MATDEF<nombre>,<filas>,<cols>,<v1>,<v2>,...
    Guarda la matriz en MATRICES['nombre'].
    Ejemplo: MATDEFA,2,2,1,2,3,4  ->  MatA = [[1,2],[3,4]]"""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        resto = cmd.split("MATDEF", 1)[-1].strip()
        partes = resto.split(",")
        nombre = partes[0].upper()
        if nombre not in MATRICES:
            return "Nombre: A B C", "", ""
        filas, cols = int(partes[1]), int(partes[2])
        if filas > 4 or cols > 4:
            return "Max 4x4", "", ""
        vals = [evaluar_expresion(v, variables_actuales()) for v in partes[3:]]
        if len(vals) != filas * cols:
            return "Num valores!=", f"{filas}x{cols}", ""
        MATRICES[nombre] = {"data": vals, "filas": filas, "cols": cols}
        lineas = _fmt_mat(vals, filas, cols)
        return f"Mat{nombre} OK {filas}x{cols}", lineas[0] if lineas else "", lineas[1] if len(lineas) > 1 else ""
    except Exception as ex:
        return f"Error Mat: {ex}", "", ""


def _get_mat(nombre):
    m = MATRICES.get(nombre)
    if m is None:
        raise ValueError(f"Mat{nombre} no definida")
    return m


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
            return f"det = {decimal_a_fraccion(det2(d))}", "", ""
        if m["filas"] == 3 and m["cols"] == 3:
            return f"det = {decimal_a_fraccion(det3(d))}", "", ""
        return "Solo 2x2 o 3x3", "", ""
    except Exception as ex:
        return f"Error: {ex}", "", ""


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
    except Exception as ex:
        return f"Error: {ex}", "", ""


# ==========================================================
# 11v4-C. MODULO EQN: ECUACIONES CUADRATICAS Y CUBICAS
# ==========================================================
def _fmt_raiz(v):
    """Formatea una raiz real o compleja de forma compacta."""
    if isinstance(v, complex):
        return decimal_a_fraccion(v)
    v = round(v, 8)
    return str(int(v)) if v == int(v) else f"{v:.5f}"


def cmd_cuad(cmd):
    """CUAD(a,b,c) -> resuelve ax^2 + bx + c = 0 (formula cuadratica).
    Devuelve X1 y X2; si MODO_COMPLEJO=True acepta discriminante negativo."""
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        partes = cmd.split("CUAD", 1)[-1].strip().strip("()")
        p = [evaluar_expresion(v.strip(), variables_actuales()) for v in partes.split(",")]
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
        p = [evaluar_expresion(v.strip(), variables_actuales()) for v in partes.split(",")]
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
    except Exception as ex:
        return f"Error: {ex}", "", ""


# ==========================================================
# 11v4-D. MODULO TABLE: TABULACION DE FUNCIONES
# ==========================================================
def cmd_table(cmd):
    """TABLE<expr>,<inicio>,<fin>,<paso>
    Genera la tabla f(x) para x en [inicio, fin] con paso dado.
    FIX 5 (v4.4): x se calcula como inicio + i*paso en cada iteracion
    para eliminar la acumulacion de error de punto flotante que ocurre
    cuando se suma paso repetidamente.
    FIX 9 (v4.4): el limite usa TABLA_MAX_FILAS (constante independiente
    de LIMITE_ESTADISTICA) para que ambas no se interfieran."""
    global TABLA_RESULTADO
    if MODO_EXAMEN:
        return "Error: No disp", "", ""
    try:
        resto = cmd.split("TABLE", 1)[-1].strip()
        partes = resto.split(",")
        eq_u = partes[0].upper()
        inicio = evaluar_expresion(partes[1], variables_actuales())
        fin    = evaluar_expresion(partes[2], variables_actuales())
        paso   = evaluar_expresion(partes[3], variables_actuales())

        if paso == 0:
            return "Error: paso=0", "", ""

        pasos_estimados = int(abs(fin - inicio) / abs(paso)) + 1
        if pasos_estimados > TABLA_MAX_FILAS:
            return "Error: Rango Max", f"max {TABLA_MAX_FILAS} filas", f"({pasos_estimados} pedidos)"

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

        x0, fx0 = TABLA_RESULTADO[0]
        return (f"TABLE ({len(TABLA_RESULTADO)} pts)",
                f"x={x0} f={decimal_a_fraccion(fx0)}",
                "DEL=ver sig." if len(TABLA_RESULTADO) > 1 else "")
    except Exception as ex:
        return f"Error Table: {ex}", "", ""


# ==========================================================
# 11v4-E. MODULO BASEN: CONVERSION DE BASE Y LOGICA DE BITS
# ==========================================================
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


# ==========================================================
# 11. CAPA DE ENTRADA: TOKENS Y MULTIPLICACION IMPLICITA
# ==========================================================
# Atajos de teclado/consola -> token real inyectado en ENTRADA_TOKENS.
# Las funciones matematicas que entran al motor RPN llevan "(" incluido
# (el "(" se procesa como token aparte por el motor). Los comandos
# especiales (SOLVE, DERIV, INT, STAT, STO, RCL, etc.) se escriben sin
# "(": su parseo es por split() de texto, no por el motor RPN.
# FIX 7 (v4.4): ALIAS_TOKENS se genera automaticamente desde FUNC_MAP
# para evitar duplicar la lista de funciones matematicas. Las entradas
# especiales que no estan en FUNC_MAP se agregan aparte.
ALIAS_TOKENS = {nombre: nombre + "(" for nombre in FUNC_MAP}
# Comandos especiales de teclado fisico / 2ND que no estan en FUNC_MAP:
ALIAS_TOKENS.update({
    "MAT2": "MAT2(", "MAT3": "MAT3(", "DOT": "DOT(", "CROSS": "CROSS(",
    "POL": "POL(", "REC": "REC(",
    "CUAD": "CUAD(", "CUB": "CUB(",
    "BIN": "BIN(", "OCT": "OCT(", "HEX": "HEX(",
    "NPR": "NPR(", "NCR": "NCR(",  # NUEVO 1 (v5.0): permutaciones/combinaciones
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



# ==========================================================
# 11b. MENU MODE (v4.3) - Identico al de la Casio fx-991 CW
# ==========================================================
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
    de confirmacion al estilo Casio (ej: 'COMP Mode')."""
    global MODO_CALC, MODO_COMPLEJO, EN_MENU_MODE
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
    return f"{nombre} Mode"


# ==========================================================
# 12. PROCESADOR DE COMANDOS GENERAL
# ==========================================================
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
        if "STAT" in cmd:
            return procesar_estadistica(cmd.split("STAT")[-1])

        # ---- ALGEBRA Y CALCULO ----
        if "SOLVE" in cmd:
            return resolver_ecuacion_lineal(cmd.split("SOLVE")[-1]), "", ""
        if "MAT2" in cmd or "MAT3" in cmd or "DOT" in cmd or "CROSS" in cmd:
            return resolver_sistema_matrices(cmd)
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
        if "CUB" in cmd and "COSH" not in cmd and "CROSS" not in cmd:
            return cmd_cub(cmd)
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

        # ---- CONVERSIONES POLARES / RECTANGULARES ----
        if "POL" in cmd:  # POL(r, deg) -> X, Y
            nums = extraer_numeros(cmd, "POL")
            r, rad = nums[0], math.radians(nums[1])
            return f"X = {r * math.cos(rad):.4f}", f"Y = {r * math.sin(rad):.4f}", ""
        if "REC" in cmd:  # REC(x, y) -> R, ANG
            nums = extraer_numeros(cmd, "REC")
            x, y = nums[0], nums[1]
            return f"R = {math.hypot(x, y):.4f}", f"ANG = {math.degrees(math.atan2(y, x)):.2f}", ""

        # ---- ALEATORIO Y RAIZ ANALITICA ----
        if "RAND" in cmd:
            return f"Rand: {time.time() % 1:.5f}", "", ""
        if "RAIZ" in cmd:
            return calcular_raiz_analitica(cmd.split("RAIZ")[-1]), "", ""

        # ---- v4.5: PERSISTENCIA, SETUP, TESTS ----
        if cmd == "SAVE":
            return guardar_estado(), "", ""
        if cmd.startswith("SETUP"):
            return cmd_setup(cmd)
        if cmd == "TEST":
            return run_tests()

        # ---- EVALUACION GENERAL (Shunting-yard + RPN, sin eval) ----
        # Soporta: +,-,*,/,^,%, parentesis, funciones trig/hiperbolicas
        # (DEG por defecto), LN/LOG/EXP/SQRT/ABS, PI/E, variables A-Y/ANS.
        res_num = evaluar_expresion(cmd, variables_actuales())
        ANS = res_num
        return decimal_a_fraccion(res_num), "", ""
    except (ValueError, ZeroDivisionError) as e:
        # FIX 6 (v4.4): mostrar el mensaje real del error al usuario.
        # "Division por cero", "Token desconocido: X", "Numero invalido: 1.2.3", etc.
        msg = str(e)
        return msg[:16] if len(msg) > 16 else msg, "", ""
    except Exception as e:
        # Error inesperado (bug real): mostrar tipo para facilitar debugging
        return f"Err:{type(e).__name__}", "", ""


# ==========================================================
# 13. BUCLE DE EJECUCION (PC / PICO)  -  v4.3
# ==========================================================
INSTRUCCIONES = (
    "PiCalc OS v5.0 - Cada linea = un TOKEN (un boton).\n"
    "Numeros/operadores: 0-9 . + - * / ^ % ( ) , =\n"
    "Funciones: SIN COS TAN ASIN ACOS ATAN SINH COSH TANH LN LOG EXP SQRT RAIZ ABS\n"
    "Combinatoria: FACT(n)=n!  NPR(n,r)  NCR(n,r)\n"
    "Complejo: CMPLX (toggle) | I=unidad imag. | CONJ(z) ARG(z)\n"
    "Memoria: A B C X Y ANS  |  Comandos: STO RCL\n"
    "Calculo: SOLVE DERIV<f>,<x>  INT<f>,<a>,<b>  MCD MCM RAND PRIMOS\n"
    "Matrices (sistemas): MAT2 MAT3 DOT CROSS\n"
    "Matrices (algebra): MATDEF<n>,<f>,<c>,vals  MATADD MATMUL MATTRANS MATDET MATINV\n"
    "Polinomios: CUAD(a,b,c)  CUB(a,b,c,d)\n"
    "Tabla: TABLE<expr>,<ini>,<fin>,<paso>\n"
    "Base-N: BIN(n) OCT(n) HEX(n) AND(a,b) OR(a,b) XOR(a,b) NOT(n)\n"
    "Estadistica: STATADD:<v> | STATX<x>,<y> (regresion) | STATCALC | STATCLEAR\n"
    "SETUP: SETUPDEG/RAD  SETUPFIX<n>  SETUPSCI  SETUPNORM\n"
    "Control: AC DEL IGUAL BYPASS=modo examen\n"
    "Cursor: IZQ DER  |  Menu modos: MODE  (luego digita 1-8)"
)


def _pos_caracter_cursor(tokens, cursor_pos):
    """Convierte CURSOR_POS (indice de token) en indice de caracter
    dentro del string 'join(tokens)', para que el cursor visual '|'
    aparezca en el lugar correcto."""
    return sum(len(t) for t in tokens[:cursor_pos])


def iniciar():
    global MODO_EXAMEN, ENTRADA_TOKENS, CURSOR_POS, EN_MENU_MODE, _SELECCION_MENU

    # NUEVO 1 (v4.5): cargar estado guardado en flash al arrancar.
    # En primer arranque el archivo no existe y cargar_estado devuelve False.
    estado_cargado = cargar_estado()

    renderizar_pantalla("PiCalc OS v5.0", f"Modo Examen: {MODO_EXAMEN}",
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

        # ==================================================
        # BLOQUE MENU MODE (v4.3)
        # El menu MODE captura los tokens mientras esta abierto.
        # Solo acepta: digitos 1-8 (seleccionar modo),
        #              IZQ/DER (navegar opciones en Pico),
        #              AC (cerrar sin cambiar modo).
        # ==================================================
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
                renderizar_pantalla(msg, f"Modo: {MODO_CALC_NOMBRES[MODO_CALC]}")
            elif accion_u.isdigit() and 1 <= int(accion_u) <= 8:
                num = int(accion_u)
                _SELECCION_MENU = num
                msg = aplicar_modo(num)
                renderizar_pantalla(msg, f"Modo: {MODO_CALC_NOMBRES[MODO_CALC]}")
            else:
                renderizar_menu_mode(_SELECCION_MENU)
            continue

        # ==================================================
        # TECLAS DE CONTROL PRINCIPALES
        # ==================================================

        # ---- BYPASS: toggle modo examen ----
        if accion_u == "BYPASS":
            MODO_EXAMEN = not MODO_EXAMEN
            expr_actual = "".join(ENTRADA_TOKENS) or "0"
            cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
            renderizar_pantalla(expr_actual, f"Modo Examen: {MODO_EXAMEN}",
                                cursor_pos=cur_ch)
            continue

        # ---- MODE: abrir menu de modos (v4.3) ----
        if accion_u == "MODE":
            EN_MENU_MODE = True
            renderizar_menu_mode()
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

        # ---- IZQ: mover cursor a la izquierda (v4.3) ----
        if accion_u == "IZQ":
            if CURSOR_POS > 0:
                CURSOR_POS -= 1
            expr_actual = "".join(ENTRADA_TOKENS) or "0"
            cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
            renderizar_pantalla(expr_actual, cursor_pos=cur_ch)
            continue

        # ---- DER: mover cursor a la derecha (v4.3) ----
        if accion_u == "DER":
            if CURSOR_POS < len(ENTRADA_TOKENS):
                CURSOR_POS += 1
            expr_actual = "".join(ENTRADA_TOKENS) or "0"
            cur_ch = _pos_caracter_cursor(ENTRADA_TOKENS, CURSOR_POS)
            renderizar_pantalla(expr_actual, cursor_pos=cur_ch)
            continue

        # ---- IGUAL: calcular ----
        if accion_u == "IGUAL":
            if ENTRADA_TOKENS:
                expr = construir_expresion(ENTRADA_TOKENS)
                texto_anterior = "".join(ENTRADA_TOKENS)
                l1, l2, l3 = procesar_todo(expr)
                # Mostrar resultado SIN cursor (igual que la Casio fisica
                # al mostrar el resultado: el cursor desaparece hasta que
                # el usuario empiece a escribir de nuevo).
                renderizar_pantalla(texto_anterior, l1, l2, l3)
                # FIX v3.2: solo limpiamos si no hubo error.
                if l1 != "Error Sintaxis":
                    ENTRADA_TOKENS = []
                    CURSOR_POS = 0
            continue

        # ==================================================
        # INSERTAR TOKEN EN LA POSICION DEL CURSOR (v4.3)
        # ==================================================
        # FIX v3.2: en la Pico, escanear_teclado() devuelve tokens ya formateados
        # (ej: "SIN(", "MAT2(") que NO son puramente .isalpha(). Para que PC y Pico
        # tengan comportamiento identico, intentamos el alias primero sobre la parte
        # alfabetica base, y si no hay alias, usamos el token tal como llego.
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

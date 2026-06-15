import time
import math
import cmath  # numeros complejos (disponible en MicroPython)

# ==========================================================
# PiCalc OS v4.1  –  Changelog desde v4.0
# ----------------------------------------------------------
# FIX 1 (TABLE): limite de 45 filas maximas (igual que Casio
#   fx-991). El chequeo ocurre ANTES de iterar con un calculo
#   previo de pasos_estimados, evitando que un rango amplio o
#   paso chico congele la OLED o desborde la RAM del RP2040.
#
# FIX 2 (CMPLX display): decimal_a_fraccion() reescrita para
#   formatear complejos al estilo Casio: "2+3i", "-i", "4-2i"
#   sin parentesis de Python ni el sufijo "j". Maneja correctamente
#   parte real=0, im=0, magnitud=1 (+i/-i) y decimales.
#
# FIX 3 (MATMUL): validacion explicita de dimensiones ANTES del
#   bucle (cols(A) == filas(B)). Antes un mismatch lanzaba
#   IndexError interno; ahora devuelve "Error Dimension" con
#   los valores exactos para que el usuario sepa que corregir.
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
ENTRADA_TOKENS = []
LIMITE_ESTADISTICA = 50  # cuida la RAM de la Pico

# ---- Estado v4.0 ----
MODO_COMPLEJO = False   # False=real, True=CMPLX (raices negativas devuelven complex)
MATRICES = {            # almacenamiento persistente de matrices (hasta 4x4)
    "A": None,
    "B": None,
    "C": None,
}
TABLA_RESULTADO = []    # cache de la ultima TABLE generada para scroll futuro

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
LAYOUT_TECLADO = [
    ["7", "8", "9", "(", ")", "DEL", "AC", "2ND"],
    ["4", "5", "6", "*", "/", "^", "%", "STO"],
    ["1", "2", "3", "+", "-", ",", "ANS", "RCL"],
    ["0", ".", "X", "PI", "E", "SIN(", "COS(", "TAN("],
    ["A", "B", "C", "Y", "=", "IGUAL", "BYPASS", "SQRT("],
    ["LN(", "LOG(", "EXP(", "ABS(", "ASIN(", "ACOS(", "ATAN(", "RAIZ("],
]

# Capa secundaria (tecla 2ND/SHIFT): funciones avanzadas poco usadas.
LAYOUT_TECLADO_2ND = [
    ["SOLVE", "DERIV", "INT", "STAT", "MAT2(", "MAT3(", "DOT(", "CROSS("],
    ["POL(", "REC(", "PRIMOS", "MCD", "MCM", "RAND", "SINH(", "COSH("],
    ["TANH(", "CMPLX", "CUAD(", "CUB(", "TABLE", "BIN(", "OCT(", "HEX("],
    ["MATDEF", "MATADD", "MATMUL", "MATTRANS", "MATDET", "MATINV", "", ""],
    ["", "", "", "", "", "", "", ""],
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
                    token = capa[i][j]
                    if token == "2ND":
                        MODO_2ND = not MODO_2ND
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
def renderizar_pantalla(linea_eq, l2="", l3="", l4=""):
    """Renderiza hasta 4 lineas para OLED 128x64 o consola PC.
    La linea 1 (ecuacion) hace SCROLL HORIZONTAL: si supera el ancho,
    muestra siempre el extremo DERECHO (donde esta el cursor)."""
    ANCHO_OLED = 16
    vista_eq_oled = linea_eq[-ANCHO_OLED:] if len(linea_eq) > ANCHO_OLED else linea_eq

    if ENTORNO_PICO and display:
        display.fill(0)
        display.text(vista_eq_oled, 0, 2, 1)
        display.text(l2[:ANCHO_OLED], 0, 18, 1)
        display.text(l3[:ANCHO_OLED], 0, 34, 1)
        display.text(l4[:ANCHO_OLED], 0, 50, 1)
        display.show()
    else:
        ANCHO_CONSOLA = 28
        vista_eq_consola = linea_eq[-ANCHO_CONSOLA:] if len(linea_eq) > ANCHO_CONSOLA else linea_eq
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
# NOTA / LIMITACION CONOCIDA:
#   La precedencia del menos unario (NEG) se fijo por ENCIMA de "^" para
#   que "2^-2" se resuelva como 2^(-2) = 0.25 (caso muy frecuente en
#   exponentes negativos / notacion cientifica). Como contrapartida,
#   "-2^2" se evalua como (-2)^2 = 4 en vez de -(2^2) = -4. Si se
#   necesita ese caso, debe escribirse explicitamente "-(2^2)".

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
}

CONSTANTES = {"PI": math.pi, "E": math.e, "I": 1j}  # I = unidad imaginaria

PRECEDENCIA = {"+": 2, "-": 2, "*": 3, "/": 3, "%": 3, "^": 5, "NEG": 6}
ASOC_DERECHA = ("^", "NEG")


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
            while j < n and (expr[j].isdigit() or expr[j] == "."):
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
                # Menos unario -> token especial NEG
                while pila and pila[-1][0] == "OP" and pila[-1][1] != "(" and _debe_pop(pila[-1][1], "NEG"):
                    salida.append(pila.pop())
                pila.append(("OP", "NEG"))
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
            if MODO_COMPLEJO and val in FUNC_MAP_CMPLX:
                fn = FUNC_MAP_CMPLX[val]
                # grados -> radianes para trig en modo complejo
                if FUNC_MAP[val][1] == "deg_in":
                    arg = cmath.pi * arg / 180
                resultado = fn(arg)
                if FUNC_MAP[val][1] == "deg_out":
                    resultado = cmath.phase(resultado) * 180 / cmath.pi
            else:
                fn, modo = FUNC_MAP[val]
                if modo == "deg_in":
                    arg = math.radians(arg)
                resultado = fn(arg)
                if modo == "deg_out":
                    resultado = math.degrees(resultado)
            pila.append(resultado)
        elif tipo == "OP":
            if val == "NEG":
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

    if MODO_EXAMEN:
        return f"{val:.5f}"
    try:
        val = round(val, 10)
        if isinstance(val, int) or val.is_integer():
            return str(int(val))
        d_base = 100000
        n_base = int(round(val * d_base))
        a, b = abs(n_base), abs(d_base)
        while b:
            a, b = b, a % b
        num, den = int(n_base / a), int(d_base / a)
        return f"{num}/{den}" if den < 1000 else f"{val:.5f}"
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
    """Maneja el ingreso de datos en lista y los calculos STATCALC."""
    global ESTADISTICA_LISTA
    try:
        if comando.startswith("ADD:") or "ADD:" in comando:
            if len(ESTADISTICA_LISTA) >= LIMITE_ESTADISTICA:
                return f"Lista llena (max {LIMITE_ESTADISTICA})", "", ""
            val = float(comando.split(":")[-1])
            ESTADISTICA_LISTA.append(val)
            return f"N = {len(ESTADISTICA_LISTA)}", f"Ultimo: {val}", ""

        if "CLEAR" in comando:
            ESTADISTICA_LISTA = []
            return "Lista limpia", "N = 0", ""

        if "CALC" in comando:
            if not ESTADISTICA_LISTA:
                return "Lista vacia", "", ""
            n = len(ESTADISTICA_LISTA)
            media = sum(ESTADISTICA_LISTA) / n
            varianza = sum((v - media) ** 2 for v in ESTADISTICA_LISTA) / n
            desviacion = varianza ** 0.5
            return (f"N = {n}  Media={media:.4f}",
                    f"Var(s2) = {varianza:.4f}",
                    f"StdDev(s) = {desviacion:.4f}")
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
    Limite: 45 filas maximas (igual que Casio fx-991) para no
    congelar la OLED ni desbordar la RAM del RP2040.
    En consola PC muestra la primera fila; el cache TABLA_RESULTADO
    contiene todos los pares (x, f(x)) para scroll posterior."""
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

        # Chequeo previo antes de iterar: protege RAM y OLED
        pasos_estimados = int(abs(fin - inicio) / abs(paso)) + 1
        if pasos_estimados > 45:
            return "Error: Rango Max", f"max 45 filas", f"({pasos_estimados} pedidos)"

        TABLA_RESULTADO = []
        x = inicio
        while (paso > 0 and x <= fin + 1e-9) or (paso < 0 and x >= fin - 1e-9):
            fx = evaluar_expresion(eq_u, variables_actuales({"X": x}))
            TABLA_RESULTADO.append((round(x, 6), round(fx, 6) if not isinstance(fx, complex) else fx))
            x += paso
            x = round(x, 10)  # evita acumulacion de error flotante

        if not TABLA_RESULTADO:
            return "Tabla vacia", "", ""

        # Mostrar primera fila en OLED; resto queda en cache
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
    """Evalua una expresion y la convierte a int (truncando)."""
    return int(evaluar_expresion(expr.strip(), variables_actuales()))


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
ALIAS_TOKENS = {
    "SIN": "SIN(", "COS": "COS(", "TAN": "TAN(",
    "ASIN": "ASIN(", "ACOS": "ACOS(", "ATAN": "ATAN(",
    "SINH": "SINH(", "COSH": "COSH(", "TANH": "TANH(",
    "LN": "LN(", "LOG": "LOG(", "EXP": "EXP(",
    "SQRT": "SQRT(", "RAIZ": "RAIZ(", "ABS": "ABS(",
    "MAT2": "MAT2(", "MAT3": "MAT3(", "DOT": "DOT(", "CROSS": "CROSS(",
    "POL": "POL(", "REC": "REC(",
    # v4.0
    "CUAD": "CUAD(", "CUB": "CUB(",
    "BIN": "BIN(", "OCT": "OCT(", "HEX": "HEX(",
}


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

        # ---- EVALUACION GENERAL (Shunting-yard + RPN, sin eval) ----
        # Soporta: +,-,*,/,^,%, parentesis, funciones trig/hiperbolicas
        # (DEG por defecto), LN/LOG/EXP/SQRT/ABS, PI/E, variables A-Y/ANS.
        res_num = evaluar_expresion(cmd, variables_actuales())
        ANS = res_num
        return decimal_a_fraccion(res_num), "", ""
    except Exception:
        return "Error Sintaxis", "", ""


# ==========================================================
# 13. BUCLE DE EJECUCION (PC / PICO)
# ==========================================================
INSTRUCCIONES = (
    "PiCalc OS v4.0 - Cada linea = un TOKEN (un boton).\n"
    "Numeros/operadores: 0-9 . + - * / ^ % ( ) , =\n"
    "Funciones: SIN COS TAN ASIN ACOS ATAN SINH COSH TANH LN LOG EXP SQRT RAIZ ABS\n"
    "Memoria: A B C X Y ANS  |  Comandos: STO RCL\n"
    "Calculo: SOLVE DERIV<f>,<x>  INT<f>,<a>,<b>  MCD MCM RAND PRIMOS\n"
    "Matrices (sistemas): MAT2 MAT3 DOT CROSS\n"
    "Matrices (algebra): MATDEF<n>,<f>,<c>,vals  MATADD MATMUL MATTRANS MATDET MATINV\n"
    "Polinomios: CUAD(a,b,c)  CUB(a,b,c,d)\n"
    "Tabla: TABLE<expr>,<ini>,<fin>,<paso>\n"
    "Base-N: BIN(n) OCT(n) HEX(n) AND(a,b) OR(a,b) XOR(a,b) NOT(n)\n"
    "Complejo: CMPLX (toggle) | usar I como unidad imaginaria\n"
    "Control: AC DEL IGUAL BYPASS=modo examen"
)


def iniciar():
    global MODO_EXAMEN, ENTRADA_TOKENS

    renderizar_pantalla("PiCalc OS v4.1", f"Modo Examen: {MODO_EXAMEN}",
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

        # ---- Comandos de control ----
        if accion_u == "BYPASS":
            MODO_EXAMEN = not MODO_EXAMEN
            renderizar_pantalla("".join(ENTRADA_TOKENS) or "0", f"Modo Examen: {MODO_EXAMEN}")
            continue

        if accion_u == "AC":
            ENTRADA_TOKENS = []
            renderizar_pantalla("0")
            continue

        if accion_u == "DEL":
            # Borra el ULTIMO TOKEN completo (ej: "SIN(" se va de un golpe)
            if ENTRADA_TOKENS:
                ENTRADA_TOKENS.pop()
            renderizar_pantalla("".join(ENTRADA_TOKENS) or "0")
            continue

        if accion_u == "IGUAL":
            if ENTRADA_TOKENS:
                expr = construir_expresion(ENTRADA_TOKENS)
                texto_anterior = "".join(ENTRADA_TOKENS)
                l1, l2, l3 = procesar_todo(expr)
                renderizar_pantalla(texto_anterior, l1, l2, l3)
                # FIX v3.2: solo limpiamos el buffer si el calculo fue exitoso.
                # Si hubo error, la expresion queda en pantalla para poder editarla
                # (comportamiento identico al de las Casio fisicas).
                if l1 != "Error Sintaxis":
                    ENTRADA_TOKENS = []
            continue

        # ---- Cualquier otro boton: se agrega como TOKEN ----
        # FIX v3.2: en la Pico, escanear_teclado() devuelve tokens ya formateados
        # (ej: "SIN(", "MAT2(") que NO son puramente .isalpha(). Para que PC y Pico
        # tengan comportamiento identico, intentamos el alias primero sobre la parte
        # alfabetica base, y si no hay alias, usamos el token tal como llego.
        token = ALIAS_TOKENS.get(accion_u, None)
        if token is None:
            # En la Pico los tokens de funcion ya traen el "(" incluido.
            # En la consola PC el usuario puede tipear "SIN" o "SIN(" indistintamente.
            token = accion_u if accion_u in ALIAS_TOKENS.values() else accion

        ENTRADA_TOKENS.append(token)
        renderizar_pantalla("".join(ENTRADA_TOKENS))


if __name__ == "__main__":
    iniciar()

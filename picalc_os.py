import time
import math

# ==========================================
# 1. DETECCIÓN DE ENTORNO Y HARDWARE
# ==========================================
try:
    import machine
    import sh1106
    ENTORNO_PICO = True
except ImportError:
    ENTORNO_PICO = False

MODO_EXAMEN = True  # True = Modo bloqueado (Clase) | False = Potencia Máxima (CAS/ClassWiz)
MEMORIA = {"A": 0, "B": 0, "C": 0, "X": 0, "Y": 0}
ESTADISTICA_LISTA = []  # Almacenamiento para el editor de listas de estadística

display = None
if ENTORNO_PICO:
    try:
        i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
        display = sh1106.SH1106_I2C(128, 64, i2c)
        display.sleep(False)
    except Exception:
        pass


def renderizar_pantalla(linea_eq, l2="", l3="", l4=""):
    """Renderiza hasta 4 líneas de texto adaptadas para OLED de 128x64 o Consola PC."""
    if ENTORNO_PICO and display:
        display.fill(0)
        display.text(linea_eq[:16], 0, 2, 1)
        display.text(l2[:16], 0, 18, 1)
        display.text(l3[:16], 0, 34, 1)
        display.text(l4[:16], 0, 50, 1)
        display.show()
    else:
        print("\n" + "=" * 34)
        print("| [PANTALLA CASIO CLASSWIZ]        |")
        print("-" * 34)
        print(f"| L1: {linea_eq:<28} |")
        print(f"| L2: {l2:<28} |")
        print(f"| L3: {l3:<28} |")
        print(f"| L4: {l4:<28} |")
        print("=" * 34)


# ==========================================
# 2. AYUDANTES MATEMÁTICOS Y ALGEBRA
# ==========================================
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
        num = int(n)
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


# ==========================================
# 3. MOTOR DE EXPRESIONES (SHUNTING-YARD + RPN)
# ==========================================
# Reemplaza por completo el uso de eval(). Convierte un string infijo
# (ej: "SIN(30)+2^3") en una lista RPN mediante el algoritmo de Dijkstra
# y la evalúa con una pila, sin pasar nunca por el interprete de Python.
#
# Modo de ángulos (DEG):
#   - SIN/COS/TAN  -> convierten el argumento de grados a radianes
#   - ASIN/ACOS/ATAN -> convierten el resultado de radianes a grados
#   - El resto de funciones (hiperbólicas, logaritmos, raíz, exp) no
#     dependen del modo de ángulo.
#
# NOTA / LIMITACIÓN CONOCIDA:
#   La precedencia del menos unario (NEG) se fijó por ENCIMA de "^" para
#   que "2^-2" se resuelva como 2^(-2) = 0.25 (caso muy frecuente en
#   exponentes negativos / notación científica). Como contrapartida,
#   "-2^2" se evalúa como (-2)^2 = 4 en vez de -(2^2) = -4. Si se
#   necesita ese caso, debe escribirse explícitamente "-(2^2)".

FUNC_MAP = {
    # nombre: (función math, modo de conversión de ángulo)
    "SIN":  (math.sin,  "deg_in"),
    "COS":  (math.cos,  "deg_in"),
    "TAN":  (math.tan,  "deg_in"),
    "ASIN": (math.asin, "deg_out"),
    "ACOS": (math.acos, "deg_out"),
    "ATAN": (math.atan, "deg_out"),
    "SINH": (math.sinh, None),
    "COSH": (math.cosh, None),
    "TANH": (math.tanh, None),
    "LN":   (math.log,   None),  # logaritmo natural
    "LOG":  (math.log10, None),  # logaritmo base 10
    "EXP":  (math.exp,   None),
    "SQRT": (math.sqrt,  None),
    "RAIZ": (math.sqrt,  None),
    "ABS":  (abs,        None),
}

CONSTANTES = {"PI": math.pi, "E": math.e}

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
            elif nombre == "X":
                tokens.append(("VAR", "X"))
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
    antes de empujar 'op', según precedencia y asociatividad."""
    prec_top = PRECEDENCIA.get(top_val, 0)
    prec_op = PRECEDENCIA[op]
    if prec_top > prec_op:
        return True
    if prec_top == prec_op and op not in ASOC_DERECHA:
        return True
    return False


def a_rpn(tokens):
    """Algoritmo Shunting-yard: convierte tokens infijos a notación RPN."""
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
    """Evalúa una lista de tokens en notación RPN usando una pila."""
    if variables is None:
        variables = {}
    pila = []
    for (tipo, val) in rpn:
        if tipo == "NUM":
            pila.append(val)
        elif tipo == "VAR":
            if val not in variables:
                raise ValueError("Variable no definida: " + val)
            pila.append(float(variables[val]))
        elif tipo == "FUNC":
            arg = pila.pop()
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
    """Punto de entrada único: tokeniza, convierte a RPN y evalúa.
    Reemplaza todo uso de eval() en el motor matemático."""
    tokens = tokenizar(expr)
    rpn = a_rpn(tokens)
    return evaluar_rpn(rpn, variables)


# ==========================================
# 4. NÚCLEO MATEMÁTICO AVANZADO
# ==========================================
def calcular_raiz_analitica(valor_str):
    try:
        valor = evaluar_expresion(valor_str.upper())
        if valor < 0:
            return "Error: Negativo"
        raiz = valor ** 0.5
        if MODO_EXAMEN or raiz.is_integer():
            return str(int(raiz)) if raiz.is_integer() else f"{raiz:.5f}"

        # Extracción analítica de factores (Visualización natural ej: 2√3 -> 2*v(3))
        fuera, dentro = 1, int(valor)
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
    if MODO_EXAMEN:
        return f"{val:.5f}"
    try:
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


# ==========================================
# 5. SOLVER, MATRICES Y VECTORES (ÁLGEBRA)
# ==========================================
def resolver_ecuacion_lineal(eq_str):
    """Resuelve f(x) = 0 o f(x) = g(x) mediante aproximación Newton-Raphson."""
    if MODO_EXAMEN:
        return "Error: No disp"
    eq = eq_str.upper().replace("=", "-(") + ")" if "=" in eq_str else eq_str.upper()
    x = 1.0
    h = 1e-6
    for _ in range(25):  # Límite reducido (20-30) para no congelar el hilo de MicroPython
        try:
            f_x = evaluar_expresion(eq, {"X": x})
            f_xh = evaluar_expresion(eq, {"X": x + h})
            derivada = (f_xh - f_x) / h
            if abs(derivada) < 1e-12:
                break
            nuevo_x = x - (f_x / derivada)
            if abs(nuevo_x - x) < 1e-6:
                return f"X = {int(nuevo_x)}" if nuevo_x.is_integer() else f"X = {nuevo_x:.5f}"
            x = nuevo_x
        except Exception:
            break
    return "Sin Solucion Real"


def resolver_sistema_matrices(datos_str):
    """
    Resuelve sistemas o dibuja matrices.
    Formato entrada: MAT2X2[a,b,c,d] -> Calcula Determinante
    """
    if MODO_EXAMEN:
        return "Error: No disp"
    try:
        nums = [float(x) for x in datos_str.split("[")[-1].replace("]", "").split(",")]
        if "2X2" in datos_str:
            det = (nums[0] * nums[3]) - (nums[1] * nums[2])
            return f"DET = {det}", f"[{nums[0]} {nums[1]}]", f"[{nums[2]} {nums[3]}]"
    except Exception:
        pass
    return "Error Matriz", "", ""


# ==========================================
# 6. CÁLCULO INTEGRAL Y DIFERENCIAL NUMÉRICO
# ==========================================
def calcular_derivada(eq, punto_str):
    if MODO_EXAMEN:
        return "Error: No disp"
    try:
        eq_u = eq.upper()
        x = evaluar_expresion(punto_str.upper())
        h = 1e-5
        f_xh1 = evaluar_expresion(eq_u, {"X": x + h})
        f_xh2 = evaluar_expresion(eq_u, {"X": x - h})
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
        lim_inf = evaluar_expresion(partes[0].upper())
        lim_sup = evaluar_expresion(partes[1].upper())
        n = 100
        h = (lim_sup - lim_inf) / n
        suma = evaluar_expresion(eq_u, {"X": lim_inf}) + evaluar_expresion(eq_u, {"X": lim_sup})

        for i in range(1, n):
            x = lim_inf + i * h
            peso = 4 if i % 2 != 0 else 2
            suma += peso * evaluar_expresion(eq_u, {"X": x})
        return f"INT = {(suma * h / 3):.5f}"
    except Exception:
        return "Error"


# ==========================================
# 7. ESTADÍSTICA BASADA EN LISTAS
# ==========================================
def procesar_estadistica(comando):
    """Maneja el ingreso de datos en lista y cálculos estadísticos."""
    global ESTADISTICA_LISTA
    try:
        if "ADD:" in list(comando)[0:4] or "ADD:" in comando:
            val = float(comando.split(":")[-1])
            ESTADISTICA_LISTA.append(val)
            return f"Lista: {ESTADISTICA_LISTA}", f"N = {len(ESTADISTICA_LISTA)}"
        elif "CLEAR" in comando:
            ESTADISTICA_LISTA = []
            return "Lista Limpia", "N = 0"
        elif "CALC" in comando:
            if not ESTADISTICA_LISTA:
                return "Lista vacía", ""
            n = len(ESTADISTICA_LISTA)
            media = sum(ESTADISTICA_LISTA) / n
            varianza = sum((x - media) ** 2 for x in ESTADISTICA_LISTA) / n
            desviacion = varianza ** 0.5
            return f"Media: {media:.4f}", f"StdDev: {desviacion:.4f}", f"N = {n}"
    except Exception:
        pass
    return "Error Estad.", ""


# ==========================================
# 8. PROCESADOR DE COMANDOS GENERAL
# ==========================================
def procesar_todo(entrada_cruda):
    cmd = entrada_cruda.upper().replace("MULT", "*").replace("DIV", "/").replace("MAS", "+").replace("MENOS", "-")

    try:
        # ---- SECCIÓN ESTADÍSTICA ----
        if "STAT" in cmd:
            res = procesar_estadistica(cmd.split("STAT")[-1])
            return res if isinstance(res, tuple) else (res, "", "")

        # ---- SECCIÓN ÁLGEBRA Y CÁLCULO ----
        if "SOLVE" in cmd:
            return resolver_ecuacion_lineal(cmd.split("SOLVE")[-1]), "", ""
        if "MAT" in cmd:
            return resolver_sistema_matrices(cmd)
        if "DERIV" in cmd:
            partes = cmd.split("DERIV")[-1].split(";")
            return calcular_derivada(partes[0], partes[1]), "", ""
        if "INT" in cmd:
            partes = cmd.split("INT")[-1].split(";")
            return calcular_integral(partes[0], partes[1]), "", ""
        if "PRIMOS" in cmd:
            return f"Fact: {factorizar_primos(cmd.split('PRIMOS')[-1])}", "", ""
        if "MCD" in cmd:
            p = cmd.split("MCD")[-1].split(",")
            return f"MCD = {mcd(int(p[0]), int(p[1]))}", "", ""
        if "MCM" in cmd:
            p = cmd.split("MCM")[-1].split(",")
            return f"MCM = {mcm(int(p[0]), int(p[1]))}", "", ""

        # ---- CONVERSIONES DE COORDENADAS Y ÁNGULOS ----
        if "POL" in cmd:  # Polar a Rectangular: POL(r, deg) -> X, Y
            p = cmd.split("POL")[-1].replace("(", "").replace(")", "").split(",")
            r, rad = float(p[0]), math.radians(float(p[1]))
            return f"X = {r * math.cos(rad):.4f}", f"Y = {r * math.sin(rad):.4f}"
        if "REC" in cmd:  # Rectangular a Polar: REC(x, y) -> R, θ
            p = cmd.split("REC")[-1].replace("(", "").replace(")", "").split(",")
            x, y = float(p[0]), float(p[1])
            return f"R = {math.hypot(x, y):.4f}", f"ANG = {math.degrees(math.atan2(y, x)):.2f}°"

        # ---- ALEATORIO Y RAÍZ ANALÍTICA ----
        if "RAND" in cmd:
            return f"Rand: {time.time() % 1:.5f}", "", ""
        if "RAIZ" in cmd:
            return calcular_raiz_analitica(cmd.split("RAIZ")[-1]), "", ""

        # ---- EVALUACIÓN GENERAL (Shunting-yard + RPN, sin eval) ----
        # Soporta: +, -, *, /, ^, %, paréntesis, SIN/COS/TAN/ASIN/ACOS/ATAN
        # (en modo DEG), SINH/COSH/TANH, LN, LOG, EXP, SQRT, ABS, PI, E.
        res_num = evaluar_expresion(cmd)
        return decimal_a_fraccion(res_num), "", ""
    except Exception:
        return "Error Sintaxis", "", ""


# ==========================================
# 9. BUCLE DE EJECUCIÓN (PC / PICO)
# ==========================================
def iniciar():
    global MODO_EXAMEN
    entrada = ""
    renderizar_pantalla("PiCalc ClassWiz v2", f"Modo Examen: {MODO_EXAMEN}", "Tipee comandos para", "comenzar el test.")

    while True:
        if ENTORNO_PICO:
            # Aquí iría el escaneo físico de matriz (ya estructurado en respuestas anteriores)
            time.sleep(0.1)
        else:
            accion = input("\nIngrese botón/comando: ").strip()
            if accion.upper() == "BYPASS":
                MODO_EXAMEN = not MODO_EXAMEN
                print(f"--> [SISTEMA] Modo Examen cambiado a: {MODO_EXAMEN}")
                continue
            elif accion.upper() == "AC":
                entrada = ""
                renderizar_pantalla("0")
                continue
            elif accion.upper() == "IGUAL":
                if entrada:
                    l1, l2, l3 = procesar_todo(entrada)
                    renderizar_pantalla(entrada, l1, l2, l3)
                continue

            entrada += accion
            renderizar_pantalla(entrada)


if __name__ == "__main__":
    iniciar()

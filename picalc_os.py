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
ESTADISTICA_LISTA = [] # Almacenamiento para el editor de listas de estadística

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
        print("\n" + "="*34)
        print(f"| [PANTALLA CASIO CLASSWIZ]        |")
        print("-"*34)
        print(f"| L1: {linea_eq:<28} |")
        print(f"| L2: {l2:<28} |")
        print(f"| L3: {l3:<28} |")
        print(f"| L4: {l4:<28} |")
        print("="*34)

# ==========================================
# 2. AYUDANTES MATEMÁTICOS Y ALGEBRA
# ==========================================
def mcd(a, b):
    while b: a, b = b, a % b
    return a

def mcm(a, b):
    return abs(a * b) // mcd(a, b) if (a and b) else 0

def factorizar_primos(n):
    if MODO_EXAMEN: return "Error: No disp"
    try:
        num = int(n)
        if num < 2: return str(num)
        factores = []
        d = 2
        while d * d <= num:
            while (num % d) == 0:
                factores.append(str(d))
                num //= d
            d += 1
        if num > 1: factores.append(str(num))
        return " * ".join(factores)
    except: return "Error"

# ==========================================
# 3. NÚCLEO MATEMÁTICO AVANZADO
# ==========================================
def calcular_raiz_analitica(valor_str):
    try:
        valor = float(valor_str)
        if valor < 0: return "Error: Negativo"
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
            else: d += 1
        return f"{fuera}*v({dentro})" if fuera > 1 else f"v({dentro})"
    except: return "Error"

def decimal_a_fraccion(val):
    if MODO_EXAMEN: return f"{val:.5f}"
    try:
        if isinstance(val, int) or val.is_integer(): return str(int(val))
        d_base = 100000
        n_base = int(round(val * d_base))
        a, b = abs(n_base), abs(d_base)
        while b: a, b = b, a % b
        num, den = int(n_base / a), int(d_base / a)
        return f"{num}/{den}" if den < 1000 else f"{val:.5f}"
    except: return f"{val:.5f}"

# ==========================================
# 4. SOLVER, MATRICES Y VECTORES (ÁLGEBRA)
# ==========================================
def resolver_ecuacion_lineal(eq_str):
    """Resuelve f(x) = 0 o f(x) = g(x) mediante aproximación Newton-Raphson."""
    if MODO_EXAMEN: return "Error: No disp"
    eq = eq_str.upper().replace("=", "-(") + ")" if "=" in eq_str else eq_str
    x = 1.0
    h = 1e-6
    for _ in range(80):
        try:
            f_x = eval(eq.replace("X", f"({x})"))
            f_xh = eval(eq.replace("X", f"({x+h})"))
            derivada = (f_
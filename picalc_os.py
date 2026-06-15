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
            derivada = (f_xh - f_x) / h
            if abs(derivada) < 1e-12: break
            nuevo_x = x - (f_x / derivada)
            if abs(nuevo_x - x) < 1e-6:
                return f"X = {int(nuevo_x)}" if nuevo_x.is_integer() else f"X = {nuevo_x:.5f}"
            x = nuevo_x
        except: break
    return "Sin Solución Real"

def resolver_sistema_matrices(datos_str):
    """
    Resuelve sistemas o dibuja matrices. 
    Formato entrada: MAT2X2[a,b,c,d] -> Calcula Determinante
    """
    if MODO_EXAMEN: return "Error: No disp"
    try:
        # Extrae los números de los corchetes
        nums = [float(x) for x in datos_str.split("[")[-1].replace("]", "").split(",")]
        if "2X2" in datos_str:
            det = (nums[0]*nums[3]) - (nums[1]*nums[2])
            return f"DET = {det}", f"[{nums[0]} {nums[1]}]", f"[{nums[2]} {nums[3]}]"
    except: pass
    return "Error Matriz", "", ""

# ==========================================
# 5. CÁLCULO INTEGRAL Y DIFERENCIAL NUMÉRICO
# ==========================================
def calcular_derivada(eq, punto_str):
    if MODO_EXAMEN: return "Error: No disp"
    try:
        x = float(punto_str)
        h = 1e-5
        f_xh1 = eval(eq.replace("X", f"({x+h})"))
        f_xh2 = eval(eq.replace("X", f"({x-h})"))
        return f"d/dx = {(f_xh1 - f_xh2) / (2*h):.5f}"
    except: return "Error"

def calcular_integral(eq, limites_str):
    """Integral definida usando la Regla de Simpson (100 intervalos)."""
    if MODO_EXAMEN: return "Error: No disp"
    try:
        lim_inf, lim_sup = map(float, limites_str.split(","))
        n = 100
        h = (lim_sup - lim_inf) / n
        suma = eval(eq.replace("X", f"({lim_inf})")) + eval(eq.replace("X", f"({lim_sup})"))
        
        for i in range(1, n):
            x = lim_inf + i * h
            peso = 4 if i % 2 != 0 else 2
            suma += peso * eval(eq.replace("X", f"({x})"))
        return f"INT = {(suma * h / 3):.5f}"
    except: return "Error"

# ==========================================
# 6. ESTADÍSTICA BASADA EN LISTAS
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
            if not ESTADISTICA_LISTA: return "Lista vacía", ""
            n = len(ESTADISTICA_LISTA)
            media = sum(ESTADISTICA_LISTA) / n
            varianza = sum((x - media)**2 for x in ESTADISTICA_LISTA) / n
            desviacion = varianza ** 0.5
            return f"Media: {media:.4f}", f"StdDev: {desviacion:.4f}", f"N = {n}"
    except: pass
    return "Error Estad.", ""

# ==========================================
# 7. PROCESADOR DE COMANDOS GENERAL
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
        if "POL" in cmd: # Polar a Rectangular: POL(r, degh) -> X, Y
            p = cmd.split("POL")[-1].replace("(","").replace(")","").split(",")
            r, rad = float(p[0]), math.radians(float(p[1]))
            return f"X = {r*math.cos(rad):.4f}", f"Y = {r*math.sin(rad):.4f}"
        if "REC" in cmd: # Rectangular a Polar: REC(x, y) -> R, θ
            p = cmd.split("REC")[-1].replace("(","").replace(")","").split(",")
            x, y = float(p[0]), float(p[1])
            return f"R = {math.hypot(x,y):.4f}", f"ANG = {math.degrees(math.atan2(y,x)):.2f}°"

        # ---- TRIGONOMETRÍA, LOGARITMOS Y OTRAS ----
        # Reemplazos dinámicos usando la librería math estándar
        cmd = cmd.replace("SIN(", "math.sin(").replace("COS(", "math.cos(").replace("TAN(", "math.tan(")
        cmd = cmd.replace("ASIN(", "math.asin(").replace("ACOS(", "math.acos(").replace("ATAN(", "math.atan(")
        cmd = cmd.replace("SINH(", "math.sinh(").replace("COSH(", "math.cosh(").replace("TANH(", "math.tanh(")
        cmd = cmd.replace("LN(", "math.log(").replace("LOG(", "math.log10(").replace("EXP(", "math.exp(")
        cmd = cmd.replace("PI", str(math.pi)).replace("E", str(math.e))
        
        if "RAND" in cmd: return f"Rand: {time.time() % 1:.5f}", "", ""
        if "RAIZ" in cmd: return calcular_raiz_analitica(cmd.split("RAIZ")[-1]), "", ""

        # Evaluación aritmética lineal estándar
        res_num = eval(cmd)
        return decimal_a_fraccion(res_num), "", ""
    except Exception as e:
        return "Error Sintaxis", "", ""

# ==========================================
# 8. BUCLE DE EJECUCIÓN (PC / PICO)
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

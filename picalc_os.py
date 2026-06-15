import time

# ==========================================
# 1. DETECCIÓN DE ENTORNO (PC vs RASPBERRY PICO)
# ==========================================
try:
    import machine
    import sh1106  # Driver de la pantalla OLED
    ENTORNO_PICO = True
except ImportError:
    ENTORNO_PICO = False

# ==========================================
# 2. CONFIGURACIÓN GLOBAL Y MODO EXAMEN
# ==========================================
# True = Modo restringido (da resultados simples/decimales para la profe).
# False = Modo Avanzado / CAS descapado.
MODO_EXAMEN = True 

# Variables de memoria de la calculadora (equivalente a las teclas STO/RCL)
MEMORIA = {"A": 0, "B": 0, "C": 0, "X": 0, "Y": 0}

# ==========================================
# 3. INTERFAZ DE PANTALLA (AUTOMÁTICA)
# ==========================================
display = None
if ENTORNO_PICO:
    try:
        i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
        display = sh1106.SH1106_I2C(128, 64, i2c)
        display.sleep(False)
    except Exception:
        print("Hardware OLED no detectado.")

def renderizar_pantalla(linea_eq, linea_res=""):
    """Dibuja en la OLED real o genera un recuadro visual en la terminal de la PC."""
    if ENTORNO_PICO and display:
        display.fill(0)
        display.text(linea_eq[:16], 0, 10, 1) # Máximo 16 caracteres por línea
        display.text(linea_res[:16], 0, 45, 1)
        display.show()
    else:
        # Renderizado estético para testear en tu PC
        print("\n" + "="*32)
        print(f"| [PANTALLA OLED SIMULADA]     |")
        print("-"*32)
        print(f"| EQ:  {linea_eq:<23} |")
        print(f"| RES: {linea_res:<23} |")
        print("="*32)

# ==========================================
# 4. MOTOR MATEMÁTICO AVANZADO CON FILTROS
# ==========================================
def simplificar_fraccion(n, d):
    """Algoritmo matemático para reducir fracciones (ej: 4/12 -> 1/3)."""
    a, b = abs(n), abs(d)
    while b:
        a, b = b, a % b
    mcd = a
    return int(n / mcd), int(d / mcd)

def calcular_raiz(numero_str):
    """Calcula raíces cuadradas aplicando el bloqueo del Modo Examen."""
    try:
        valor = float(numero_str)
        if valor < 0: return "Error: Negativo"
        
        raiz = valor ** 0.5
        
        if MODO_EXAMEN:
            # Comportamiento común exigido en clase: entero o decimal directo
            if raiz.is_integer(): return str(int(raiz))
            return f"{raiz:.5f}"
        else:
            # MODO AVANZADO: Intenta simplificar la raíz de forma analítica (CAS)
            # Si es exacta:
            if raiz.is_integer(): return f"{int(raiz)}"
            
            # Intenta factorizar raíces no exactas (ej: √12 -> 2√3)
            # Algoritmo de extracción de factores:
            fuera = 1
            dentro = int(valor)
            d = 2
            while d * d <= dentro:
                if dentro % (d * d) == 0:
                    fuera *= d
                    dentro //= (d * d)
                else:
                    d += 1
            if fuera > 1:
                return f"{fuera}*v({dentro})" # Representación de raíz en texto plano
            return f"v({int(valor)})"
            
    except Exception:
        return "Error de Entrada"

def procesar_operacion(entrada_cruda):
    """Analiza la cadena de texto y ejecuta la matemática correspondiente."""
    # Reemplazos globales para compatibilidad con el motor de Python
    eq = entrada_cruda.upper().replace("MULT", "*").replace("DIV", "/").replace("MAS", "+").replace("MENOS", "-")
    
    try:
        # 1. Procesar función Raíz Cuadrada
        if "RAIZ" in eq:
            num_part = eq.split("RAIZ")[-1]
            return calcular_raiz(num_part)
            
        # 2. Inyección de variables guardadas en memoria
        for var, val in MEMORIA.items():
            if var in eq:
                eq = eq.replace(var, str(val))
                
        # 3. Cálculo general
        resultado = eval(eq)
        
        # 4. Formateo de salida según el modo
        if isinstance(resultado, float) and resultado.is_integer():
            resultado = int(resultado)
            
        if not MODO_EXAMEN and isinstance(resultado, float):
            # En modo avanzado, si da decimal, intenta mostrarlo como fracción irreducible
            if "0." in str(resultado) or "." in str(resultado):
                val_dec = resultado
                d_base = 100000
                n_base = int(round(val_dec * d_base))
                num, den = simplificar_fraccion(n_base, d_base)
                if den < 1000: # Evita fracciones ridículamente largas
                    return f"{num}/{den}"
                    
        return str(resultado)
    except Exception:
        return "Error"

# ==========================================
# 5. CONFIGURACIÓN DE PINES (SOLO PARA PICO)
# ==========================================
FILAS = [6, 7, 8, 9, 10, 11]
COLUMNAS = [12, 13, 14, 15, 16, 17]

if ENTORNO_PICO:
    pines_filas = [machine.Pin(p, machine.Pin.OUT) for p in FILAS]
    pines_columnas = [machine.Pin(p, machine.Pin.IN, machine.Pin.PULL_DOWN) for p in COLUMNAS]

MAPA_TECLADO = [
    ["7", "8", "9", "DEL", "AC"],
    ["4", "5", "6", "MULT", "DIV"],
    ["1", "2", "3", "MAS", "MENOS"],
    ["0", ".", "X", "Y", "IGUAL"],
    ["RAIZ", "STO_A", "STO_B", "SHIFT", "ALPHA"]
]

# ==========================================
# 6. BUCLE PRINCIPAL E INTERACCIÓN
# ==========================================
def leer_boton_pico():
    """Escanea la matriz física si está corriendo en la placa."""
    for i, pin_fila in enumerate(pines_filas):
        pin_fila.value(1)
        for j, pin_col in enumerate(pines_columnas):
            if pin_col.value() == 1:
                time.sleep_ms(50) # Debounce
                while pin_col.value() == 1: pass
                pin_fila.value(0)
                return MAPA_TECLADO[i][j]
        pin_fila.value(0)
    return None

def ejecutar_sistema():
    global MODO_EXAMEN
    entrada_usuario = ""
    resultado_actual = ""
    
    # Mensaje inicial de inicio
    renderizar_pantalla("PiCalc Ready", f"Examen: {MODO_EXAMEN}")
    
    if not ENTORNO_PICO:
        print("\n--> [INFO] Corriendo en PC.")
        print("Tipeá comandos válidos del mapa (Ej: 7 MAS 9, RAIZ12, RAIZ16, AC, IGUAL).")
        print("Para alternar Modo Examen oculto, tipeá el atajo: BYPASS\n")

    while True:
        boton = None
        
        if ENTORNO_PICO:
            boton = leer_boton_pico()
            # Lógica del atajo físico: SHIFT + 7 + 9 retenidos (Se emula revisando la cadena en orden)
            # En hardware real se puede pulir midiendo pulsaciones simultáneas.
        else:
            # Captura lo que escribís en la consola de la PC
            accion_pc = input("Apretá un botón: ").strip().upper()
            if accion_pc == "BYPASS":
                MODO_EXAMEN = not MODO_EXAMEN
                print(f"\n[SISTEMA] Modo Examen cambiado a: {MODO_EXAMEN}")
                continue
            boton = accion_pc

        if boton:
            if boton == "AC":
                entrada_usuario = ""
                resultado_actual = ""
                renderizar_pantalla("0")
            elif boton == "DEL":
                entrada_usuario = entrada_usuario[:-1]
                renderizar_pantalla(entrada_usuario if entrada_usuario else "0")
            elif boton == "IGUAL":
                if entrada_usuario:
                    # Atajo por combinatoria de software detectado al dar IGUAL
                    if "SHIFT79" in entrada_usuario:
                        MODO_EXAMEN = not MODO_EXAMEN
                        entrada_usuario = ""
                        renderizar_pantalla("0")
                        continue
                    
                    # Manejo básico de guardado en memoria rápida (Ej: STO_A)
                    if "STO_" in entrada_usuario:
                        parts = entrada_usuario.split("STO_")
                        var_destino = parts[1][0]
                        valor_num = procesar_operacion(parts[0])
                        try:
                            MEMORIA[var_destino] = float(valor_num)
                            renderizar_pantalla(f"Guardado en {var_destino}", valor_num)
                            entrada_usuario = ""
                            continue
                        except:
                            renderizar_pantalla("Error Memoria")
                            entrada_usuario = ""
                            continue
                            
                    resultado_actual = procesar_operacion(entrada_usuario)
                    renderizar_pantalla(entrada_usuario, resultado_actual)
            else:
                entrada_usuario += boton
                renderizar_pantalla(entrada_usuario)
                
        time.sleep(0.05)

if __name__ == "__main__":
    ejecutar_sistema()

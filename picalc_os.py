import machine
import time
import sys

# ==========================================
# 1. CONFIGURACIÓN DEL HARDWARE (I2C y GPIO)
# ==========================================

# Configuración de la pantalla OLED (SH1106 / SSD1306)
# Ajustá los pines SCL y SDA según cómo los sueldes a tu RP2040
try:
    sda_pin = machine.Pin(4)
    scl_pin = machine.Pin(5)
    i2c = machine.I2C(0, sda=sda_pin, scl=scl_pin, freq=400000)
    # Importamos el driver externo (debe estar guardado en la placa como sh1106.py)
    import sh1106
    display = sh1106.SH1106_I2C(128, 64, i2c)
    display.sleep(False)
except Exception as e:
    print("Error al iniciar pantalla:", e)
    display = None

# Definición de la Matriz del Teclado de la Casio
# Cambiá estos números por los pines GPIO reales que uses para tus filas y columnas
FILAS = [6, 7, 8, 9, 10, 11]
COLUMNAS = [12, 13, 14, 15, 16, 17]

# Inicialización de Pines de la Matriz
pines_filas = [machine.Pin(pin, machine.Pin.OUT) for pin in FILAS]
pines_columnas = [machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_DOWN) for pin in COLUMNAS]

# Mapa de caracteres según la posición de la matriz (Ejemplo conceptual de distribución)
MAPA_TECLADO = [
    ["7", "8", "9", "DEL", "AC"],
    ["4", "5", "6", "MULT", "DIV"],
    ["1", "2", "3", "MAS", "MENOS"],
    ["0", "DOT", "EXP", "ANS", "IGUAL"],
    ["SIN", "COS", "TAN", "RAIZ", "POT"],
    ["SHIFT", "ALPHA", "UP", "DOWN", "MODE"]
]

# ==========================================
# 2. CONFIGURACIÓN DEL MODO EXAMEN (OCULTO)
# ==========================================
# Si está en True, se desactivan las funciones avanzadas y actúa como calculadora estándar.
MODO_EXAMEN = True 

# ==========================================
# 3. CONTROLADORES Y LÓGICA DE ENTRADA
# ==========================================

def escanear_teclado():
    """Escanea la matriz de botones y devuelve el caracter presionado o None."""
    for i, pin_fila in enumerate(pines_filas):
        pin_fila.value(1) # Energiza la fila actual
        for j, pin_col en enumerate(pines_columnas):
            if pin_col.value() == 1:
                # Anti-rebote (Debounce) básico por software
                time.sleep_ms(50)
                while pin_col.value() == 1:
                    pass # Espera a que suelte el botón
                pin_fila.value(0)
                return MAPA_TECLADO[i][j]
        pin_fila.value(0) # Apaga la fila antes de pasar a la siguiente
    return None

def actualizar_pantalla(linea1, linea2=""):
    """Dibuja el texto en la pantalla OLED imitando un formato limpio."""
    if display:
        display.fill(0) # Limpia pantalla
        display.text(linea1, 0, 10, 1)  # Línea de entrada/ecuación
        display.text(linea2, 0, 45, 1)  # Línea de resultado (alineado abajo)
        display.show()
    else:
        print(f"PANTALLA -> L1: {linea1} | L2: {linea2}")

# ==========================================
# 4. MOTOR MATEMÁTICO CON RESTRICCIONES
# ==========================================

def calcular_raiz(numero_str):
    """Calcula la raíz cuadrada aplicando las restricciones del Modo Examen."""
    try:
        valor = float(numero_str)
        if valor < 0:
            return "Error: Negativo"
        
        resultado_real = valor ** 0.5
        
        if MODO_EXAMEN:
            # En modo examen se comporta de forma tradicional: devuelve el número directo (entero o decimal)
            if resultado_real.is_integer():
                return str(int(resultado_real))
            else:
                return f"{resultado_real:.5f}" # Formato decimal estándar
        else:
            # Modo Avanzado (CAS descapado): Si es una raíz exacta o simplificable, podrías
            # programar acá que devuelva texto formateado (ej: "4" o "2√3" para raíz de 12)
            if resultado_real.is_integer():
                return f"Fact: {int(resultado_real)}"
            else:
                # Ejemplo de salida CAS avanzada simulada
                return f"Raiz({numero_str})"
                
    except ValueError:
        return "Error de Sintaxis"

def procesar_operacion(entrada):
    """Evalúa la cadena de texto acumulada de forma segura."""
    # Reemplazos de interfaz a operadores de Python
    ecuacion = entrada.replace("MULT", "*").replace("DIV", "/").replace("MAS", "+").replace("MENOS", "-")
    
    try:
        # Si se presionó el botón de raíz en la interfaz
        if "RAIZ" in ecuacion:
            num = ecuacion.split("RAIZ")[-1]
            return calcular_raiz(num)
        
        # Evaluación estándar para sumas, restas, etc.
        resultado = eval(ecuacion)
        if isinstance(resultado, float) and resultado.is_integer():
            return str(int(resultado))
        return str(resultado)
    except Exception:
        return "Error"

# ==========================================
# 5. BUCLE PRINCIPAL Y GESTIÓN DE ENERGÍA
# ==========================================

def iniciar_calculadora():
    # Desactivar el segundo núcleo explícitamente no es necesario en MicroPython estándar
    # ya que por defecto corre en un solo núcleo a menos que uses el módulo '_thread'.
    
    entrada_usuario = ""
    resultado_actual = ""
    ultimo_evento = time.time()
    
    actualizar_pantalla("PiCalc Ready")
    
    while True:
        boton = escanear_teclado()
        
        if boton:
            ultimo_evento = time.time() # Resetea el temporizador de inactividad
            
            if boton == "AC":
                entrada_usuario = ""
                resultado_actual = ""
                actualizar_pantalla("0")
            elif boton == "DEL":
                entrada_usuario = entrada_usuario[:-1]
                actualizar_pantalla(entrada_usuario if entrada_usuario else "0")
            elif boton == "IGUAL":
                if entrada_usuario:
                    resultado_actual = procesar_operacion(entrada_usuario)
                    actualizar_pantalla(entrada_usuario, resultado_actual)
            else:
                # Acumula el botón presionado en la cadena de entrada
                entrada_usuario += boton
                actualizar_pantalla(entrada_usuario)
                
        # --- CONTROL DE INACTIVIDAD (3 Minutos = 180 segundos) ---
        if time.time() - ultimo_evento > 180:
            if display:
                display.fill(0)
                display.show()
                display.sleep(True) # Apaga físicamente los píxeles del OLED para ahorrar
            
            # Pone al RP2040 en modo de bajo consumo hasta que se detecte una interrupción externa
            # Nota: Para despertar del modo Light Sleep o Dormant de forma eficiente en producción,
            # se suelen configurar interrupciones por hardware (IRQ) en los pines de las filas.
            machine.lightsleep() 
            
            # Al despertar:
            if display:
                display.sleep(False)
            ultimo_evento = time.time() # Resetea el contador al volver a activar

# Ejecutar el sistema
if __name__ == "__main__":
    iniciar_calculadora()

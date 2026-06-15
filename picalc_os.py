import time

# ==========================================
# 1. EMULACIÓN DEL HARDWARE
# ==========================================

# Simulamos el Modo Examen (Cambiá a False para probar el modo avanzado)
MODO_EXAMEN = True 

def actualizar_pantalla_simulada(linea1, linea2=""):
    """Simula la pantalla OLED dibujando un recuadro en la terminal."""
    print("\n" + "="*30)
    print(f"| PANTALLA OLED CASIO        |")
    print("-"*30)
    print(f"| EQ: {linea1:<22} |")
    print(f"| RES: {linea2:<21} |")
    print("="*30 + "\n")

# ==========================================
# 2. MOTOR MATEMÁTICO CON RESTRICCIONES
# ==========================================

def calcular_raiz(numero_str):
    try:
        valor = float(numero_str)
        if valor < 0:
            return "Error: Negativo"
        
        resultado_real = valor ** 0.5
        
        if MODO_EXAMEN:
            # Comportamiento tradicional exigido por la profe
            if resultado_real.is_integer():
                return str(int(resultado_real))
            else:
                return f"{resultado_real:.5f}"
        else:
            # Modo Avanzado (CAS)
            if resultado_real.is_integer():
                return f"Fact: {int(resultado_real)}"
            else:
                return f"Raiz({numero_str}) -> Simplificada"
                
    except ValueError:
        return "Error de Sintaxis"

def procesar_operacion(entrada):
    # Reemplazamos los comandos de los botones por operadores de Python
    ecuacion = entrada.upper().replace("MULT", "*").replace("DIV", "/").replace("MAS", "+").replace("MENOS", "-")
    
    try:
        if "RAIZ" in ecuacion:
            num = ecuacion.split("RAIZ")[-1]
            return calcular_raiz(num)
        
        resultado = eval(ecuacion)
        if isinstance(resultado, float) and resultado.is_integer():
            return str(int(resultado))
        return str(resultado)
    except Exception:
        return "Error"

# ==========================================
# 3. BUCLE PRINCIPAL (SIMULADO POR CONSOLA)
# ==========================================

def iniciar_simulacion():
    entrada_usuario = ""
    resultado_actual = ""
    
    actualizar_pantalla_simulada("PiCalc Ready", "Modo Examen: " + str(MODO_EXAMEN))
    
    print("INSTRUCCIONES DE COMENTARIOS:")
    print("- Escribí números u operaciones (ej: 5 MAS 5, 8 MULT 2)")
    print("- Para raíz escribí: RAIZ16 o RAIZ12")
    print("- Escribí 'IGUAL' para procesar, 'AC' para limpiar, o 'EXIT' para salir.\n")

    while True:
        # En la PC, simulamos el botón usando la entrada de texto de la consola
        accion = input("Presioná un botón (o tipea la acción): ").strip().upper()
        
        if accion == "EXIT":
            print("Simulación terminada.")
            break
        elif accion == "AC":
            entrada_usuario = ""
            resultado_actual = ""
            actualizar_pantalla_simulada("0")
        elif accion == "IGUAL":
            if entrada_usuario:
                resultado_actual = procesar_operacion(entrada_usuario)
                actualizar_pantalla_simulada(entrada_usuario, resultado_actual)
        else:
            # Acumula la entrada como si apretaras botones de la Casio
            entrada_usuario += accion
            actualizar_pantalla_simulada(entrada_usuario)

if __name__ == "__main__":
    iniciar_simulacion()

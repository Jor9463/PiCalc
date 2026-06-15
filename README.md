# PiCalc-Casio (Supercalculadora Científica para RP2040) 🔬

**PiCalc-Casio** es un proyecto de ingeniería inversa, electrónica Maker y desarrollo de software que transforma la carcasa, la membrana de gomas y la estética de una calculadora científica estándar (como la *Casio fx-82*) en una supercalculadora avanzada de alta potencia.

El corazón del proyecto es una **Raspberry Pi Pico (RP2040)** ejecutando **PiCalc OS**, un sistema operativo a medida programado íntegramente en **MicroPython**. El firmware replica la experiencia de usuario y la fidelidad de interfaz de una **Casio fx-991 ClassWiz**, incorporando un motor algebraico avanzado propio.

---

## 📜 Términos de Uso y Derechos de Autor (Licencia)

© 2026. Todos los derechos reservados.

Este proyecto se publica bajo un modelo de **Software Propietario de Uso Gratuito (Freeware)**. 
* **Permitido:** Se autoriza a cualquier usuario a descargar el código fuente, compilarlo, instalarlo y utilizarlo de forma estrictamente personal y gratuita en su propio hardware.
* **Prohibido:** Queda totalmente prohibida la modificación, alteración, bifurcación (forking) con fines de distribución, copia total o parcial del motor matemático para otros proyectos, y la comercialización o reventa de este software o de dispositivos que lo incluyan sin la autorización expresa del autor original.

---

## 📱 Descripción General e Idea Principal

El objetivo central es actualizar las limitaciones de cómputo del hardware escolar tradicional mediante hardware de bajo coste. Al interceptar los pads del teclado y añadir una pantalla OLED de alta resolución camuflada bajo un plástico polarizado gris, el dispositivo mantiene un aspecto exterior idéntico al original mientras despliega un motor algebraico avanzado que prescinde totalmente de la función insegura `eval()`.

### 🔐 El Módulo de Restricciones Académicas ("Modo Examen")
Para cumplir con las normativas escolares y de exámenes, el sistema integra variables globales de control (interruptores booleanos) que modifican por completo el comportamiento del motor matemático:
* **Modo Examen Activo (`True`):** Capa por completo las funciones de cálculo avanzado (sistemas de ecuaciones, cálculo matricial, derivadas, integrales y CAS), devolviendo únicamente resultados aritméticos tradicionales con decimales o enteros simples exigidos en el aula.
* **Modo Examen Desactivado (`False`):** Libera la potencia máxima del sistema (Cálculo analítico, complejos con cmath, simplificación de raíces, fracciones reducidas, etc.).
* **Indicador de Honestidad Visual:** Cuando el Modo Examen está activo, la pantalla muestra una marca de agua o código fijo en la esquina superior (ej. `[MODO R-1]`) para que el profesorado pueda verificar visualmente y a distancia que el alumno rinde bajo las reglas permitidas.

---

## 🛠️ Especificaciones de Hardware (BOM)

| Componente | Descripción | Notas de Integración |
| :--- | :--- | :--- |
| **Cerebro** | Placa compatible con **Raspberry Pi Pico** (RP2040). | 4MB de memoria Flash, puerto USB-C. Se usa sin los pines soldados para ahorrar espacio interno. |
| **Pantalla** | Módulo **OLED de 1.3"** I2C. | Controlador SH1106 o SSD1306 (128x64 píxeles). |
| **Camuflaje Visual** | Lámina de plástico polarizado gris o filtro difusor. | Colocada sobre el OLED para imitar el aspecto gris mate del LCD original apagado. |
| **Cableado** | Cable de cobre esmaltado ultra fino. | Reciclado del bobinado de un transformador de microondas para realizar conexiones internas sin obstruir las gomas del teclado. |
| **Alimentación** | Portapilas AAA original. | 2x pilas AAA en serie que entregan 3V directos conectados al pin `3V3` de la placa. |

---

## ⚡ Estrategia de Ingeniería Inversa (Bypass del Teclado)

Dado que las calculadoras modernas utilizan una lámina plástica flexible impresa que no tolera el calor del soldador, se interceptan las señales mediante **Bypass en la Placa Rígida Original**:
1. Se desuelda o raspa la alimentación del procesador nativo de la calculadora (la "gota de resina negra") para dejarlo inactivo y evitar interferencias eléctricas.
2. Los cables esmaltados ultra finos se sueldan directamente a las pistas de cobre expuestas de la placa rígida original (filas y columnas).
3. El otro extremo se redirige a los pines GPIO correspondientes de la Raspberry Pi Pico para realizar el escaneo matricial digital directo por software.

---

## 📈 Historial Completo de Desarrollo y Versiones

El firmware ha evolucionado a través de dos grandes etapas: la etapa de **Simulación Estructurada** (Betas y v1.0) y la etapa de **Motor de Tokens y Parsing Avanzado** (v3.0 a v4.3).

### 📐 Fase 1: Simulación Lineal y Bloqueo de Aula (Basados en Eval)

* **picalc_os_vBeta1 (El Concepto Base):**
    * Diseño troncal para la Raspberry Pi Pico con escáner matricial clásico utilizando resistencias *Pull-Down*.
    * Integración del driver gráfico para la pantalla `sh1106.py` mediante I2C.
    * Estrategia de energía: Timer de inactividad de 3 minutos que apaga los píxeles de la OLED y activa `machine.lightsleep()` reduciendo el consumo de batería a 0.2mA.
* **picalc_os_vBeta1.1 (Testeo Multiplataforma):**
    * Aislamiento de hardware mediante bloques `try-except` creando la **Dualidad de Entorno**: si detecta que corre en PC, deshabilita los pines físicos, simula la pantalla OLED dibujando un recuadro en la terminal y lee comandos desde el teclado de la computadora.
* **picalc_os_vBeta1.2 (Seguridad y Memorias):**
    * Inclusión de un atajo de combinación por software (`SHIFT79` al presionar `IGUAL`) para conmutar el `MODO_EXAMEN`.
    * Añadido sistema de almacenamiento en memoria rápida mediante variables asignables (`STO_A`, `STO_B`, `STO_X`, etc.).
* **picalc_os_vBeta1.3 / picalc.py (El Techo del Motor Lineal):**
    * Incorporación de álgebra elemental y cálculo numérico: **Solver de Newton-Raphson** para buscar incógnitas, resolución de sistemas lineales por regla de Cramer, integrales por Regla de Simpson (100 intervalos) y descomposición en factores primos (`PRIMOS`).
    * Implementación de algoritmos analíticos básicos: extracción de factores de raíces no exactas (ej: devuelve `2*v(3)` en vez de `3.46410`) y redondeo por fracciones continuas de hasta 5 cifras de denominador en modo libre.
* **picalc_os_v1.0 (Producción Escolar):**
    * Consolidación de la lógica lineal. Firmware blindado para el aula con tablas comparativas estrictas de lo permitido en Modo Examen vs Modo Avanzado.

---

### 🧠 Fase 2: El Motor de Arquitectura de Compiladores (Tokenización y RPN)

* **picalc_os_v3.0 / v3.0.1 (Adiós a Eval):**
    * **Reescritura completa desde cero:** Se desecha `eval()` por seguridad, estabilidad de memoria RAM y fidelidad.
    * Implementación del algoritmo de ordenación **Shunting-Yard (de Dijkstra)** para procesar texto infijo, convertirlo a Notación Polaca Inversa (RPN) y evaluarlo mediante pilas de forma analítica.
    * Estructura basada en **Tokens** independientes: funciones como `SIN(`, `COS(`, `MAT1(` se guardan como un único elemento. Al presionar la tecla `DEL`, se borra la estructura completa de un solo golpe (comportamiento idéntico a Casio).
    * Inclusión de un límite estricto de almacenamiento de listas estadísticas (`LIMITE_ESTADISTICA = 50`) para prevenir desbordamientos de la memoria Heap del chip RP2040.
* **picalc_os_v3.1 (Protección Eléctrica del GPIO):**
    * **FIX CRÍTICO DE HARDWARE:** Se rediseñó el método `escanear_teclado()`. Ahora, todos los pines de las filas se configuran en estado de **Alta Impedancia (Input)** en reposo. Al escanear, se conmuta una sola fila a la vez a `Output HIGH`. Esto previene cortocircuitos destructivos si el usuario presiona dos teclas de la misma columna simultáneamente.
    * Corrección del parser en el comando `SOLVE`, aislando los bloques `lhs` (izquierdo) y `rhs` (derecho) del signo `=` de manera segura sin romper los paréntesis internos.
* **picalc_os_v3.2 (Comportamiento de Fidelidad Casio):**
    * Cambio de la sintaxis y separador de argumentos de punto y coma (`;`) a coma (`,`) para adaptarse al layout de botones físico disponible en la carcasa (Fila 3, Columna 6).
    * Modificación lúdica al presionar `IGUAL`: si el cálculo arroja un `Error Sintaxis`, el buffer de tokens no se borra. La expresión inválida permanece en pantalla permitiendo al usuario corregir el error con el cursor, idéntico a las calculadoras comerciales.
* **picalc_os_v4.0 / v4.1 / v4.2 (Expansión Avanzada de Modos):**
    * **Módulo Complejo (CMPLX):** Integración nativa del módulo `cmath` de MicroPython cuando se activa el flag complejo. Entrada mediante el token de unidad imaginaria `i` (mapeado a `1j`) y formateo estricto de salida sin paréntesis tipo Python (ej: muestra `2+3i`, `-i`, `4-2i`).
    * **Módulo de Matrices (MAT):** Creación de almacenamiento persistente para `MatA`, `MatB` y `MatC` (hasta 4x4). Implementación de operaciones analíticas: multiplicación matricial con validación previa de dimensiones (`Error Dimension`), transposición, determinantes y matrices inversas.
    * **Filtro Anticolgaduras en Tablas (TABLE):** Se fijó un límite absoluto de 45 filas máximas en el modo tabla de valores. El sistema estima por software la cantidad de pasos calculados *antes* de iniciar las iteraciones matemáticas para evitar la congelación de la pantalla o el desborde de memoria RAM.
* **picalc_os_v4.3 (La Versión Actual - Interfaz Gráfica Dinámica):**
    * **Navegación por Cursor Real:** `ENTRADA_TOKENS` pasa de ser una lista estática a un buffer direccionable mediante un índice de cursor (`CURSOR_POS`). Las flechas de dirección mueven el cursor de forma fluida. Las inserciones de tokens y la acción de borrado (`DEL` actuando como backspace) se realizan exactamente en la posición del cursor (`|`).
    * **Scroll Horizontal Centrado:** El método de renderizado gráfico calcula dinámicamente la posición del cursor en caracteres y centra la vista de la pantalla OLED alrededor del cursor en lugar de fijar el extremo derecho.
    * **Menú MODE Fx-991 ClassWiz:** Al presionar la tecla `MODE`, la interfaz despliega el menú de cuadrícula icónico de la gama ClassWiz:
        ```text
        1:COMP    2:CMPLX   3:STAT   4:BASE-N
        5:EQN     6:MATRIX  7:TABLE  8:VECTOR
        ```
        Permite la selección rápida mediante flechas de navegación o por digitación directa del número de modo.

---

## 🚀 Cómo Empezar / Instalación

### En PC (Entorno de Depuración Rápida)
1. Descargá el archivo de la última versión estable (ubicado en `src/picalc_os_v4_3.py`).
2. Ejecutalo desde tu terminal favorita usando Python 3:
   ```bash
  python src/picalc_os_v4_3.py
3. Interactuá directamente tipeando los comandos. Podés tipear MODE para cambiar el estado global, usar las palabras clave de los alias para meter funciones y probar la velocidad del parser RPN.
### En Hardware Real (Raspberry Pi Pico)
1. Flasheá el firmware oficial de MicroPython en tu Raspberry Pi Pico.
2. Conectá el módulo OLED SH1106 a los pines I2C definidos en el script (SDA: GPIO 4, SCL: GPIO 5).
3. Cableá tu matriz de botones a los pines GPIO de Filas y Columnas configurados en la sección de hardware.
4. Cargá el script dentro de la memoria flash de la placa usando Thonny IDE y renombralo estrictamente como main.py para que se ejecute en bucle infinito de forma automática al recibir energía.
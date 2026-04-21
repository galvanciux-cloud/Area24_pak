# 📦 Area24 - Gestión y Logística de Paquetería

**Area24** es una aplicación de escritorio robusta desarrollada en Python para la administración de puntos de recogida y almacenes de paquetería. Permite un control total sobre la entrada de mercancía, asignación de ubicaciones físicas, facturación por compañía y análisis estadístico de rendimiento.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Interfaz](https://img.shields.io/badge/UI-Tkinter-orange.svg)
![Data](https://img.shields.io/badge/Análisis-Pandas-blue.svg)

## 🔥 Funcionalidades Clave

* **Registro Automatizado:** Entrada de paquetes con detección de fecha y hora automática.
* **Algoritmo de Precios:** Cálculo inteligente de ingresos basado en precios específicos por compañía (Amazon, GLS, Correos, etc.) y un precio base configurable.
* **Control de Ubicaciones:** Gestión de inventario físico mediante sistema de coordenadas (Ej: A1, B2, C3) para optimizar la búsqueda.
* **Dashboard Estadístico:** Gráficos dinámicos integrados con *Matplotlib* que muestran el flujo de paquetes diario del mes en curso.
* **Gestión de Manifiestos:** Historial detallado de todas las cargas procesadas.
* **Exportación de Datos:** Capacidad para procesar y listar datos mediante *Pandas*.

## 🛠️ Instalación

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/TU_USUARIO/area24-logistica.git](https://github.com/TU_USUARIO/area24-logistica.git)
    cd area24-logistica
    ```

2.  **Instalar las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Ejecutar la aplicación:**
    ```bash
    python Area24_pak.py
    ```

## 📊 Estructura Técnica

* **Base de Datos:** SQLite (`paquetes.db`) para un almacenamiento local ligero y fiable.
* **Interfaz Gráfica:** Tkinter con uso avanzado de `Treeview` para tablas y `FigureCanvasTkAgg` para los gráficos.
* **Lógica de Negocio:**
    * `config.json`: Permite personalizar ubicaciones y precios sin tocar el código.
    * Manejo de imágenes con `PIL` (Pillow) para la identidad visual.

## ⚙️ Configuración Personalizada

Puedes editar los precios y las estanterías disponibles directamente en el diccionario de configuración del script o mediante el archivo `config.json` generado:

```json
{
    "precio_base": 0.30,
    "ubicaciones": ["A1", "A2", "B1", "B2"],
    "precios_especiales": {
        "GLS": 0.35,
        "Amazon Logistics": 0.25
    }
}

Desarrollado por Pablo Galván García
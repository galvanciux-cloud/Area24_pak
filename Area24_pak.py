# autor: Pablo Galvan Garcia
# gestión de paquetes por nombre y ubicacíon.
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog
from datetime import datetime
import pandas as pd
import calendar
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import json
import logging
from PIL import Image, ImageTk
import os

# --- CONFIGURACIÓN INICIAL ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuración externa (fácil de modificar)
CONFIG = {
    "db_name": "paquetes.db",
    "precio_base": 0.30,
    "ubicaciones": ['A1', 'A2', 'A3', 'B1', 'B2', 'B3', 'C1', 'C2', 'C3'],
    "precios_especiales": {
        "Amazon Logistics": 0.25,
        "GLS": 0.35,
        "Correos": 0.30,
        "Kanguroo/PuntoPack": 0.30
    }
}

DB_NAME = CONFIG["db_name"]
UBICACIONES = CONFIG["ubicaciones"]
PRECIO_UNITARIO_PAQUETE = CONFIG["precio_base"]

# --- 1. CONFIGURACIÓN Y LÓGICA CENTRAL DE LA BASE DE DATOS ---

def get_db_connection():
    """Helper para conexiones seguras con row_factory."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
    return conn

def crear_db():
    """Crea las tablas e índices necesarios."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Tabla de Paquetes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS paquetes (
                tracking_id TEXT PRIMARY KEY COLLATE NOCASE,
                compania TEXT NOT NULL,
                destinatario TEXT NOT NULL COLLATE NOCASE,
                ubicacion TEXT NOT NULL,
                fecha_entrada TEXT NOT NULL,
                fecha_entrega TEXT,
                precio_generado REAL NOT NULL,
                estado TEXT NOT NULL CHECK(estado IN ('RECIBIDO', 'ENTREGADO'))
            )
        ''')
        
        # Tabla de Manifiestos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS manifiestos (
                nombre_archivo TEXT PRIMARY KEY,
                fecha_carga TEXT NOT NULL,
                paquetes_cargados INTEGER NOT NULL
            )
        ''')
        
        # Índices para búsquedas rápidas
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tracking ON paquetes(tracking_id COLLATE NOCASE)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_destinatario ON paquetes(destinatario COLLATE NOCASE)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_estado ON paquetes(estado)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fecha_entrada ON paquetes(fecha_entrada)')
        
        # Migración: Añadir 'fecha_entrega' si no existe (compatibilidad backwards)
        try:
            cursor.execute("SELECT fecha_entrega FROM paquetes LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Migrando base de datos: Añadiendo columna 'fecha_entrega'...")
            cursor.execute("ALTER TABLE paquetes ADD COLUMN fecha_entrega TEXT")

def identificar_compania(tracking_id):
    """Identifica la compañía por el formato del número de seguimiento."""
    if not tracking_id:
        return "Desconocida"
    tid = tracking_id.strip().upper()
    
    if len(tid) == 14 and tid.isdigit() and (tid.startswith('11') or tid.startswith('12')):
        return "GLS"
    if len(tid) == 13 and tid[0:2].isalpha() and tid[2:11].isdigit() and tid[11:13].isalpha():
        if tid.endswith('ES') or tid.startswith(('RR', 'PQ', 'CD')):
            return "Correos"
    if len(tid) in (17, 18) and tid.isdigit():
        return "Amazon Logistics"
    if len(tid) == 16 and tid.isdigit():
        return "Kanguroo/PuntoPack"
    return "Otras/Desconocida"

def registrar_paquete(tracking_id, destinatario, ubicacion, precio):
    """Inserta un paquete con estado 'RECIBIDO'."""
    tracking_id = tracking_id.strip().upper()  # ✅ Normalización
    compania = identificar_compania(tracking_id)
    fecha_entrada = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    estado = "RECIBIDO"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO paquetes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (tracking_id, compania, destinatario, ubicacion, fecha_entrada, None, precio, estado)
            )
            return True, f"✅ Registrado: {compania} para {destinatario} en **{ubicacion}**"
        except sqlite3.IntegrityError:
            return False, f"❌ ERROR: Paquete {tracking_id} ya registrado."

def marcar_como_entregado(tracking_id):
    """Actualiza el estado de un paquete a 'ENTREGADO'."""
    tracking_id = tracking_id.strip().upper()
    fecha_entrega = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE paquetes SET estado = 'ENTREGADO', fecha_entrega = ? WHERE tracking_id = ? AND estado = 'RECIBIDO'",
            (fecha_entrega, tracking_id)
        )
        if cursor.rowcount > 0:
            return True, "✅ Paquete marcado como entregado con éxito."
        else:
            return False, "❌ Paquete no encontrado o ya entregado."

def obtener_contadores_db():
    """Devuelve el total de paquetes recibidos (activos) y entregados."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        recibidos = cursor.execute("SELECT COUNT(*) FROM paquetes WHERE estado = 'RECIBIDO'").fetchone()[0]
        entregados = cursor.execute("SELECT COUNT(*) FROM paquetes WHERE estado = 'ENTREGADO'").fetchone()[0]
        return recibidos, entregados

def buscar_paquete_db(query):
    """Busca por Tracking ID o por Destinatario (case-insensitive)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tracking_id, compania, destinatario, ubicacion, estado, precio_generado, fecha_entrega "
            "FROM paquetes WHERE tracking_id = ? COLLATE NOCASE OR destinatario LIKE ? COLLATE NOCASE "
            "ORDER BY destinatario",
            (query.strip().upper(), f'%{query.strip()}%')
        )
        return cursor.fetchall()

def obtener_todos_los_paquetes_db(estado=None):
    """Recupera todos los paquetes, opcionalmente filtrando por estado."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if estado and estado in ('RECIBIDO', 'ENTREGADO'):
            cursor.execute(
                "SELECT tracking_id, compania, destinatario, ubicacion, estado, precio_generado, fecha_entrega "
                "FROM paquetes WHERE estado = ? ORDER BY ubicacion, destinatario",
                (estado,)
            )
        else:
            cursor.execute(
                "SELECT tracking_id, compania, destinatario, ubicacion, estado, precio_generado, fecha_entrega "
                "FROM paquetes ORDER BY ubicacion, destinatario"
            )
        return cursor.fetchall()

def actualizar_ubicacion_paquete(tracking_id, nueva_ubicacion):
    """Actualiza la ubicación de un paquete por su Tracking ID."""
    tracking_id = tracking_id.strip().upper()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE paquetes SET ubicacion = ? WHERE tracking_id = ?",
            (nueva_ubicacion, tracking_id)
        )
        return cursor.rowcount > 0

def guardar_manifiesto(nombre, num_paquetes):
    """Guarda un registro de manifiesto cargado."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO manifiestos VALUES (?, ?, ?)",
                (nombre, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), num_paquetes)
            )
        except sqlite3.IntegrityError:
            pass  # Ya existe → ignorar

def obtener_dashboard_data():
    """Recupera datos para el Dashboard (Gráfico y Total Generado)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        start_of_month = datetime.now().strftime("%Y-%m-01 00:00:00")
        
        # Paquetes recibidos por día
        recibidos_diarios = cursor.execute("""
            SELECT strftime('%d', fecha_entrada), COUNT(*)
            FROM paquetes
            WHERE fecha_entrada >= ?
            GROUP BY strftime('%d', fecha_entrada)
        """, (start_of_month,)).fetchall()
        
        # Total generado (solo entregados)
        total_generado = cursor.execute(
            "SELECT COALESCE(SUM(precio_generado), 0) FROM paquetes WHERE estado = 'ENTREGADO'"
        ).fetchone()[0]
        
        # Últimos manifiestos
        manifiestos_list = cursor.execute(
            "SELECT nombre_archivo, fecha_carga, paquetes_cargados "
            "FROM manifiestos ORDER BY fecha_carga DESC"
        ).fetchall()
        
        daily_data = {day: count for day, count in recibidos_diarios}
        return daily_data, float(total_generado), manifiestos_list

# --- 2. INTERFAZ GRÁFICA (TKINTER) ---

class GestorApp:
    def __init__(self, master):
        self.master = master
        master.title("📦 Gestor de Paquetes (V5 - Mejorado)")
        master.geometry("1200x800")
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

        style = ttk.Style()
        style.configure("Ubicacion.TButton", font=("Arial", 18, "bold"), padding=10)
        style.configure("Counter.TLabel", font=("Arial", 16, "bold"))
        style.configure("Entregado.TButton", foreground="white", background="#28a745")
        style.map("Entregado.TButton", background=[("active", "#218838")])
        
        crear_db()
        self.tracking_data = {} 

        self.notebook = ttk.Notebook(master)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        self.crear_pestana_registro()
        self.crear_pestana_busqueda()
        self.crear_pestana_entregados() 
        self.crear_pestana_carga()
        self.crear_pestana_dashboard()

        self.actualizar_contadores()

    def on_closing(self):
        if messagebox.askokcancel("Salir", "¿Deseas cerrar la aplicación?"):
            self.master.destroy()

    def on_tab_change(self, event):
        selected_tab = self.notebook.tab(self.notebook.select(), "text")
        if "DASHBOARD" in selected_tab:
            self.actualizar_dashboard()
        elif "REGISTRO" in selected_tab:
            self.entry_tracking_reg.focus()
        elif "ENTREGADOS" in selected_tab:
            self.mostrar_inventario_entregado()

    # === Diálogos personalizados con validación ===
    def _pedir_destinatario(self):
        dialog = tk.Toplevel(self.master)
        dialog.title("Introduce destinatario")
        dialog.geometry("400x120")
        dialog.transient(self.master)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Nombre del destinatario:").pack(pady=5)
        entry = ttk.Entry(dialog, font=("Arial", 14))
        entry.pack(pady=5, padx=20, fill="x")
        entry.focus()

        result = [None]
        
        def aceptar(event=None):
            val = entry.get().strip()
            if not val:
                messagebox.showwarning("Advertencia", "El nombre no puede estar vacío.", parent=dialog)
                return
            result[0] = val
            dialog.destroy()

        ttk.Button(dialog, text="Aceptar", command=aceptar).pack(pady=5)
        dialog.bind('<Return>', aceptar)
        dialog.bind('<Escape>', lambda e: dialog.destroy())
        
        self.master.wait_window(dialog)
        return result[0]

    def _pedir_precio(self, compania=None):
        dialog = tk.Toplevel(self.master)
        dialog.title("Precio del paquete")
        dialog.geometry("300x160")
        dialog.transient(self.master)
        dialog.grab_set()
        
        # Precio sugerido por compañía
        precio_sugerido = CONFIG["precios_especiales"].get(compania, PRECIO_UNITARIO_PAQUETE)
        var = tk.StringVar(value=f"{precio_sugerido:.2f}")
        
        ttk.Label(dialog, text=f"Precio (€) - {compania or 'Base'}:").pack(pady=5)
        entry = ttk.Entry(dialog, textvariable=var, font=("Arial", 14), justify="right")
        entry.pack(pady=5, padx=20, fill="x")
        entry.focus()

        result = [None]
        
        def aceptar(event=None):
            try:
                val = float(var.get().replace(',', '.'))
                if val <= 0:
                    raise ValueError
                result[0] = val
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Ingresa un número válido y positivo.", parent=dialog)
                entry.focus()

        btn = ttk.Button(dialog, text="Aceptar", command=aceptar)
        btn.pack(pady=5)
        dialog.bind('<Return>', aceptar)
        dialog.bind('<Escape>', lambda e: dialog.destroy())
        
        self.master.wait_window(dialog)
        return result[0]

    # --- PESTAÑA DE REGISTRO RÁPIDO ---
    def crear_pestana_registro(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="1. 📥 REGISTRO RÁPIDO")
        
        # Contadores
        counter_frame = ttk.Frame(tab, padding="10", relief=tk.RAISED)
        counter_frame.pack(fill="x", pady=5)
        self.lbl_recibidos = ttk.Label(counter_frame, text="📦 Activos: 0", style="Counter.TLabel", foreground="#007bff")
        self.lbl_recibidos.pack(side="left", padx=20)
        self.lbl_entregados = ttk.Label(counter_frame, text="✅ Entregados: 0", style="Counter.TLabel", foreground="#28a745")
        self.lbl_entregados.pack(side="left", padx=20)

        # Escaneo
        scan_frame = ttk.Frame(tab, padding="10")
        scan_frame.pack(fill="x")
        ttk.Label(scan_frame, text="ESCANEAR TRACKING ID:").pack(side="left", padx=5)
        self.entry_tracking_reg = ttk.Entry(scan_frame, width=30, font=("Arial", 14))
        self.entry_tracking_reg.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_tracking_reg.bind('<Return>', self.procesar_escaneo_registro)
        self.entry_tracking_reg.focus()

        # Datos Identificados
        info_frame = ttk.Frame(tab, padding="10")
        info_frame.pack(fill="x")
        self.lbl_compania = ttk.Label(info_frame, text="Compañía: --", font=("Arial", 14, "bold"))
        self.lbl_compania.pack(side="left", padx=10)
        self.lbl_destinatario = ttk.Label(info_frame, text="Destinatario: --", font=("Arial", 14))
        self.lbl_destinatario.pack(side="left", padx=10)
        self.lbl_ubicacion_predef = ttk.Label(info_frame, text="Ubicación Predef: --", font=("Arial", 14), foreground="orange")
        self.lbl_ubicacion_predef.pack(side="right", padx=10)

        # Ubicaciones (Botones Grandes)
        ubicacion_frame = ttk.Frame(tab, padding="20")
        ubicacion_frame.pack(expand=True, fill="both")
        
        for i, ubicacion in enumerate(UBICACIONES):
            row = i // 3
            col = i % 3
            btn = ttk.Button(ubicacion_frame, text=ubicacion, style="Ubicacion.TButton", 
                             command=lambda u=ubicacion: self.seleccionar_ubicacion(u))
            btn.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            ubicacion_frame.grid_columnconfigure(col, weight=1)
        for i in range(3):
            ubicacion_frame.grid_rowconfigure(i, weight=1)

        self.status_reg = ttk.Label(tab, text="Esperando escaneo...", relief=tk.SUNKEN, anchor="w", font=("Arial", 12))
        self.status_reg.pack(side="bottom", fill="x")

    def actualizar_contadores(self):
        recibidos, entregados = obtener_contadores_db()
        self.lbl_recibidos.config(text=f"📦 Activos: {recibidos}")
        self.lbl_entregados.config(text=f"✅ Entregados: {entregados}")

    def procesar_escaneo_registro(self, event):
        tracking_id = self.entry_tracking_reg.get().strip().upper()
        self.entry_tracking_reg.delete(0, tk.END)
        
        if not tracking_id:
            self.status_reg.config(text="❌ Escaneo vacío.")
            return

        compania = identificar_compania(tracking_id)
        
        data = self.tracking_data.get(tracking_id, ("DESTINATARIO NO ENCONTRADO (INTRODUCIR MANUAL)", "--"))
        destinatario = data[0]
        ubicacion_predef = data[1]

        self.lbl_compania.config(text=f"Compañía: {compania}")
        self.lbl_destinatario.config(text=f"Destinatario: {destinatario}")
        self.lbl_ubicacion_predef.config(text=f"Ubicación Predef: {ubicacion_predef}" if ubicacion_predef != "--" else "Ubicación Predef: --")
        
        self.current_tracking_id = tracking_id
        self.current_destinatario = destinatario
        self.current_ubicacion_predef = ubicacion_predef
        self.current_compania = compania

        self.status_reg.config(text="✅ Escaneo OK. ¡HAZ CLIC EN LA UBICACIÓN AHORA!")

    def seleccionar_ubicacion(self, ubicacion):
        if not hasattr(self, 'current_tracking_id'):
            self.status_reg.config(text="❌ Primero escanea un paquete.")
            return

        destinatario_final = self.current_destinatario
        if self.current_destinatario == "DESTINATARIO NO ENCONTRADO (INTRODUCIR MANUAL)":
            destinatario_final = self._pedir_destinatario()
            if not destinatario_final:
                self.status_reg.config(text="❌ Registro cancelado por falta de destinatario.", background="red", foreground="white")
                return
        
        precio = self._pedir_precio(self.current_compania)
        if precio is None:
            self.status_reg.config(text="❌ Registro cancelado por falta de precio.", background="red", foreground="white")
            return

        exito, mensaje = registrar_paquete(self.current_tracking_id, destinatario_final, ubicacion, precio)
        
        if exito:
            self.status_reg.config(text=mensaje, background="green", foreground="white")
            self.actualizar_contadores()
            
            # Limpiar datos
            for attr in ['current_tracking_id', 'current_destinatario', 'current_ubicacion_predef', 'current_compania']:
                if hasattr(self, attr):
                    delattr(self, attr)
            self.lbl_compania.config(text="Compañía: --")
            self.lbl_destinatario.config(text="Destinatario: --")
            self.lbl_ubicacion_predef.config(text="Ubicación Predef: --")
        else:
            self.status_reg.config(text=mensaje, background="red", foreground="white")
        
        self.entry_tracking_reg.focus()

    # --- PESTAÑA DE BÚSQUEDA / INVENTARIO ---
    def crear_pestana_busqueda(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="2. 🔍 BÚSQUEDA / INVENTARIO")

        # Input de búsqueda y botones de gestión
        search_frame = ttk.Frame(tab, padding="10")
        search_frame.pack(fill="x")
        ttk.Label(search_frame, text="Tracking ID o Nombre:").pack(side="left", padx=5)
        self.entry_busqueda = ttk.Entry(search_frame, width=30, font=("Arial", 14))
        self.entry_busqueda.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_busqueda.bind('<Return>', lambda e: self.ejecutar_busqueda())
        ttk.Button(search_frame, text="Buscar", command=self.ejecutar_busqueda).pack(side="left", padx=5)
        
        self.btn_asignar_ubicacion = ttk.Button(search_frame, text="📍 Asignar Ubicación", command=self.abrir_selector_ubicacion, state=tk.DISABLED)
        self.btn_asignar_ubicacion.pack(side="right", padx=5)
        
        self.btn_entregado = ttk.Button(search_frame, text="📦 Marcar como ENTREGADO", command=self.marcar_entregado_seleccionado, state=tk.DISABLED, style="Entregado.TButton")
        self.btn_entregado.pack(side="right", padx=5)
        
        ttk.Button(search_frame, text="Ver Inventario Completo", command=self.mostrar_inventario_completo).pack(side="right", padx=5)
        ttk.Button(search_frame, text="📥 Exportar CSV", command=self.exportar_inventario).pack(side="left", padx=5)

        # Resultado Principal
        result_frame = ttk.Frame(tab, padding="10")
        result_frame.pack(fill="x")
        
        self.lbl_resultado_ubi = ttk.Label(result_frame, text="Ubicación: ?", 
                                          font=("Arial", 50, "bold"), foreground="blue")
        self.lbl_resultado_ubi.pack(side="left", padx=20)
        
        self.lbl_resultado_det = ttk.Label(result_frame, text="Detalles:", font=("Arial", 14))
        self.lbl_resultado_det.pack(side="left", fill="x", expand=True)

        # Tabla de Resultados/Inventario Completo
        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(tab, columns=('id', 'compania', 'destinatario', 'ubicacion', 'estado', 'precio', 'entrega'), show='headings', yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree.yview)

        self.tree.heading('id', text='Tracking ID')
        self.tree.heading('compania', text='Compañía')
        self.tree.heading('destinatario', text='Destinatario')
        self.tree.heading('ubicacion', text='Ubicación')
        self.tree.heading('estado', text='Estado')
        self.tree.heading('precio', text='Precio (€)')
        self.tree.heading('entrega', text='F. Entrega')
        self.tree.column('id', width=150)
        self.tree.column('compania', width=120)
        self.tree.column('destinatario', width=150)
        self.tree.column('ubicacion', width=80, anchor='center')
        self.tree.column('estado', width=100, anchor='center')
        self.tree.column('precio', width=80, anchor='e')
        self.tree.column('entrega', width=120, anchor='center')
        
        # Estilos para estados
        self.tree.tag_configure('entregado', background='#e0f7fa', foreground='#006064')
        self.tree.tag_configure('activo', background='#e8f5e8', foreground='#1b5e20')

        scrollbar.pack(side='right', fill='y')
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        self.mostrar_inventario_completo()

    def on_tree_select(self, event):
        selected_item = self.tree.focus()
        self.btn_entregado.config(state=tk.DISABLED)
        self.btn_asignar_ubicacion.config(state=tk.DISABLED)
        
        if selected_item:
            values = self.tree.item(selected_item, 'values')
            if values and values[4] == 'RECIBIDO':
                self.btn_entregado.config(state=tk.NORMAL)
                self.btn_asignar_ubicacion.config(state=tk.NORMAL)

    def ejecutar_busqueda(self):
        query = self.entry_busqueda.get().strip()
        self.entry_busqueda.delete(0, tk.END)
        self.entry_busqueda.focus()

        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if not query:
            self.mostrar_inventario_completo()
            return

        resultados = buscar_paquete_db(query)
        
        if resultados:
            first = resultados[0]
            ubicacion = first[3]
            estado = first[4]
            fecha_entrega = first[6] if first[6] else '--'
            detalles = f"Compañía: {first[1]} | Cliente: {first[2]} | Estado: {estado}"
            
            color = "green" if estado == "RECIBIDO" else "blue"
            self.lbl_resultado_ubi.config(text=f"UBICACIÓN: {ubicacion}", foreground=color)
            self.lbl_resultado_det.config(text=detalles)
            
            for res in resultados:
                tag = 'activo' if res[4] == 'RECIBIDO' else 'entregado'
                self.tree.insert('', tk.END, values=(
                    res[0], res[1], res[2], res[3], res[4], f"{res[5]:.2f}", res[6] if res[6] else '--'
                ), tags=(tag,))
        else:
            self.lbl_resultado_ubi.config(text="NO ENCONTRADO", foreground="red")
            self.lbl_resultado_det.config(text="")
        
        self.btn_entregado.config(state=tk.DISABLED)
        self.btn_asignar_ubicacion.config(state=tk.DISABLED)

    def mostrar_inventario_completo(self):
        resultados = obtener_todos_los_paquetes_db()

        for item in self.tree.get_children():
            self.tree.delete(item)
            
        for res in resultados:
            tag = 'activo' if res[4] == 'RECIBIDO' else 'entregado'
            self.tree.insert('', tk.END, values=(
                res[0], res[1], res[2], res[3], res[4], f"{res[5]:.2f}", res[6] if res[6] else '--'
            ), tags=(tag,))
            
        self.lbl_resultado_ubi.config(text="INVENTARIO", foreground="gray")
        self.lbl_resultado_det.config(text=f"Total en DB: {len(resultados)} paquetes.")

    def marcar_entregado_seleccionado(self):
        selected_item = self.tree.focus()
        if not selected_item: return

        tracking_id = self.tree.item(selected_item, 'values')[0]
        
        if messagebox.askyesno("Confirmar Entrega", f"¿Confirmas la entrega del paquete {tracking_id}?", parent=self.master):
            exito, mensaje = marcar_como_entregado(tracking_id)
            if exito:
                messagebox.showinfo("Éxito", mensaje, parent=self.master)
                self.mostrar_inventario_completo()
                self.actualizar_contadores()
                self.btn_entregado.config(state=tk.DISABLED)
                self.btn_asignar_ubicacion.config(state=tk.DISABLED)
                try:
                    self.mostrar_inventario_entregado()
                except AttributeError:
                    pass
            else:
                messagebox.showerror("Error", mensaje, parent=self.master)

    def abrir_selector_ubicacion(self):
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showerror("Error", "Selecciona un paquete de la lista primero.", parent=self.master)
            return

        tracking_id = self.tree.item(selected_item, 'values')[0]
        current_ubi = self.tree.item(selected_item, 'values')[3]
        
        dialog = tk.Toplevel(self.master)
        dialog.title(f"📍 Asignar Ubicación a {tracking_id}")
        dialog.geometry("350x300")
        dialog.transient(self.master)
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"Paquete: {tracking_id}\nUbicación actual: {current_ubi}", font=("Arial", 12)).pack(pady=10)
        ttk.Label(dialog, text="Selecciona la nueva ubicación:", font=("Arial", 12, "bold")).pack(pady=5)
        
        ubicacion_frame = ttk.Frame(dialog)
        ubicacion_frame.pack(padx=10, pady=10)
        
        def asignar_y_cerrar(ubi):
            if actualizar_ubicacion_paquete(tracking_id, ubi):
                messagebox.showinfo("Éxito", f"Ubicación de {tracking_id} actualizada a {ubi}.", parent=dialog)
                self.mostrar_inventario_completo()
            else:
                messagebox.showerror("Error", "No se pudo actualizar la ubicación.", parent=dialog)
            dialog.destroy()

        for i, ubi in enumerate(UBICACIONES):
            row = i // 3
            col = i % 3
            btn = ttk.Button(ubicacion_frame, text=ubi, command=lambda u=ubi: asignar_y_cerrar(u))
            btn.grid(row=row, column=col, padx=5, pady=5)

    def exportar_inventario(self):
        from tkinter.filedialog import asksaveasfilename
        path = asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Guardar inventario como CSV"
        )
        if not path:
            return
        try:
            import csv
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Tracking ID', 'Compañía', 'Destinatario', 'Ubicación', 'Estado', 'Precio (€)', 'Fecha Entrega'])
                for item in self.tree.get_children():
                    writer.writerow(self.tree.item(item)['values'])
            messagebox.showinfo("Éxito", f"Inventario exportado a:\n{path}", parent=self.master)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar:\n{e}", parent=self.master)

    # --- NUEVA PESTAÑA: ENTREGADOS ---
    def crear_pestana_entregados(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="3. ✅ PAQUETES ENTREGADOS")
        
        self.lbl_entregados_info = ttk.Label(tab, text="Inventario de paquetes entregados:", font=("Arial", 14))
        self.lbl_entregados_info.pack(fill="x", pady=10, padx=10)

        # Botón de exportación
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(btn_frame, text="📥 Exportar CSV", command=self.exportar_entregados).pack(side="right")

        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL)
        self.tree_entregados = ttk.Treeview(tab, columns=('id', 'compania', 'destinatario', 'precio', 'entrega'), show='headings', yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree_entregados.yview)

        self.tree_entregados.heading('id', text='Tracking ID')
        self.tree_entregados.heading('compania', text='Compañía')
        self.tree_entregados.heading('destinatario', text='Destinatario')
        self.tree_entregados.heading('precio', text='Precio (€)')
        self.tree_entregados.heading('entrega', text='Fecha Entrega')
        
        self.tree_entregados.column('id', width=150)
        self.tree_entregados.column('compania', width=120)
        self.tree_entregados.column('destinatario', width=150)
        self.tree_entregados.column('precio', width=80, anchor='e')
        self.tree_entregados.column('entrega', width=140, anchor='center')
        
        # Estilo suave
        self.tree_entregados.tag_configure('entregado', background='#e0f7fa')
        
        scrollbar.pack(side='right', fill='y')
        self.tree_entregados.pack(fill="both", expand=True, padx=10, pady=10)

    def mostrar_inventario_entregado(self):
        for item in self.tree_entregados.get_children():
            self.tree_entregados.delete(item)
        
        resultados = obtener_todos_los_paquetes_db(estado='ENTREGADO')

        for res in resultados:
            self.tree_entregados.insert('', tk.END, values=(
                res[0], res[1], res[2], f"{res[5]:.2f}", res[6] if res[6] else '--'
            ), tags=('entregado',))
            
        self.lbl_entregados_info.config(text=f"Inventario de paquetes entregados. Total: {len(resultados)}.")

    def exportar_entregados(self):
        from tkinter.filedialog import asksaveasfilename
        path = asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Guardar entregados como CSV"
        )
        if not path:
            return
        try:
            import csv
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Tracking ID', 'Compañía', 'Destinatario', 'Precio (€)', 'Fecha Entrega'])
                for item in self.tree_entregados.get_children():
                    writer.writerow(self.tree_entregados.item(item)['values'])
            messagebox.showinfo("Éxito", f"Entregados exportados a:\n{path}", parent=self.master)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar:\n{e}", parent=self.master)

    # --- PESTAÑA DE CARGA DE MANIFIESTO ---
    def crear_pestana_carga(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="4. 📤 CARGA DE MANIFIESTO")
        
        ttk.Label(tab, text="Carga un Excel/CSV para pre-asignar destinatarios y ubicaciones.\nColumnas requeridas: 'tracking_id', 'destinatario'. Opcional: 'ubicacion'.", 
                  wraplength=700, justify="center").pack(pady=10, padx=10)
        ttk.Button(tab, text="📂 Cargar Archivo (CSV/Excel)", command=self.cargar_manifiesto).pack(pady=10)
        self.lbl_carga_status = ttk.Label(tab, text="Estado: No cargado", foreground="blue")
        self.lbl_carga_status.pack(pady=5)

    def cargar_manifiesto(self):
        from tkinter.filedialog import askopenfilename
        filepath = askopenfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx")]
        )
        if not filepath:
            return

        try:
            if filepath.endswith('.csv'):
                df = pd.read_csv(filepath, dtype=str)  # Evita pérdida de ceros a la izq
            elif filepath.endswith('.xlsx'):
                df = pd.read_excel(filepath, dtype=str)
            else:
                self.lbl_carga_status.config(text="❌ Error: formato de archivo no soportado.", foreground="red")
                return

            required_cols = {'tracking_id', 'destinatario'}
            if not required_cols.issubset(df.columns):
                missing = required_cols - set(df.columns)
                self.lbl_carga_status.config(text=f"❌ Error: Faltan columnas: {', '.join(missing)}", foreground="red")
                return

            self.tracking_data = {}
            insertados = 0
            ya_existentes = 0

            for _, row in df.iterrows():
                tid = str(row['tracking_id']).strip().upper()
                dest = str(row['destinatario']).strip()
                ubi = None
                if 'ubicacion' in row and pd.notna(row['ubicacion']):
                    val = str(row['ubicacion']).strip().upper()
                    ubi = val if val else None

                if not tid or not dest:
                    continue

                # Mantener en tracking_data para pre-asignación en registro rápido
                self.tracking_data[tid] = (dest, ubi if ubi else "--")

                # Preparar inserción en BD: usar ubicacion 'PENDIENTE' si no hay una válida
                ubicacion_para_bd = ubi if ubi else "PENDIENTE"

                # Determinar compañía y precio por defecto
                compania = identificar_compania(tid)
                precio_def = CONFIG["precios_especiales"].get(compania, PRECIO_UNITARIO_PAQUETE)

                # Intentar insertar en la BD; si ya existe, contar como existente
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    try:
                        cur.execute(
                            "INSERT INTO paquetes (tracking_id, compania, destinatario, ubicacion, fecha_entrada, fecha_entrega, precio_generado, estado) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (tid, compania, dest, ubicacion_para_bd, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), None, float(precio_def), "RECIBIDO")
                        )
                        insertados += 1
                    except sqlite3.IntegrityError:
                        ya_existentes += 1
                        # no hacemos nada, ya estaba en DB

            num_manifiesto = len(self.tracking_data)
            num_activos = obtener_contadores_db()[0]

            guardar_manifiesto(os.path.basename(filepath), num_manifiesto)

            self.lbl_carga_status.config(
                text=(f"✅ Manifiesto '{os.path.basename(filepath)}' cargado: {num_manifiesto} paquetes listos. "
                      f"Inserciones nuevas: {insertados}. Ya existentes: {ya_existentes}. "
                      f"Inventario activo ahora: {num_activos + insertados}"),
                foreground="green"
            )

            # Refrescar vistas si están abiertas
            try:
                self.mostrar_inventario_completo()
            except Exception:
                pass

        except Exception as e:
            logging.exception("Error al cargar manifiesto")
            self.lbl_carga_status.config(text=f"❌ Error al cargar: {e}", foreground="red")
            messagebox.showerror("Error de Carga", f"Ocurrió un error:\n{e}", parent=self.master)

    # --- PESTAÑA DASHBOARD ---
    def crear_pestana_dashboard(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="5. 📊 DASHBOARD")

        main_frame = ttk.Frame(tab, padding="10")
        main_frame.pack(fill="both", expand=True)

        left_frame = ttk.Frame(main_frame, width=350)
        left_frame.pack(side="left", fill="y", padx=10)
        left_frame.pack_propagate(False)

        ttk.Label(left_frame, text=f"Resumen de {datetime.now().strftime('%B %Y')}", 
                  font=("Arial", 16, "bold")).pack(pady=10)
        
        self.lbl_total_generado = ttk.Label(left_frame, text="💰 Generado (Entregas): 0.00 €", 
                                           font=("Arial", 14, "bold"), foreground="#17a2b8")
        self.lbl_total_generado.pack(pady=5)

        ttk.Label(left_frame, text="Manifiestos Cargados:", 
                  font=("Arial", 14, "underline")).pack(pady=15)
        self.manifiesto_tree = ttk.Treeview(left_frame, columns=('nombre', 'fecha', 'num'), show='headings', height=10)
        self.manifiesto_tree.heading('nombre', text='Archivo')
        self.manifiesto_tree.heading('fecha', text='Fecha Carga')
        self.manifiesto_tree.heading('num', text='Paquetes')
        self.manifiesto_tree.column('nombre', width=150)
        self.manifiesto_tree.column('fecha', width=120)
        self.manifiesto_tree.column('num', width=80, anchor='center')
        self.manifiesto_tree.pack(fill="x")

        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True)
        
        self.fig, self.ax = plt.subplots(figsize=(6, 5))
        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

    def actualizar_dashboard(self):
        daily_data, total_generado, manifiestos_list = obtener_dashboard_data()
        
        self.lbl_total_generado.config(text=f"💰 Generado (Entregas): {total_generado:.2f} €")
        
        for item in self.manifiesto_tree.get_children():
            self.manifiesto_tree.delete(item)
        for manifiesto in manifiestos_list:
            self.manifiesto_tree.insert('', tk.END, values=manifiesto)

        self.ax.clear()
        current_month_days = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
        dias_del_mes = [str(i).zfill(2) for i in range(1, current_month_days + 1)]
        paquetes_diarios = [daily_data.get(day, 0) for day in dias_del_mes]

        bars = self.ax.bar(dias_del_mes, paquetes_diarios, color='#007bff', edgecolor='white')
        self.ax.set_title("Paquetes Recibidos Diariamente (Mes Actual)", fontsize=12)
        self.ax.set_xlabel("Día del Mes")
        self.ax.set_ylabel("Nº Paquetes")
        self.ax.tick_params(axis='x', labelsize=8, rotation=45)
        self.ax.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Añadir valores encima de las barras (solo si > 0)
        for bar, count in zip(bars, paquetes_diarios):
            if count > 0:
                self.ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, 
                            str(count), ha='center', va='bottom', fontsize=8)
        
        self.fig.tight_layout()
        self.canvas.draw()

# --- 3. INICIO DE LA APLICACIÓN ---

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = GestorApp(root)
        root.mainloop()
    except Exception as e:
        logging.exception("Error fatal al iniciar la aplicación")
        messagebox.showerror("Error Fatal", f"Ocurrió un error inesperado:\n{e}")

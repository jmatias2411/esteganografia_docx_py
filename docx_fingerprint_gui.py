import os
import sys
import tempfile
import traceback
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Importamos directamente la versión oficial y mejorada
try:
    import docx_fingerprint as df
except ImportError:
    messagebox.showerror("Error Faltante", "No se encontró el archivo 'docx_fingerprint.py'. \nDebe estar en la misma carpeta que este ejecutable.")
    sys.exit(1)

# Función de apoyo para PyInstaller (rutas de assets)
def resource_path(relative_path):
    """Obtiene la ruta absoluta al recurso, funciona en dev e instalado como .exe"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class FingerprintGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🛡️ Sistema de Trazabilidad Documental (.docx)")
        self.geometry("750x550")
        self.minsize(700, 500)
        
        # Centrar la ventana principal
        self.center_window(750, 550)
        self.configure(bg="#eef2f5")

        # Configurar Estilos Modernos
        self.setup_styles()

        # Contenedor principal con padding
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Notebook (Pestañas)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        # Pestaña 1: Generar
        self.tab_encode = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.tab_encode, text=" 🔏 Generar Documento Marcado ")

        # Pestaña 2: Verificar
        self.tab_decode = ttk.Frame(self.notebook, padding=20)
        self.notebook.add(self.tab_decode, text=" 🔍 Auditar Documento ")

        # Construir Interfaces
        self.build_encode_tab()
        self.build_decode_tab()

    def center_window(self, width, height):
        """Centra la ventana en la pantalla del usuario."""
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = int((screen_width / 2) - (width / 2))
        y = int((screen_height / 2) - (height / 2) - 40) # Un poco más arriba del centro vertical
        self.geometry(f'{width}x{height}+{x}+{y}')

    def setup_styles(self):
        """Aplica estilos modernos simulando Flat Design dentro de lo posible en Tkinter."""
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        
        bg_color = "#eef2f5"
        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, font=("Segoe UI", 10), foreground="#333333")
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground="#1e3a8a", background=bg_color)
        
        style.configure("TButton", font=("Segoe UI", 10), padding=6, focuscolor=bg_color)
        
        # Botón Primario (Acción Principal)
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), background="#2563eb", foreground="white")
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")])

        # Botón Secundario
        style.configure("Secondary.TButton", font=("Segoe UI", 11, "bold"), background="#10b981", foreground="white")
        style.map("Secondary.TButton", background=[("active", "#059669"), ("pressed", "#047857")])

    def build_encode_tab(self):
        # Título
        ttk.Label(self.tab_encode, text="Proteger documento asignándolo a un destinatario", style="Header.TLabel").grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 20))

        # Campos
        ttk.Label(self.tab_encode, text="1. Documento Original (.docx):").grid(row=1, column=0, sticky='w', pady=(5, 5))
        self.enc_file_var = tk.StringVar()
        ttk.Entry(self.tab_encode, textvariable=self.enc_file_var, font=("Segoe UI", 10)).grid(row=1, column=1, padx=10, pady=(5, 5), sticky='ew')
        ttk.Button(self.tab_encode, text="Explorar...", command=self.browse_enc_file).grid(row=1, column=2, pady=(5, 5))
        
        ttk.Label(self.tab_encode, text="2. Destinatario (Responsable):").grid(row=2, column=0, sticky='w', pady=15)
        self.enc_name_var = tk.StringVar()
        ttk.Entry(self.tab_encode, textvariable=self.enc_name_var, font=("Segoe UI", 10)).grid(row=2, column=1, padx=10, pady=15, sticky='ew')
        
        ttk.Label(self.tab_encode, text="3. Guardar en (Dejar vacío para auto):").grid(row=3, column=0, sticky='w', pady=5)
        self.enc_out_var = tk.StringVar()
        ttk.Entry(self.tab_encode, textvariable=self.enc_out_var, font=("Segoe UI", 10)).grid(row=3, column=1, padx=10, pady=5, sticky='ew')
        ttk.Button(self.tab_encode, text="Explorar...", command=self.browse_enc_out).grid(row=3, column=2, pady=5)

        ttk.Label(self.tab_encode, text="4. Archivo de clave (.key):").grid(row=4, column=0, sticky='w', pady=5)
        self.enc_key_var = tk.StringVar(value=df.DEFAULT_KEY_FILE)
        ttk.Entry(self.tab_encode, textvariable=self.enc_key_var, font=("Segoe UI", 10)).grid(row=4, column=1, padx=10, pady=5, sticky='ew')
        ttk.Button(self.tab_encode, text="Explorar...", command=self.browse_enc_key).grid(row=4, column=2, pady=5)

        self.tab_encode.columnconfigure(1, weight=1)

        # Separador
        ttk.Separator(self.tab_encode, orient='horizontal').grid(row=5, column=0, columnspan=3, sticky='ew', pady=30)

        # Botón de Generar
        generate_btn = ttk.Button(self.tab_encode, text="🔐 Generar Documento Marcado", style="Primary.TButton", command=self.generate_doc, cursor="hand2")
        generate_btn.grid(row=6, column=0, columnspan=3, pady=10, ipadx=40, ipady=8)

        # Etiqueta de nota
        ttk.Label(self.tab_encode, text="El documento generado lucirá idéntico al original, pero contendrá\nuna huella dactilar microscópica e invisible.", justify="center", foreground="#6b7280").grid(row=7, column=0, columnspan=3, pady=10)

    def build_decode_tab(self):
        ttk.Label(self.tab_decode, text="Suba un documento Word sospechoso o filtrado para extraer su huella.", style="Header.TLabel").grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 20))

        ttk.Label(self.tab_decode, text="Documento a Examinar:").grid(row=1, column=0, sticky='w', pady=(5, 5))
        self.dec_file_var = tk.StringVar()
        ttk.Entry(self.tab_decode, textvariable=self.dec_file_var, font=("Segoe UI", 10)).grid(row=1, column=1, padx=10, pady=(5, 5), sticky='ew')
        ttk.Button(self.tab_decode, text="Explorar...", command=self.browse_dec_file).grid(row=1, column=2, pady=(5, 5))

        ttk.Label(self.tab_decode, text="Archivo de clave (.key):").grid(row=2, column=0, sticky='w', pady=5)
        self.dec_key_var = tk.StringVar(value=df.DEFAULT_KEY_FILE)
        ttk.Entry(self.tab_decode, textvariable=self.dec_key_var, font=("Segoe UI", 10)).grid(row=2, column=1, padx=10, pady=5, sticky='ew')
        ttk.Button(self.tab_decode, text="Explorar...", command=self.browse_dec_key).grid(row=2, column=2, pady=5)

        self.tab_decode.columnconfigure(1, weight=1)

        ttk.Button(self.tab_decode, text="🔍 Extraer Huella Dactilar", style="Secondary.TButton", command=self.analyze_doc, cursor="hand2").grid(row=3, column=0, columnspan=3, pady=25, ipadx=40, ipady=8)

        # Panel de Resultados (Scrollable Text)
        frame_result = ttk.Frame(self.tab_decode)
        frame_result.grid(row=4, column=0, columnspan=3, sticky='nsew')
        self.tab_decode.rowconfigure(4, weight=1)
        
        scrollbar = ttk.Scrollbar(frame_result)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.dec_result_text = tk.Text(frame_result, height=12, font=("Consolas", 10), state=tk.DISABLED, bg="#ffffff", fg="#1f2937", yscrollcommand=scrollbar.set, relief="flat", padx=10, pady=10)
        self.dec_result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.dec_result_text.yview)

    # Lógica de Interfaz y Archivos
    def browse_enc_file(self):
        filename = filedialog.askopenfilename(title="Seleccione docx origen", filetypes=[("Docx Original", "*.docx")])
        if filename:
            self.enc_file_var.set(filename)
            self.update_auto_output()

    def update_auto_output(self, event=None):
        filename = self.enc_file_var.get()
        name = self.enc_name_var.get()
        if filename and name and not self.enc_out_var.get():
            out = f"{Path(filename).stem}__{name.replace(' ', '_')}.docx"
            self.enc_out_var.set(os.path.join(os.path.dirname(filename), out))

    def browse_enc_out(self):
        filename = filedialog.asksaveasfilename(title="Guardar como...", defaultextension=".docx", filetypes=[("Documentos Word", "*.docx")])
        if filename:
            self.enc_out_var.set(filename)

    def browse_dec_file(self):
        filename = filedialog.askopenfilename(title="Seleccione docx a auditar", filetypes=[("Documentos Word", "*.docx")])
        if filename:
            self.dec_file_var.set(filename)

    def browse_enc_key(self):
        filename = filedialog.askopenfilename(title="Seleccionar archivo de clave", filetypes=[("Archivos de clave", "*.key"), ("Todos", "*.*")])
        if filename:
            self.enc_key_var.set(filename)

    def browse_dec_key(self):
        filename = filedialog.askopenfilename(title="Seleccionar archivo de clave", filetypes=[("Archivos de clave", "*.key"), ("Todos", "*.*")])
        if filename:
            self.dec_key_var.set(filename)

    def log_result(self, msg, clear=False):
        self.dec_result_text.config(state=tk.NORMAL)
        if clear:
            self.dec_result_text.delete(1.0, tk.END)
        self.dec_result_text.insert(tk.END, msg + "\n")
        self.dec_result_text.see(tk.END)
        self.dec_result_text.config(state=tk.DISABLED)

    # Funciones Core (Llamadas a docx_fingerprint.py)
    def generate_doc(self):
        docx_path = self.enc_file_var.get()
        name = self.enc_name_var.get().strip()
        output_path = self.enc_out_var.get()
        key_path = self.enc_key_var.get().strip() or df.DEFAULT_KEY_FILE

        if not docx_path or not os.path.exists(docx_path):
            messagebox.showwarning("Atención", "Por favor seleccione un documento válido.")
            return

        if not name:
            messagebox.showwarning("Atención", "Debe ingresar el nombre del responsable del documento.")
            return

        if not output_path:
            output_path = os.path.join(
                os.path.dirname(docx_path),
                f"{Path(docx_path).stem}__{name.replace(' ', '_')}.docx"
            )

        try:
            key = df.load_or_create_key(key_path)
            entry = df.encode_document(docx_path, name, output_path, key)
            df.register_fingerprint_v2(entry)

            messagebox.showinfo(
                "¡Generado con Éxito!",
                f"El archivo se ha sellado de forma invisible y guardado.\n\n"
                f"Responsable: {name}\n"
                f"Ubicación: {output_path}\n"
                f"Capas: {', '.join(entry['layers_injected'])}\n"
                f"HMAC: {entry['payload_hmac']}"
            )

            self.enc_file_var.set("")
            self.enc_name_var.set("")
            self.enc_out_var.set("")

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error Crítico", f"Ocurrió un fallo de sistema:\n{str(e)}")

    def analyze_doc(self):
        docx_path = self.dec_file_var.get()
        key_path = self.dec_key_var.get().strip() or df.DEFAULT_KEY_FILE

        if not docx_path or not os.path.exists(docx_path):
            messagebox.showwarning("Atención", "Busque y seleccione el documento para examinar.")
            return

        self.log_result("============== ANÁLISIS FORENSE ==============", clear=True)
        self.log_result(f"Cargando archivo: {os.path.basename(docx_path)}")

        try:
            if os.path.exists(key_path):
                key = df.load_or_create_key(key_path)
            else:
                key = b"\x00" * 32  # fallback legacy

            result = df.decode_document(docx_path, key)

            if result:
                integrity = ""
                if result["doc_intact"] is True:
                    integrity = "✅ Contenido íntegro"
                elif result["doc_intact"] is False:
                    integrity = "⚠️  CONTENIDO MODIFICADO desde el envío"
                else:
                    integrity = "(documento v1 — verificación no disponible)"

                msg = "\n🎯 ¡HUELLA INVISIBLE ENCONTRADA!\n"
                msg += "=" * 40 + "\n"
                msg += f"👉 Destinatario   : {result['recipient']}\n"
                if result["timestamp"]:
                    msg += f"📅 Fecha de envío : {result['timestamp'][:19].replace('T', ' ')}\n"
                msg += f"🔒 Capa detectada : {result['layer_used']}\n"
                msg += f"📄 Integridad     : {integrity}\n"
                msg += "=" * 40 + "\n"

                registry = df.load_registry()
                matches = [e for e in registry.get("fingerprints", []) if e["recipient"].lower() == result["recipient"].lower()]
                if matches:
                    msg += f"\n📋 Registros locales ({len(matches)}):\n"
                    for i, m in enumerate(matches, 1):
                        msg += f"  #{i}: {os.path.basename(m['output_file'])}  [{m['timestamp'][:19].replace('T', ' ')}]\n"
                else:
                    msg += f"\n⚠️  Sin registro local para '{result['recipient']}'.\n"

                self.log_result(msg)
                messagebox.showwarning("¡Marcador Positivo!", f"Documento perteneciente a:\n\n{result['recipient']}")
            else:
                self.log_result("\n[X] No se encontraron marcadores invisibles.")
                self.log_result("    El documento puede estar limpio o su estructura fue reescrita.")
                messagebox.showinfo("Resultados", "Auditoría terminada. Documento limpio.")

        except Exception as e:
            traceback.print_exc()
            self.log_result(f"\n[!] ERROR DE AUDITORÍA: {str(e)}")
            messagebox.showerror("Error", f"Fallo al escanear archivo:\n{str(e)}")

if __name__ == "__main__":
    app = FingerprintGUI()
    # Atar el evento 'keyup' del nombre para mostrar el autocompletar de ruta
    app.enc_name_var.trace_add("write", lambda *args: app.update_auto_output())
    app.mainloop()

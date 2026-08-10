import sqlite3
import os
import sys
import traceback
import re
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import threading
import json

class DBManager:
    def __init__(self, db_name="pelizone.db"):
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.getcwd()

        self.db_path = os.path.join(self.base_dir, db_name)
        
        # =======================================================
        # SOPORTE PARA RENDER / VARIABLES DE ENTORNO EN LA NUBE
        # =======================================================
        if "GOOGLE_CREDENTIALS_JSON" in os.environ:
            try:
                env_creds_path = os.path.join(self.base_dir, "credentials.json")
                with open(env_creds_path, "w") as f:
                    f.write(os.environ["GOOGLE_CREDENTIALS_JSON"])
                print("☁️ credentials.json creado exitosamente desde la variable de entorno de Render.")
            except Exception as e:
                print(f"⚠️ Error al crear credentials.json desde el entorno: {e}")
        # =======================================================

        self.creds_path = self._resolver_ruta_credenciales()

        self._create_tables()
        self.limpiar_clientes_vencidos()

        self.scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        self.sheet_id = "1CFvQZ-kpNt6TXo6ttJWwbLQz4URh4NqLhgjaHl3cZto"
        self.hoja_clientes = None
        self.hoja_usuarios = None

        self._sheets_ready = threading.Event()
        self._sync_lock = threading.Lock()

        # Conexión inicial en segundo plano
        threading.Thread(target=self.conectar_google_sheets, daemon=True).start()

    def _resolver_ruta_credenciales(self, nombre="credentials.json"):
        candidatos = [
            os.path.join(self.base_dir, nombre),
            os.path.join(self.base_dir, "_internal", nombre),
            os.path.join(os.path.dirname(self.base_dir), nombre),
        ]
        for ruta in candidatos:
            if os.path.exists(ruta):
                return ruta
        return candidatos[0]

    def conectar_google_sheets(self):
        try:
            if not os.path.exists(self.creds_path):
                print(f"❌ Archivo credentials.json NO encontrado en: {self.creds_path}")
                return

            creds = Credentials.from_service_account_file(self.creds_path, scopes=self.scopes)
            cliente_gspread = gspread.authorize(creds)
            archivo = cliente_gspread.open_by_key(self.sheet_id)
            
            # Hoja 1 para Clientes
            self.hoja_clientes = archivo.sheet1

            # Hoja para Usuarios (la busca o la crea automáticamente si no existe)
            try:
                self.hoja_usuarios = archivo.worksheet("Usuarios")
            except gspread.exceptions.WorksheetNotFound:
                self.hoja_usuarios = archivo.add_worksheet(title="Usuarios", rows="100", cols="4")
                self.hoja_usuarios.append_row(["Usuario", "Clave", "Rol", "Tienda Asignada"])

            print("✅ Conectado a Google Sheets (Clientes y Usuarios) exitosamente.")

            # Sincronización automática de ambas tablas apenas conecta
            self.sincronizar_desde_google_sheets()
            self.sincronizar_usuarios_desde_google_sheets()
        except Exception as e:
            print(f"❌ Error conectando a Google Sheets: {e}")
            traceback.print_exc()
        finally:
            self._sheets_ready.set()

    def cambiar_hoja_id(self, nuevo_id: str):
        self.sheet_id = nuevo_id
        self._sheets_ready.clear()
        threading.Thread(target=self.conectar_google_sheets, daemon=True).start()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("PRAGMA table_info(usuarios)")
                columnas = [col[1] for col in cursor.fetchall()]
                if "correo" in columnas:
                    cursor.execute("DROP TABLE usuarios")
            except Exception as e:
                print(f"⚠️ Error verificando/migrando tabla usuarios: {e}")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS clientes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    telefono TEXT NOT NULL,
                    tienda TEXT NOT NULL,
                    fecha_compra DATE NOT NULL,
                    fecha_renovacion DATE NOT NULL,
                    estado TEXT DEFAULT 'Activo',
                    observaciones TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cliente_id INTEGER,
                    fecha_accion DATE,
                    accion TEXT,
                    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tiendas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    clave TEXT NOT NULL,
                    rol TEXT NOT NULL, 
                    tienda_asignada TEXT
                )
            ''')
            
            cursor.execute("SELECT COUNT(*) FROM tiendas")
            if cursor.fetchone()[0] == 0:
                cursor.executemany("INSERT INTO tiendas (nombre) VALUES (?)", [("STREAMSHOP",), ("PELIZONE",)])
            
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO usuarios (usuario, clave, rol, tienda_asignada) 
                    VALUES (?, ?, ?, ?)
                ''', ("tecnoplay", "2006", "admin", "Todas"))
            
            conn.commit()

    def limpiar_telefono(self, telefono_str: str) -> str:
        if not telefono_str or str(telefono_str).strip().lower() == "sin número":
            return "Sin número"
        
        digitos = re.sub(r'\D', '', str(telefono_str))
        
        if len(digitos) == 12 and digitos.startswith('57'):
            digitos = digitos[2:]
            
        return digitos if digitos else "Sin número"

    def sincronizar_desde_google_sheets(self):
        if not self.hoja_clientes:
            return False

        with self._sync_lock:
            try:
                filas = self.hoja_clientes.get_all_values()
                if len(filas) <= 1:
                    return True

                insertados = 0
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    for i, fila in enumerate(filas[1:], start=2):
                        if len(fila) < 5:
                            continue
                        nombre, telefono, tienda, f_compra_ui, f_renov_ui = fila[0].strip(), fila[1].strip(), fila[2].strip(), fila[3].strip(), fila[4].strip()
                        
                        telefono = self.limpiar_telefono(telefono)

                        try:
                            f_compra_iso = datetime.strptime(f_compra_ui, "%d/%m/%Y").strftime("%Y-%m-%d")
                            f_renov_iso = datetime.strptime(f_renov_ui, "%d/%m/%Y").strftime("%Y-%m-%d")
                        except ValueError:
                            continue 

                        cursor.execute('''
                            SELECT id FROM clientes 
                            WHERE nombre = ? AND telefono = ? AND tienda = ? AND fecha_renovacion = ?
                        ''', (nombre, telefono, tienda, f_renov_iso))
                        
                        if not cursor.fetchone():
                            cursor.execute('''
                                INSERT INTO clientes (nombre, telefono, tienda, fecha_compra, fecha_renovacion, estado, observaciones)
                                VALUES (?, ?, ?, ?, ?, 'Activo', '')
                            ''', (nombre, telefono, tienda, f_compra_iso, f_renov_iso))
                            insertados += 1
                    conn.commit()
                print(f"🔄 Sincronización de clientes completada. Nuevos: {insertados}.")
                return True
            except Exception as e:
                print(f"❌ Error al sincronizar clientes: {e}")
                return False

    def sincronizar_usuarios_desde_google_sheets(self):
        if not self.hoja_usuarios:
            return
        try:
            filas = self.hoja_usuarios.get_all_values()
            if len(filas) <= 1:
                return

            with self.get_connection() as conn:
                cursor = conn.cursor()
                usuarios_nuevos = 0
                for fila in filas[1:]:
                    if len(fila) < 4:
                        continue
                    usuario, clave, rol, tienda_asignada = fila[0].strip(), fila[1].strip(), fila[2].strip(), fila[3].strip()

                    cursor.execute("SELECT id FROM usuarios WHERE usuario = ?", (usuario,))
                    if not cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO usuarios (usuario, clave, rol, tienda_asignada)
                            VALUES (?, ?, ?, ?)
                        ''', (usuario, clave, rol, tienda_asignada))
                        usuarios_nuevos += 1
                conn.commit()
            print(f"🔄 Sincronización de usuarios completada. Nuevos en SQLite: {usuarios_nuevos}.")
        except Exception as e:
            print(f"⚠️ Error sincronizando usuarios desde la nube: {e}")

    def limpiar_clientes_vencidos(self):
        hoy = datetime.now()
        limite_sin_numero = (hoy - timedelta(days=5)).strftime("%Y-%m-%d")
        limite_con_numero = (hoy - timedelta(days=150)).strftime("%Y-%m-%d")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM clientes WHERE telefono = "Sin número" AND fecha_renovacion < ?', (limite_sin_numero,))
            cursor.execute('DELETE FROM clientes WHERE telefono != "Sin número" AND fecha_renovacion < ?', (limite_con_numero,))
            conn.commit()

    def verificar_login(self, usuario: str, clave: str):
        if self.hoja_usuarios:
            self.sincronizar_usuarios_desde_google_sheets()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT usuario, rol, tienda_asignada FROM usuarios WHERE usuario = ? AND clave = ?", (usuario, clave))
            user = cursor.fetchone()
            if user:
                return True, {"usuario": user[0], "rol": user[1], "tienda_asignada": user[2]}
            return False, "Usuario o contraseña incorrectos"

    def crear_usuario(self, usuario: str, clave: str, rol: str, tienda_asignada: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO usuarios (usuario, clave, rol, tienda_asignada) VALUES (?, ?, ?, ?)", 
                               (usuario, clave, rol, tienda_asignada))
                conn.commit()
                
                datos_usuario = [usuario, clave, rol, tienda_asignada]
                threading.Thread(target=self._respaldar_usuario_en_nube, args=(datos_usuario,), daemon=True).start()

                return True, "Usuario creado exitosamente"
            except sqlite3.IntegrityError:
                return False, "El nombre de usuario ya está registrado"

    def _respaldar_usuario_en_nube(self, datos_fila):
        if self.hoja_usuarios:
            try:
                self.hoja_usuarios.append_row(datos_fila)
                print("☁️ Usuario respaldado en Google Sheets con éxito.")
            except Exception as e:
                print(f"❌ Error respaldando usuario en Google Sheets: {e}")

    def obtener_tiendas(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre FROM tiendas")
            return [row[0] for row in cursor.fetchall()]

    def agregar_tienda(self, nombre_tienda: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO tiendas (nombre) VALUES (?)", (nombre_tienda.upper(),))
                conn.commit()
                return True, "Tienda agregada exitosamente"
            except sqlite3.IntegrityError:
                return False, "La tienda ya existe"

    def _registrar_historial(self, cursor, cliente_id: int, fecha: str, accion: str):
        cursor.execute('INSERT INTO historial (cliente_id, fecha_accion, accion) VALUES (?, ?, ?)', (cliente_id, fecha, accion))

    def registrar_cliente(self, nombre: str, telefono: str, tienda: str, fecha_compra_ui: str, observaciones: str = ""):
        telefono = self.limpiar_telefono(telefono)
        
        fecha_obj = datetime.strptime(fecha_compra_ui, "%d/%m/%Y")
        fecha_compra_iso = fecha_obj.strftime("%Y-%m-%d")
        fecha_renovacion_iso = (fecha_obj + timedelta(days=30)).strftime("%Y-%m-%d")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO clientes (nombre, telefono, tienda, fecha_compra, fecha_renovacion, observaciones)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (nombre, telefono, tienda, fecha_compra_iso, fecha_renovacion_iso, observaciones))
            
            cliente_id = cursor.lastrowid
            self._registrar_historial(cursor, cliente_id, fecha_compra_iso, "Registro Inicial")
            conn.commit()

        datos_fila = [nombre, telefono, tienda, fecha_compra_ui, datetime.strptime(fecha_renovacion_iso, "%Y-%m-%d").strftime("%d/%m/%Y"), "Nuevo", observaciones]
        threading.Thread(target=self._respaldar_en_nube, args=(datos_fila,), daemon=True).start()

    def registrar_clientes_masivo(self, clientes_lista: list):
        datos_para_sheets = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for cli in clientes_lista:
                nombre, telefono, tienda, fecha_compra_ui = cli
                
                telefono = self.limpiar_telefono(telefono)
                
                fecha_obj = datetime.strptime(fecha_compra_ui, "%d/%m/%Y")
                fecha_compra_iso = fecha_obj.strftime("%Y-%m-%d")
                fecha_renovacion_iso = (fecha_obj + timedelta(days=30)).strftime("%Y-%m-%d")
                
                cursor.execute('''
                    INSERT INTO clientes (nombre, telefono, tienda, fecha_compra, fecha_renovacion, observaciones)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (nombre, telefono, tienda, fecha_compra_iso, fecha_renovacion_iso, ""))
                
                cliente_id = cursor.lastrowid
                self._registrar_historial(cursor, cliente_id, fecha_compra_iso, "Registro Inicial Masivo")
                
                fecha_renovacion_ui = datetime.strptime(fecha_renovacion_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
                datos_para_sheets.append([nombre, telefono, tienda, fecha_compra_ui, fecha_renovacion_ui, "Nuevo", ""])
            conn.commit()

        if self.hoja_clientes and datos_para_sheets:
            threading.Thread(target=self._respaldar_masivo_en_nube, args=(datos_para_sheets,), daemon=True).start()

    def obtener_clientes_por_renovar(self, tienda_filtro=None, tiempo_espera_conexion=8):
        self._sheets_ready.wait(timeout=tiempo_espera_conexion)

        if self.hoja_clientes:
            self.sincronizar_desde_google_sheets()

        hoy_iso = datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if tienda_filtro and tienda_filtro != "Todas":
                cursor.execute('''
                    SELECT id, nombre, telefono, tienda, fecha_compra, fecha_renovacion 
                    FROM clientes 
                    WHERE fecha_renovacion = ? AND estado = 'Activo' AND tienda = ?
                ''', (hoy_iso, tienda_filtro))
            else:
                cursor.execute('''
                    SELECT id, nombre, telefono, tienda, fecha_compra, fecha_renovacion 
                    FROM clientes 
                    WHERE fecha_renovacion = ? AND estado = 'Activo'
                ''', (hoy_iso,))
            
            resultados = cursor.fetchall()
            clientes_formateados = []
            for c in resultados:
                f_comp_ui = datetime.strptime(c[4], "%Y-%m-%d").strftime("%d/%m/%Y")
                f_renov_ui = datetime.strptime(c[5], "%Y-%m-%d").strftime("%d/%m/%Y")
                clientes_formateados.append((c[0], c[1], c[2], c[3], f_comp_ui, f_renov_ui))
                
            return clientes_formateados

    def eliminar_cliente(self, cliente_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
            conn.commit()

    def renovar_cliente(self, cliente_id: int):
        hoy_obj = datetime.now()
        hoy_iso = hoy_obj.strftime("%Y-%m-%d")
        nueva_renovacion_iso = (hoy_obj + timedelta(days=30)).strftime("%Y-%m-%d")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre, telefono, tienda FROM clientes WHERE id = ?", (cliente_id,))
            cli = cursor.fetchone()
            if not cli: return
            nombre, telefono, tienda = cli

            cursor.execute('''
                UPDATE clientes 
                SET fecha_compra = ?, fecha_renovacion = ?
                WHERE id = ?
            ''', (hoy_iso, nueva_renovacion_iso, cliente_id))
            
            self._registrar_historial(cursor, cliente_id, hoy_iso, "Renovación 30 días")
            conn.commit()

        hoy_ui = hoy_obj.strftime("%d/%m/%Y")
        nueva_renovacion_ui = (hoy_obj + timedelta(days=30)).strftime("%d/%m/%Y")
        datos_fila = [nombre, telefono, tienda, hoy_ui, nueva_renovacion_ui, "Renovado", "Renovación automática"]
        threading.Thread(target=self._respaldar_en_nube, args=(datos_fila,), daemon=True).start()

    def renovar_por_telefono(self, telefono_buscar: str, tienda_filtro=None):
        telefono_buscar = self.limpiar_telefono(telefono_buscar)
        
        hoy_obj = datetime.now()
        hoy_iso = hoy_obj.strftime("%Y-%m-%d")
        nueva_renovacion_iso = (hoy_obj + timedelta(days=30)).strftime("%Y-%m-%d")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if tienda_filtro and tienda_filtro != "Todas":
                cursor.execute('''
                    SELECT id, nombre, tienda 
                    FROM clientes 
                    WHERE telefono = ? AND estado = 'Activo' AND tienda = ?
                    ORDER BY id DESC LIMIT 1
                ''', (telefono_buscar, tienda_filtro))
            else:
                cursor.execute('''
                    SELECT id, nombre, tienda 
                    FROM clientes 
                    WHERE telefono = ? AND estado = 'Activo' 
                    ORDER BY id DESC LIMIT 1
                ''', (telefono_buscar,))
            
            cli = cursor.fetchone()
            if not cli:
                return False, "Número no encontrado o no pertenece a tu tienda."
                
            cliente_id, nombre, tienda = cli

            cursor.execute('''
                UPDATE clientes 
                SET fecha_compra = ?, fecha_renovacion = ?
                WHERE id = ?
            ''', (hoy_iso, nueva_renovacion_iso, cliente_id))
            self._registrar_historial(cursor, cliente_id, hoy_iso, "Renovación Rápida por Teléfono")
            conn.commit()

        hoy_ui = hoy_obj.strftime("%d/%m/%Y")
        nueva_renovacion_ui = (hoy_obj + timedelta(days=30)).strftime("%d/%m/%Y")
        datos_fila = [nombre, telefono_buscar, tienda, hoy_ui, nueva_renovacion_ui, "Renovado", "Renovación Rápida"]
        threading.Thread(target=self._respaldar_en_nube, args=(datos_fila,), daemon=True).start()
        return True, nombre

    def _respaldar_en_nube(self, datos_fila):
        if self.hoja_clientes:
            try:
                self.hoja_clientes.append_row(datos_fila)
                print("☁️ Cliente respaldado en Google Sheets.")
            except Exception as e:
                print(f"❌ Error respaldando en Google Sheets: {e}")

    def _respaldar_masivo_en_nube(self, datos_matriz):
        if not self.hoja_clientes:
            print("⚠️ Respaldo masivo omitido.")
            return
        try:
            self.hoja_clientes.append_rows(datos_matriz)
            print(f"☁️ {len(datos_matriz)} clientes respaldados masivamente.")
        except Exception as e:
            print(f"❌ Error en respaldo masivo: {e}")
import flet as ft
import re
from datetime import datetime
from database.db_manager import DBManager
# Importamos utilidades de WhatsApp y formato
from core.utils import generar_mensaje_renovacion, limpiar_numero_whatsapp, generar_mensaje_rapido, generar_enlace_whatsapp_seguro

class ClientView(ft.Container):
    def __init__(self, db: DBManager, page: ft.Page, usuario_actual: dict = None):
        super().__init__()
        self.db = db
        self.main_page = page 
        self.expand = True
        
        # Si no se pasa usuario (por seguridad), asume un Admin por defecto
        self.usuario = usuario_actual or {"rol": "admin", "tienda_asignada": "Todas"}
        
        # ==========================================
        # LÓGICA DE TIENDAS DINÁMICAS Y PERMISOS
        # ==========================================
        todas_las_tiendas = self.db.obtener_tiendas()
        
        if self.usuario["tienda_asignada"] != "Todas":
            opciones_tienda = [ft.dropdown.Option(self.usuario["tienda_asignada"])]
            opciones_filtro = [ft.dropdown.Option(self.usuario["tienda_asignada"])]
            val_defecto = self.usuario["tienda_asignada"]
            val_filtro = self.usuario["tienda_asignada"]
        else:
            opciones_tienda = [ft.dropdown.Option(t) for t in todas_las_tiendas]
            opciones_filtro = [ft.dropdown.Option("Todas")] + [ft.dropdown.Option(t) for t in todas_las_tiendas]
            val_defecto = opciones_tienda[0].key if opciones_tienda else ""
            val_filtro = "Todas"

        # ==========================================
        # CONTROLES DE INTERFAZ INTELIGENTES
        # ==========================================
        self.tf_nombre = ft.TextField(
            label="Nombre del Cliente", 
            prefix_icon=ft.Icons.PERSON, 
            expand=True
        )
        
        # Campo de Teléfono con Limpieza e Inspección al Pegar/Escribir
        self.tf_telefono = ft.TextField(
            label="WhatsApp (Pegar texto o número)", 
            prefix_icon=ft.Icons.PHONE, 
            expand=True,
            keyboard_type=ft.KeyboardType.PHONE,
            on_change=self.analizar_y_limpiar_telefono_registro,
            hint_text="Extrae automáticamente los 10 dígitos limpios si pegas texto."
        )
        
        self.tf_fecha = ft.TextField(
            label="Fecha (DD/MM/YYYY)", 
            value=datetime.now().strftime("%d/%m/%Y"), 
            expand=True
        )
        
        self.dd_tienda = ft.Dropdown(
            label="Selecciona la Tienda", 
            options=opciones_tienda, 
            value=val_defecto, 
            expand=True
        )

        # Renovación Express por Teléfono con Análisis Automático
        self.tf_renovar_tel = ft.TextField(
            label="Número a renovar rápido (Pegar texto o número)", 
            prefix_icon=ft.Icons.PHONE, 
            expand=True,
            keyboard_type=ft.KeyboardType.PHONE,
            on_change=self.analizar_y_limpiar_telefono_renovacion,
            hint_text="Analiza el texto pegado y busca el cliente."
        )
        
        self.btn_renovar_tel = ft.ElevatedButton(
            "Renovar Ahora", 
            icon=ft.Icons.AUTORENEW, 
            on_click=self.accion_renovar_rapido,
            color=ft.Colors.WHITE,
            bgcolor=ft.Colors.BLUE_700
        )

        self.tf_rapido_nombre = ft.TextField(label="Nombre", expand=True)
        self.tf_rapido_fecha = ft.TextField(label="Fecha Compra (DD/MM/YYYY)", value=datetime.now().strftime("%d/%m/%Y"), expand=True)
        self.dd_rapido_tienda = ft.Dropdown(label="Tienda", options=opciones_tienda, value=val_defecto, expand=True)

        self.dd_filtro_renovaciones = ft.Dropdown(
            label="Filtrar por Tienda",
            options=opciones_filtro,
            value=val_filtro,
            width=200
        )
        self.dd_filtro_renovaciones.on_change = self.cargar_renovaciones

        self.tf_import_texto = ft.TextField(
            label="Pega el texto crudo aquí", 
            multiline=True, min_lines=4, max_lines=8, expand=True,
            hint_text="Ej: Ale 06/07/2026 santiago ariza 06/07/2026"
        )
        self.dd_import_tienda = ft.Dropdown(label="Tienda destino", options=opciones_tienda, value=val_defecto)
        self.dlg_importar = ft.AlertDialog(
            title=ft.Text("Importación Masiva (Sin número)", color=ft.Colors.BLUE_200),
            content=ft.Column([
                ft.Text("Pega el bloque de texto con los nombres y fechas. El sistema los separará y guardará.", size=13, color=ft.Colors.WHITE70),
                self.dd_import_tienda,
                self.tf_import_texto
            ], tight=True),
            actions=[
                ft.TextButton("Cancelar", on_click=self.cerrar_modal),
                ft.ElevatedButton("Procesar y Guardar", icon=ft.Icons.AUTO_FIX_HIGH, on_click=self.procesar_importacion, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.lv_renovaciones = ft.ListView(expand=True, spacing=10)
        self.content = self.build_ui()

    # ==========================================
    # MANEJADORES DE EXTRACCIÓN/LIMPIEZA EN TIEMPO REAL
    # ==========================================
    def analizar_y_limpiar_telefono_registro(self, e):
        texto = self.tf_telefono.value
        if not texto:
            return
            
        # Si contiene texto extra o caracteres no numéricos, ejecutar el extractor
        if any(not c.isdigit() for c in texto) or len(texto) > 10:
            num_limpio = DBManager.limpiar_telefono(texto)
            if num_limpio != "Sin número" and num_limpio != texto:
                self.tf_telefono.value = num_limpio
                self.tf_telefono.update()

    def analizar_y_limpiar_telefono_renovacion(self, e):
        texto = self.tf_renovar_tel.value
        if not texto:
            return
            
        if any(not c.isdigit() for c in texto) or len(texto) > 10:
            num_limpio = DBManager.limpiar_telefono(texto)
            if num_limpio != "Sin número" and num_limpio != texto:
                self.tf_renovar_tel.value = num_limpio
                self.tf_renovar_tel.update()

    # ==========================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ==========================================
    def build_ui(self):
        return ft.ListView([
            ft.Row([
                ft.Text("Registro Rápido de Clientes", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200),
                ft.ElevatedButton("Importación Masiva", icon=ft.Icons.LIBRARY_ADD, on_click=self.abrir_modal, bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([self.tf_nombre, self.tf_telefono]),
            ft.Row([self.tf_fecha, self.dd_tienda]),
            ft.ElevatedButton(
                "Guardar Cliente", 
                icon=ft.Icons.SAVE, 
                on_click=self.guardar_cliente,
                style=ft.ButtonStyle(bgcolor=ft.Colors.DEEP_PURPLE_700, color=ft.Colors.WHITE)
            ),
            
            ft.Divider(height=30, color=ft.Colors.BLUE_GREY_900),
            
            # Renovación Express
            ft.Text("🚀 Renovación Express (Por número)", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_300),
            ft.Row([self.tf_renovar_tel, self.btn_renovar_tel]),

            ft.Divider(height=40, color=ft.Colors.BLUE_GREY_900),
            
            ft.Row([
                ft.Text("Vencidos o por Renovar (Hoy)", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_300),
                ft.Row([
                    self.dd_filtro_renovaciones,
                    ft.ElevatedButton("Actualizar Lista", icon=ft.Icons.REFRESH, on_click=self.cargar_renovaciones)
                ])
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            
            ft.Container(content=self.lv_renovaciones, height=350),
            
            ft.Divider(height=40, color=ft.Colors.BLUE_GREY_900),
            
            ft.Text("⚡ Generador Rápido (No Registrados)", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_300),
            ft.Row([self.tf_rapido_nombre, self.tf_rapido_fecha, self.dd_rapido_tienda]),
            ft.ElevatedButton(
                "Calcular y Copiar Mensaje", 
                icon=ft.Icons.CALCULATE, 
                on_click=self.crear_mensaje_rapido,
                style=ft.ButtonStyle(bgcolor=ft.Colors.AMBER_800, color=ft.Colors.BLACK)
            )
        ], expand=True, spacing=15)

    def mostrar_notificacion(self, mensaje: str, color: str):
        snack = ft.SnackBar(ft.Text(mensaje), bgcolor=color)
        self.main_page.overlay.append(snack)
        snack.open = True
        self.main_page.update()

    def abrir_modal(self, e):
        self.main_page.overlay.append(self.dlg_importar)
        self.dlg_importar.open = True
        self.main_page.update()

    def cerrar_modal(self, e):
        self.dlg_importar.open = False
        self.main_page.update()

    def accion_renovar_rapido(self, e):
        telefono = DBManager.limpiar_telefono(self.tf_renovar_tel.value)
        if not telefono or telefono == "Sin número":
            self.mostrar_notificacion("Ingresa o pega un número de teléfono válido.", ft.Colors.RED_400)
            return
            
        exito, resultado = self.db.renovar_por_telefono(telefono, self.usuario["tienda_asignada"])
        
        if exito:
            self.mostrar_notificacion(f"¡Renovado con éxito! Cliente: {resultado}", ft.Colors.GREEN_600)
            self.tf_renovar_tel.value = "" 
            self.main_page.update()
            self.cargar_renovaciones()
        else:
            self.mostrar_notificacion(resultado, ft.Colors.RED_400)

    def procesar_importacion(self, e):
        texto_crudo = self.tf_import_texto.value
        tienda_destino = self.dd_import_tienda.value
        
        if not texto_crudo:
            self.mostrar_notificacion("El texto está vacío", ft.Colors.RED)
            return
            
        texto_crudo = texto_crudo.replace('\n', ' ')
        patron = r"(.*?)([0-9]{2}/[0-9]{2}/[0-9]{4})"
        matches = re.findall(patron, texto_crudo)
        
        if not matches:
            self.mostrar_notificacion("No se encontraron fechas válidas. Verifica el texto.", ft.Colors.RED)
            return
            
        lista_a_guardar = []
        for match in matches:
            nombre = match[0].strip()
            fecha = match[1].strip()
            if nombre == "":
                nombre = "Desconocido"
            lista_a_guardar.append((nombre, "Sin número", tienda_destino, fecha))
            
        self.db.registrar_clientes_masivo(lista_a_guardar)
        self.tf_import_texto.value = ""
        self.cerrar_modal(None)
        self.mostrar_notificacion(f"¡Se importaron {len(lista_a_guardar)} clientes con éxito!", ft.Colors.GREEN_700)
        self.cargar_renovaciones()

    def guardar_cliente(self, e):
        if not self.tf_nombre.value or not self.tf_telefono.value:
            self.mostrar_notificacion("Falta nombre o teléfono", ft.Colors.RED)
            return
            
        telefono = DBManager.limpiar_telefono(self.tf_telefono.value)
        if len(telefono) < 10 and telefono != "Sin número":
            self.mostrar_notificacion("Ingresa un número de WhatsApp válido (10 dígitos)", ft.Colors.RED)
            return

        try:
            datetime.strptime(self.tf_fecha.value, "%d/%m/%Y")
        except ValueError:
            self.mostrar_notificacion("Formato de fecha inválido. Usa DD/MM/YYYY", ft.Colors.RED)
            return

        self.db.registrar_cliente(self.tf_nombre.value, telefono, self.dd_tienda.value, self.tf_fecha.value)
        self.mostrar_notificacion("Cliente guardado con éxito", ft.Colors.GREEN_700)
        
        self.tf_nombre.value = ""
        self.tf_telefono.value = ""
        self.main_page.update()
        self.cargar_renovaciones()

    def cargar_renovaciones(self, e=None):
        self.lv_renovaciones.controls.clear()
        
        clientes = self.db.obtener_clientes_por_renovar(self.usuario["tienda_asignada"])
        filtro_actual = self.dd_filtro_renovaciones.value
        
        for c in clientes:
            c_id, nombre, tel, tienda, f_compra, f_renov = c
            
            if filtro_actual != "Todas" and tienda != filtro_actual:
                continue
            
            mensaje = generar_mensaje_renovacion(nombre, tienda)
            color_tienda = ft.Colors.PURPLE_400 if tienda == "PeliZone" else ft.Colors.TEAL_400
            
            tarjeta = ft.Card(
                bgcolor=ft.Colors.BLUE_GREY_900,
                data={"num_copiado": False, "msg_copiado": False, "id": c_id}
            )
            
            if tel != "Sin número":
                link_seguro = generar_enlace_whatsapp_seguro(tel, mensaje)
                btn_whatsapp = ft.ElevatedButton(
                    "WhatsApp", 
                    icon=ft.Icons.ROCKET_LAUNCH, 
                    bgcolor=ft.Colors.GREEN_600, 
                    color=ft.Colors.WHITE,
                    on_click=lambda e, l=link_seguro, tj=tarjeta: self.accion_abrir_whatsapp(l, tj, e)
                )
                btn_num = ft.TextButton("Copiar Número", icon=ft.Icons.COPY, on_click=lambda e, t=tel, tj=tarjeta: self.accion_copiar("numero", t, tj, e))
            else:
                btn_whatsapp = ft.Container()
                btn_num = ft.TextButton("Copiar Nombre", icon=ft.Icons.PERSON_SEARCH, on_click=lambda e, n=nombre, tj=tarjeta: self.accion_copiar("nombre", n, tj, e))
                
            btn_msg = ft.TextButton("Copiar Mensaje", icon=ft.Icons.MESSAGE, on_click=lambda e, m=mensaje, tj=tarjeta: self.accion_copiar("mensaje", m, tj, e))
            btn_renovar = ft.ElevatedButton("Renovar Ahora", icon=ft.Icons.AUTORENEW, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, on_click=lambda e, id_c=c_id: self.ejecutar_renovacion(id_c))

            tarjeta.content = ft.Container(
                padding=15,
                content=ft.Column([
                    ft.Row([
                        ft.Text(f"{nombre}", weight=ft.FontWeight.BOLD, size=18),
                        ft.Container(content=ft.Text(tienda, size=12, weight=ft.FontWeight.BOLD), bgcolor=color_tienda, padding=5, border_radius=5)
                    ]),
                    ft.Text(f"Vence hoy/Vencido: {f_renov} (Compró: {f_compra} | Tel: {tel})", color=ft.Colors.RED_200),
                    ft.Row([btn_num, btn_msg, btn_whatsapp, btn_renovar])
                ])
            )
            
            self.lv_renovaciones.controls.append(tarjeta)
            
        self.main_page.update()

    def accion_abrir_whatsapp(self, link: str, tarjeta: ft.Card, e):
        self.main_page.launch_url(link)
        tarjeta.data["num_copiado"] = True 
        tarjeta.data["msg_copiado"] = True
        
        e.control.text = "Enviado ✔"
        e.control.bgcolor = ft.Colors.BLUE_600
        self.main_page.update()
        
        self.verificar_eliminacion(tarjeta)

    def accion_copiar(self, tipo: str, texto: str, tarjeta: ft.Card, e):
        self.escribir_portapapeles(texto)
        
        e.control.icon = ft.Icons.CHECK
        e.control.text = "Copiado ✔"
        e.control.color = ft.Colors.GREEN_400
        self.main_page.update()

        if tipo in ["numero", "nombre"]:
            tarjeta.data["num_copiado"] = True
        elif tipo == "mensaje":
            tarjeta.data["msg_copiado"] = True
            
        self.verificar_eliminacion(tarjeta)
        
    def verificar_eliminacion(self, tarjeta: ft.Card):
        if tarjeta.data["num_copiado"] and tarjeta.data["msg_copiado"]:
            cliente_id = tarjeta.data["id"]
            self.db.eliminar_cliente(cliente_id)
            
            self.mostrar_notificacion("¡Contactado! Registro eliminado de la base de datos local.", ft.Colors.GREEN_700)
            if tarjeta in self.lv_renovaciones.controls:
                self.lv_renovaciones.controls.remove(tarjeta)
                self.main_page.update()
        else:
            self.mostrar_notificacion("Elemento copiado al portapapeles.", ft.Colors.BLUE_700)

    def ejecutar_renovacion(self, cliente_id: int):
        self.db.renovar_cliente(cliente_id)
        self.mostrar_notificacion("¡Cliente renovado por 30 días más!", ft.Colors.GREEN_700)
        self.cargar_renovaciones()

    def crear_mensaje_rapido(self, e):
        nombre = self.tf_rapido_nombre.value
        fecha = self.tf_rapido_fecha.value
        tienda = self.dd_rapido_tienda.value
        
        if not nombre or not fecha:
            self.mostrar_notificacion("Faltan datos", ft.Colors.RED)
            return
            
        mensaje = generar_mensaje_rapido(nombre, fecha, tienda)
        if "Error:" in mensaje:
            self.mostrar_notificacion(mensaje, ft.Colors.RED)
        else:
            self.escribir_portapapeles(mensaje)
            self.mostrar_notificacion("¡Mensaje calculated y copiado al portapapeles!", ft.Colors.BLUE_700)

    def escribir_portapapeles(self, texto: str):
        async def accion_copiar_async(texto_a_copiar):
            try:
                await self.main_page.clipboard.set(texto_a_copiar)
            except Exception as e:
                print(f"Error asíncrono al copiar: {e}")

        self.main_page.run_task(accion_copiar_async, texto)
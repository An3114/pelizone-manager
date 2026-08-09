import flet as ft
from database.db_manager import DBManager

class AdminView(ft.Container):
    def __init__(self, db: DBManager, page: ft.Page):
        super().__init__()
        self.db = db
        self.main_page = page
        self.expand = True

        self.tf_nueva_tienda = ft.TextField(label="Nombre de la nueva página/tienda", expand=True)
        self.btn_crear_tienda = ft.Button("Agregar Tienda", icon=ft.Icons.STORE, on_click=self.crear_tienda, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)

        self.tf_usuario = ft.TextField(label="Nombre de usuario (Login del asesor)", expand=True)
        self.tf_clave = ft.TextField(label="Contraseña (Ej: 2026)", expand=True)
        self.dd_rol = ft.Dropdown(label="Rol de Usuario", options=[
            ft.dropdown.Option("admin"),
            ft.dropdown.Option("vendedor")
        ], value="vendedor", expand=True)

        self.dd_tienda_asignada = ft.Dropdown(label="Tienda Asignada (Solo para vendedores)", expand=True)
        self.actualizar_dropdown_tiendas()

        self.btn_crear_usuario = ft.Button("Crear Usuario", icon=ft.Icons.PERSON_ADD, on_click=self.crear_usuario, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)

        self.content = self.build_ui()

    def actualizar_dropdown_tiendas(self):
        tiendas = self.db.obtener_tiendas()
        opciones = [ft.dropdown.Option("Todas")] + [ft.dropdown.Option(t) for t in tiendas]
        self.dd_tienda_asignada.options = opciones
        if not self.dd_tienda_asignada.value:
            self.dd_tienda_asignada.value = "Todas"

    def build_ui(self):
        return ft.ListView([
            ft.Text("Panel de Administración", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.DEEP_PURPLE_200),
            ft.Text("Aquí puedes crear nuevas tiendas y darle acceso a tus vendedores.", color=ft.Colors.WHITE54),
            
            ft.Divider(height=30, color=ft.Colors.BLUE_GREY_900),
            
            ft.Text("🏬 Gestión de Tiendas / Páginas", size=20, weight=ft.FontWeight.BOLD),
            ft.Row([self.tf_nueva_tienda, self.btn_crear_tienda], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            
            ft.Divider(height=40, color=ft.Colors.BLUE_GREY_900),

            ft.Text("👥 Crear Nuevos Accesos (Login)", size=20, weight=ft.FontWeight.BOLD),
            ft.Row([self.tf_usuario, self.tf_clave]),
            ft.Row([self.dd_rol, self.dd_tienda_asignada]),
            ft.Row([self.btn_crear_usuario], alignment=ft.MainAxisAlignment.END)
        ], expand=True, spacing=15)

    def mostrar_notificacion(self, mensaje: str, color: str):
        snack = ft.SnackBar(ft.Text(mensaje), bgcolor=color)
        self.main_page.overlay.append(snack)
        snack.open = True
        self.main_page.update()

    def crear_tienda(self, e):
        nombre = self.tf_nueva_tienda.value
        if not nombre:
            self.mostrar_notificacion("Escribe un nombre para la tienda", ft.Colors.RED)
            return
            
        exito, msj = self.db.agregar_tienda(nombre)
        if exito:
            self.mostrar_notificacion(msj, ft.Colors.GREEN)
            self.tf_nueva_tienda.value = ""
            self.actualizar_dropdown_tiendas()
            self.main_page.update()
        else:
            self.mostrar_notificacion(msj, ft.Colors.RED)

    def crear_usuario(self, e):
        usuario = self.tf_usuario.value.strip()
        clave = self.tf_clave.value
        rol = self.dd_rol.value
        tienda = self.dd_tienda_asignada.value

        if not usuario or not clave:
            self.mostrar_notificacion("El usuario y la clave son obligatorios", ft.Colors.RED)
            return

        exito, msj = self.db.crear_usuario(usuario, clave, rol, tienda)
        if exito:
            self.mostrar_notificacion(msj, ft.Colors.GREEN)
            self.tf_usuario.value = ""
            self.tf_clave.value = ""
            self.main_page.update()
        else:
            self.mostrar_notificacion(msj, ft.Colors.RED)
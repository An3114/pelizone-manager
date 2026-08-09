import flet as ft
import json
import os
from database.db_manager import DBManager
from ui.views.clients import ClientView
from ui.views.admin import AdminView 

def main(page: ft.Page):
    # Configuración de la ventana y tema
    page.title = "PeliZone Manager"
    page.window.width = 1200
    page.window.height = 800
    page.window.min_width = 800
    page.window.min_height = 600
    
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.DEEP_PURPLE,
        visual_density=ft.VisualDensity.COMFORTABLE,
    )
    page.padding = 0 
    
    db = DBManager()

    def mostrar_login():
        page.clean()
        page.appbar = None 

        tf_usuario = ft.TextField(
            label="Usuario", 
            width=350, 
            prefix_icon=ft.Icons.PERSON
        )
        tf_clave = ft.TextField(
            label="Contraseña", 
            width=350, 
            password=True, 
            can_reveal_password=True, 
            prefix_icon=ft.Icons.LOCK,
            on_submit=lambda e: intentar_login(e)  # Inicia sesión al presionar Enter
        )
        lbl_error = ft.Text("", color=ft.Colors.RED_400)

        def intentar_login(e):
            usuario = tf_usuario.value.strip()
            clave = tf_clave.value
            valido, resultado = db.verificar_login(usuario, clave)

            if valido:
                try:
                    with open("sesion.json", "w", encoding="utf-8") as f:
                        json.dump({"usuario": usuario, "clave": clave}, f)
                except Exception as err:
                    print(f"⚠️ No se pudo guardar la sesión local: {err}")

                cargar_app_principal(resultado) 
            else:
                lbl_error.value = str(resultado)
                page.update()

        caja_login = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS, size=80, color=ft.Colors.DEEP_PURPLE_300),
                ft.Text("PeliZone Manager", size=32, weight=ft.FontWeight.BOLD),
                ft.Text("Inicia sesión para continuar", size=16, color=ft.Colors.WHITE54),
                ft.Container(height=20),
                tf_usuario,
                tf_clave,
                lbl_error,
                ft.ElevatedButton(
                    "Ingresar", 
                    on_click=intentar_login, 
                    bgcolor=ft.Colors.DEEP_PURPLE_700, 
                    color=ft.Colors.WHITE, 
                    width=350, 
                    height=50
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.Alignment(0, 0), # <--- SOLUCIÓN: Nueva sintaxis de Flet 0.80+ para centrar
            expand=True,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW
        )
        
        page.add(caja_login)

    def cargar_app_principal(usuario_actual: dict):
        page.clean()
        
        vista_clientes = ClientView(db, page, usuario_actual)
        pantalla_clientes = ft.Container(content=vista_clientes, padding=20, expand=True)
        
        pantalla_dashboard = ft.Container(
            content=ft.Column([
                ft.Text("Estadísticas", size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200),
                ft.Text("Módulo en construcción...", size=16, color=ft.Colors.WHITE54)
            ]), padding=20, expand=True
        )

        vista_admin = AdminView(db, page)
        pantalla_admin = ft.Container(content=vista_admin, padding=20, expand=True)
        
        contenedor_activo = ft.AnimatedSwitcher(
            content=pantalla_clientes,
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=300,
            expand=True
        )
        
        titulo_seccion = ft.Text("Gestión de Clientes", size=20, weight=ft.FontWeight.BOLD)
        
        destinos_menu = [
            ft.NavigationRailDestination(icon=ft.Icons.PEOPLE_OUTLINE, selected_icon=ft.Icons.PEOPLE, label="Clientes"),
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Estadísticas"),
        ]
        
        if usuario_actual.get("rol") == "admin":
            destinos_menu.append(
                ft.NavigationRailDestination(icon=ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, selected_icon=ft.Icons.ADMIN_PANEL_SETTINGS, label="Admin")
            )

        def cambiar_vista(e):
            idx = e.control.selected_index
            if idx == 0:
                contenedor_activo.content = pantalla_clientes
                titulo_seccion.value = "Gestión de Clientes"
            elif idx == 1:
                contenedor_activo.content = pantalla_dashboard
                titulo_seccion.value = "Panel de Estadísticas"
            elif idx == 2 and usuario_actual.get("rol") == "admin":
                contenedor_activo.content = pantalla_admin
                titulo_seccion.value = "Administración del Sistema"
            
            contenedor_activo.update()
            titulo_seccion.update()

        menu_lateral = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            group_alignment=-0.95,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            destinations=destinos_menu,
            on_change=cambiar_vista
        )

        def cerrar_sesion(e):
            if os.path.exists("sesion.json"):
                try:
                    os.remove("sesion.json")
                except Exception:
                    pass
            mostrar_login()

        texto_usuario = ft.Text(
            f"👤 {usuario_actual.get('usuario', '')} | Tienda: {usuario_actual.get('tienda_asignada', '')}", 
            size=14, 
            color=ft.Colors.WHITE70
        )
        btn_salir = ft.IconButton(
            icon=ft.Icons.LOGOUT, 
            tooltip="Cerrar Sesión", 
            on_click=cerrar_sesion, 
            icon_color=ft.Colors.RED_300
        )

        page.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.MOVIE_FILTER, color=ft.Colors.DEEP_PURPLE_200, size=30),
            leading_width=60,
            title=titulo_seccion,
            center_title=False,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            actions=[
                ft.Row([texto_usuario, btn_salir], alignment=ft.MainAxisAlignment.END),
                ft.Container(width=20) 
            ]
        )

        page.add(
            ft.Row(
                [
                    menu_lateral,
                    ft.VerticalDivider(width=1, color=ft.Colors.WHITE10),
                    ft.Container(content=contenedor_activo, expand=True) 
                ],
                expand=True,
                spacing=0
            )
        )
        
        vista_clientes.cargar_renovaciones()

    # Verificación de sesión persistente
    sesion_guardada = None
    if os.path.exists("sesion.json"):
        try:
            with open("sesion.json", "r", encoding="utf-8") as f:
                sesion_guardada = json.load(f)
        except Exception as e:
            print(f"⚠️ Error leyendo sesion.json: {e}")
            
    if sesion_guardada:
        valido, resultado = db.verificar_login(
            sesion_guardada.get("usuario", ""), 
            sesion_guardada.get("clave", "")
        )
        if valido:
            cargar_app_principal(resultado)
        else:
            if os.path.exists("sesion.json"):
                try:
                    os.remove("sesion.json")
                except Exception:
                    pass
            mostrar_login()
    else:
        mostrar_login()

if __name__ == "__main__":
    ft.run(main)
from datetime import datetime, timedelta
import urllib.parse
import re

def limpiar_numero_whatsapp(numero: str, codigo_pais_defecto: str = "57") -> str:
    """
    Extrae únicamente los dígitos numéricos y asegura que el número 
    tenga el prefijo internacional necesario para abrir enlaces wa.me sin errores.
    """
    if not numero or str(numero).strip().lower() in ("sin número", "sin numero", "none", ""):
        return ""

    # Extraer únicamente dígitos
    digitos = re.sub(r'\D', '', str(numero))

    if not digitos:
        return ""

    # Normalizar prefijos internacionales con ceros iniciales (ej. 0057... -> 57...)
    if digitos.startswith("00"):
        digitos = digitos.lstrip("0")

    # Caso Colombia: Número celular local de 10 dígitos que inicia en 3 (ej. 3104266339)
    if len(digitos) == 10 and digitos.startswith("3"):
        return f"{codigo_pais_defecto}{digitos}"

    # Caso Colombia: Si ya incluye el código de país (12 dígitos e inicia en 57)
    if len(digitos) == 12 and digitos.startswith("57"):
        return digitos

    # Retorno por defecto garantizado (evita devolver None en otros formatos)
    return digitos


def generar_enlace_whatsapp_seguro(numero: str, mensaje: str, codigo_pais_defecto: str = "57") -> str:
    """
    Genera una URL compatible con la API de WhatsApp (https://wa.me/)
    garantizando que el número tenga el formato internacional correcto.
    """
    num_limpio = limpiar_numero_whatsapp(numero, codigo_pais_defecto)
    if not num_limpio:
        return "#"
        
    mensaje_codificado = urllib.parse.quote(mensaje.strip())
    return f"https://wa.me/{num_limpio}?text={mensaje_codificado}"


def generar_mensaje_renovacion(nombre: str, tienda: str) -> str:
    """
    Crea el mensaje formateado para avisar del vencimiento de un servicio.
    """
    nombre_fmt = str(nombre).strip().title() if nombre else "Cliente"
    tienda_fmt = str(tienda).strip() if tienda else "nuestra tienda"

    return (
        f"Hola, {nombre_fmt} 👋\n"
        f"Esperamos que estés muy bien.\n"
        f"Te escribimos de parte de {tienda_fmt} para informarte que tu paquete de servicio ya se venció.\n"
        f"¿Deseas comprar un nuevo paquete para continuar disfrutando del servicio?\n"
        f"Quedamos atentos a tu mensaje. ¡Muchas gracias! 😊"
    )


def generar_mensaje_rapido(nombre: str, fecha_str: str, tienda: str) -> str:
    """
    Calcula la fecha de renovación a 30 días y genera un mensaje con el estado exacto del paquete.
    Soporta formatos DD/MM/YYYY y DD-MM-YYYY.
    """
    nombre_fmt = str(nombre).strip().title() if nombre else "Cliente"
    tienda_fmt = str(tienda).strip() if tienda else "nuestra tienda"
    fecha_limpia = str(fecha_str).strip().replace("-", "/")

    try:
        fecha_obj = datetime.strptime(fecha_limpia, "%d/%m/%Y")
    except ValueError:
        return "Error: Revisa que la fecha sea exactamente DD/MM/YYYY (Ej: 28/07/2026)"

    fecha_renovacion = fecha_obj + timedelta(days=30)
    hoy = datetime.now().date()
    f_renov_date = fecha_renovacion.date()

    if hoy > f_renov_date:
        estado = f"se venció el {fecha_renovacion.strftime('%d/%m/%Y')}"
    elif hoy == f_renov_date:
        estado = "vence HOY"
    else:
        estado = f"vence el {fecha_renovacion.strftime('%d/%m/%Y')}"

    fecha_compra_fmt = fecha_obj.strftime("%d/%m/%Y")

    return (
        f"Hola, {nombre_fmt} 👋\n"
        f"Te escribimos de parte de {tienda_fmt}.\n"
        f"Te recordamos que el paquete que compraste el {fecha_compra_fmt} {estado}.\n"
        f"¿Deseas comprar un nuevo paquete?\n"
        f"Estaremos felices de ayudarte. 😊"
    )
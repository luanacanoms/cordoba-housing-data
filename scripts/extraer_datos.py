"""
================================================================
SCRIPT DE EXTRACCIÓN AUTOMÁTICA — Viviendas en venta en Córdoba
================================================================
Este script se ejecuta automáticamente todos los días (mediante
GitHub Actions) y hace, en orden, lo siguiente:

  1. Se conecta a la API oficial de Idealista y obtiene los datos
     de todos los anuncios de viviendas en venta en Córdoba capital
  2. Organiza esos datos en el formato/columnas que necesitamos
     para el análisis (regresión y redes neuronales)
  3. Compara los anuncios de hoy con los del día anterior, para
     detectar si aparecieron anuncios nuevos
  4. Si hay anuncios nuevos, envía un correo electrónico de aviso
  5. Guarda todo en archivos CSV dentro de la carpeta "data/"

No hace falta ejecutar nada manualmente: todo esto ocurre solo,
una vez al día.
================================================================
"""

import requests
import base64
import pandas as pd
import time
import os
import glob
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ----------------------------------------------------------------
# Estas credenciales NO están escritas aquí por seguridad.
# Se guardan de forma protegida en GitHub ("Secrets") y el sistema
# las coloca automáticamente en estas variables cuando el script
# se ejecuta. Nadie puede verlas, ni siquiera nosotros, una vez
# guardadas.
# ----------------------------------------------------------------
EMAIL_REMETENTE = os.environ.get("EMAIL_REMETENTE")
EMAIL_SENHA = os.environ.get("EMAIL_SENHA")
EMAIL_DESTINATARIO = os.environ.get("EMAIL_DESTINATARIO")

API_KEY = os.environ.get("IDEALISTA_API_KEY")
API_SECRET = os.environ.get("IDEALISTA_API_SECRET")

# ----------------------------------------------------------------
# Configuración general: dónde buscar (Córdoba capital, 5 km a la
# redonda), cuántas páginas de resultados leer como máximo, y los
# nombres de los archivos que se van a generar cada día (con la
# fecha de hoy incluida en el nombre).
# ----------------------------------------------------------------
CENTRO_CORDOBA = "37.8882,-4.7794"
RADIO_METROS = "5000"
MAX_PAGINAS = 55

RUTA_GABARITO = "data/foo.csv"  # plantilla con el orden de columnas que necesitamos
FECHA_HOY = datetime.now().strftime('%Y-%m-%d')
RUTA_SALIDA = f"data/viviendas_cordoba_idealista_{FECHA_HOY}.csv"
RUTA_NUEVOS = f"data/anuncios_nuevos_{FECHA_HOY}.csv"


# ==================================================================
# PASO 1: Pedirle permiso a Idealista para usar su API
# ==================================================================
def obtener_token():
    """
    Antes de poder pedir datos a Idealista, hay que "identificarse"
    con nuestras credenciales (como un usuario y contraseña).
    Idealista nos responde con un "token": un código temporal que
    demuestra que tenemos permiso para consultar sus datos.
    """
    credentials = f"{API_KEY}:{API_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    token_url = "https://api.idealista.com/oauth/token"
    data = {"grant_type": "client_credentials", "scope": "read"}
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
    }

    response = requests.post(token_url, data=data, headers=headers)

    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        raise Exception(f"Error de autenticación: {response.status_code} - {response.text}")


# ==================================================================
# PASO 2: Traducir cada vivienda al formato que necesitamos
# ==================================================================
def mapear_imovel_api(imovel_json):
    """
    Idealista nos devuelve la información de cada vivienda con sus
    propios nombres de campo (por ejemplo, "propertyCode" en vez de
    "id"). Esta función "traduce" esos nombres a los que definimos
    para nuestra base de datos final, para que todo quede ordenado
    y consistente.
    """
    detalhes = imovel_json.get('detailedType', {})
    estacionamento = imovel_json.get('parkingSpace', {})

    return {
        'id': imovel_json.get('propertyCode'),
        'url': imovel_json.get('url'),
        'operation': imovel_json.get('operation'),
        'state': imovel_json.get('province'),
        'location_id': imovel_json.get('municipality'),
        'ubicacion_latitude': imovel_json.get('latitude'),
        'ubicacion_longitud': imovel_json.get('longitude'),
        'ubicacion_HasHidden': imovel_json.get('showAddress') == False,
        'ubication__administrativeAreaLevel1': imovel_json.get('country'),
        'ubication__administrativeAreaLevel2': imovel_json.get('province'),
        'ubication__administrativeAreaLevel3': imovel_json.get('district'),
        'ubication__administrativeAreaLevel4': imovel_json.get('neighborhood'),
        'commercialDataId': None,
        'price_raw': imovel_json.get('price'),
        'housetype': imovel_json.get('propertyType'),
        'extendedPropertyType': detalhes.get('subTypology') or detalhes.get('typology'),
        'constructedArea': imovel_json.get('size'),
        'usableArea': None,
        'plotOfLand': None,
        'roomNumber': imovel_json.get('rooms'),
        'bathNumber': imovel_json.get('bathrooms'),
        'isInTopFloor': None,
        'isDuplex': 'duplex' in imovel_json.get('propertyType', '').lower(),
        'flatLocation': None,
        'isStudio': 'studio' in imovel_json.get('propertyType', '').lower(),
        'agencyIsABank': None,
        'isPenthouse': None,
        'energyCertificationType': None,
        'energyPerformance': None,
        'status': imovel_json.get('status'),
        'lift': imovel_json.get('hasLift'),
        'isAuction': None,
        'boxroom': None,
        'swimmingPool': imovel_json.get('hasSwimmingPool'),
        'chimney': None,
        'garden': None,
        'communityCosts': None,
        'heaterType1': None,
        'heaterType2': None,
        'construction_year': None,
        'manyFloors': None,
        'orientation': None,
        'terrace': None,
        'has_garage': estacionamento.get('hasParkingSpace', False),
        'garage_price': None,
        'floorNumber': imovel_json.get('floor'),
        'aircondicioning': imovel_json.get('hasAirConditioning')
    }


# ==================================================================
# PASO 3: Descargar TODOS los anuncios (recorriendo página por página)
# ==================================================================
def extrair_base_completa(token_acesso, max_paginas=MAX_PAGINAS):
    """
    Idealista no nos da todos los anuncios de una vez: los entrega
    en "páginas" (como los resultados de un buscador). Esta función
    va pidiendo página tras página, hasta que ya no queden más
    anuncios, y junta todo en una única lista.
    """
    url_search = "https://api.idealista.com/3.5/es/search"
    headers = {
        "Authorization": f"Bearer {token_acesso}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    todos_imoveis = []

    for pagina in range(1, max_paginas + 1):
        print(f"Coletando página {pagina}...")

        payload = {
            "country": "es",
            "operation": "sale",
            "propertyType": "homes",
            "center": CENTRO_CORDOBA,
            "distance": RADIO_METROS,
            "maxItems": "50",
            "numPage": str(pagina)
        }

        response = requests.post(url_search, data=payload, headers=headers)

        if response.status_code == 200:
            dados = response.json()
            lista_elementos = dados.get('elementList', [])

            # Si la página viene vacía, ya no hay más anuncios: paramos aquí
            if not lista_elementos:
                print("Fin de los resultados alcanzado.")
                break

            for imovel_bruto in lista_elementos:
                todos_imoveis.append(mapear_imovel_api(imovel_bruto))
        else:
            print(f"Error en la página {pagina}: Status {response.status_code}")
            print("Detalle:", response.text)
            break

        # Pequeña pausa entre página y página, para no saturar el servidor de Idealista
        time.sleep(1.5)

    return pd.DataFrame(todos_imoveis)


# ==================================================================
# PASO 4: Ordenar las columnas según la plantilla del proyecto
# ==================================================================
def alinhar_com_gabarito(df_raspado, ruta_gabarito):
    """
    Nos aseguramos de que el archivo final tenga exactamente las
    mismas columnas, con los mismos nombres y en el mismo orden,
    que la plantilla original (foo.csv) que definimos al principio
    del proyecto.
    """
    df_gabarito = pd.read_csv(ruta_gabarito, nrows=0)

    mapa_colunas = {
        'ubicacion_latitude': 'ubication__latitude',
        'ubicacion_longitud': 'ubication__longitude',
        'ubicacion_HasHidden': 'ubication__hasHiddenAddress',
        'has_garage': 'has garage',
        'garage_price': 'garage price',
        'construction_year': 'construction year',
        'aircondicioning': 'air conditioning',
        'price_raw': 'price raw',
        'housetype': 'house type'
    }

    df_raspado = df_raspado.rename(columns=mapa_colunas)
    return df_raspado.reindex(columns=df_gabarito.columns)


# ==================================================================
# PASO 5: Comparar con el archivo de ayer para detectar novedades
# ==================================================================
def comparar_com_historico(df_hoy):
    """
    Busca el archivo más reciente guardado anteriormente (el de
    "ayer") y lo compara con los datos de hoy. Cualquier vivienda
    que aparezca hoy pero no estuviera ayer se considera un
    "anuncio nuevo".
    """
    lista_archivos = glob.glob('data/viviendas_cordoba_idealista_*.csv')
    lista_archivos = [f for f in lista_archivos if RUTA_SALIDA not in f]
    lista_archivos.sort(key=os.path.getmtime)

    # Si es la primera vez que se ejecuta el script, no hay nada con qué comparar
    if len(lista_archivos) == 0:
        print("No se encontró historial previo. Saltando la comparación.")
        return pd.DataFrame()

    archivo_historico = lista_archivos[-1]
    print(f"Comparando datos contra: {archivo_historico}")

    df_ayer = pd.read_csv(archivo_historico)
    nuevos_ids = set(df_hoy['id']) - set(df_ayer['id'])
    anuncios_nuevos = df_hoy[df_hoy['id'].isin(nuevos_ids)]

    if not anuncios_nuevos.empty:
        anuncios_nuevos.to_csv(RUTA_NUEVOS, index=False, encoding='utf-8-sig')
        print(f"¡Se exportaron {len(anuncios_nuevos)} anuncios nuevos a {RUTA_NUEVOS}!")
    else:
        print("El mercado está quieto: no hay anuncios nuevos hoy.")

    return anuncios_nuevos


# ==================================================================
# PASO 6: Avisar por correo si hay anuncios nuevos
# ==================================================================
def enviar_email_alerta(anuncios_nuevos):
    """
    Si el paso anterior encontró anuncios nuevos, esta función
    redacta y envía automáticamente un correo de aviso, con la
    cantidad de anuncios nuevos y sus enlaces directos.
    """
    if anuncios_nuevos.empty:
        print("Sin anuncios nuevos, no se envía correo.")
        return

    if not EMAIL_REMETENTE or not EMAIL_SENHA or not EMAIL_DESTINATARIO:
        print("Faltan credenciales de correo, no se puede enviar la alerta.")
        return

    cantidad = len(anuncios_nuevos)
    lista_urls = "\n".join(anuncios_nuevos['url'].dropna().tolist())

    cuerpo = f"""Se han detectado {cantidad} nuevos anuncios de vivienda en Córdoba capital.

Enlaces:
{lista_urls}

El archivo completo con todos los datos está disponible en el repositorio de GitHub, en la carpeta data/.
"""

    mensaje = MIMEMultipart()
    mensaje['From'] = EMAIL_REMETENTE
    mensaje['To'] = EMAIL_DESTINATARIO
    mensaje['Subject'] = f"[Córdoba] {cantidad} nuevos anuncios detectados - {FECHA_HOY}"
    mensaje.attach(MIMEText(cuerpo, 'plain'))

    try:
        # Nos conectamos al servidor de correo de Gmail y enviamos el mensaje,
        # usando la "contraseña de aplicación" (no la contraseña normal de la cuenta)
        servidor = smtplib.SMTP('smtp.gmail.com', 587)
        servidor.starttls()
        servidor.login(EMAIL_REMETENTE, EMAIL_SENHA)
        servidor.send_message(mensaje)
        servidor.quit()
        print(f"Correo de alerta enviado a {EMAIL_DESTINATARIO}")
    except Exception as e:
        print(f"Error al enviar el correo: {e}")


# ==================================================================
# EJECUCIÓN PRINCIPAL — el "orden de pasos" que se sigue cada día
# ==================================================================
def main():
    if not API_KEY or not API_SECRET:
        raise Exception("Faltan las credenciales de la API (IDEALISTA_API_KEY / IDEALISTA_API_SECRET)")

    print("Obteniendo token de acceso...")
    token = obtener_token()

    print("Extrayendo datos de la API...")
    df_raspado = extrair_base_completa(token)
    print(f"Total de inmuebles extraídos: {len(df_raspado)}")

    print("Alineando columnas con el esquema de referencia...")
    df_hoy = alinhar_com_gabarito(df_raspado, RUTA_GABARITO)

    os.makedirs("data", exist_ok=True)

    print("Comparando con el historial...")
    anuncios_nuevos = comparar_com_historico(df_hoy)

    print("Verificando envío de alerta por correo...")
    enviar_email_alerta(anuncios_nuevos)

    # Guardamos la base de datos de hoy: será el "historial de ayer"
    # que se usará mañana para la próxima comparación
    df_hoy.to_csv(RUTA_SALIDA, index=False, encoding='utf-8-sig')
    print(f"Base general actualizada y guardada en: {RUTA_SALIDA}")


if __name__ == "__main__":
    main()

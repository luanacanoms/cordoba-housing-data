import requests
import base64
import pandas as pd
import time
import os
import glob
from datetime import datetime

API_KEY = os.environ.get("IDEALISTA_API_KEY")
API_SECRET = os.environ.get("IDEALISTA_API_SECRET")

CENTRO_CORDOBA = "37.8882,-4.7794"
RADIO_METROS = "5000"
MAX_PAGINAS = 55

RUTA_GABARITO = "data/foo.csv"
FECHA_HOY = datetime.now().strftime('%Y-%m-%d')
RUTA_SALIDA = f"data/viviendas_cordoba_idealista_{FECHA_HOY}.csv"
RUTA_NUEVOS = f"data/anuncios_nuevos_{FECHA_HOY}.csv"


def obtener_token():
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


def mapear_imovel_api(imovel_json):
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
        'agencyIsABankisPenthouse': None,
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


def extrair_base_completa(token_acesso, max_paginas=MAX_PAGINAS):
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

            if not lista_elementos:
                print("Fin de los resultados alcanzado.")
                break

            for imovel_bruto in lista_elementos:
                todos_imoveis.append(mapear_imovel_api(imovel_bruto))
        else:
            print(f"Error en la página {pagina}: Status {response.status_code}")
            print("Detalle:", response.text)
            break

        time.sleep(1.5)

    return pd.DataFrame(todos_imoveis)


def alinhar_com_gabarito(df_raspado, ruta_gabarito):
    df_gabarito = pd.read_csv(ruta_gabarito, nrows=0)

    mapa_colunas = {
        'ubicacion_latitude': 'ubication__latitude',
        'ubicacion_longitud': 'ubication__longitude',
        'ubicacion_HasHidden': 'ubication__hasHiddenAddress',
        'has_garage': 'has garage',
        'garage_price': 'garage price',
        'construction_year': 'construction year',
        'aircondicioning': 'air conditioning'
    }

    df_raspado = df_raspado.rename(columns=mapa_colunas)
    return df_raspado.reindex(columns=df_gabarito.columns)


def comparar_com_historico(df_hoy):
    lista_archivos = glob.glob('data/viviendas_cordoba_idealista_*.csv')
    lista_archivos = [f for f in lista_archivos if RUTA_SALIDA not in f]
    lista_archivos.sort(key=os.path.getmtime)

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
    comparar_com_historico(df_hoy)

    df_hoy.to_csv(RUTA_SALIDA, index=False, encoding='utf-8-sig')
    print(f"Base general actualizada y guardada en: {RUTA_SALIDA}")


if __name__ == "__main__":
    main()

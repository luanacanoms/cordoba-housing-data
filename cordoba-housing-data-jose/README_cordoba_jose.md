Dataset de Viviendas — Córdoba Capital (Idealista)

Extracción y estructuración de datos de viviendas en venta en Córdoba capital, obtenidos a través de la API oficial de Idealista (acceso académico), como apoyo a la investigación de tesis doctoral.

Contexto

Este repositorio forma parte de una colaboración de investigación con **José Cubells Puchades**, doctorando en la Universidad Pablo de Olavide (UPO), cuya tesis analiza los determinantes del precio de la vivienda mediante modelos de regresión lineal múltiple y redes neuronales, incorporando variables sociodemográficas.

Fuente de datos

Los datos se obtienen a través de la **API oficial de Idealista** (acceso concedido para fines académicos y de investigación), no mediante scraping directo de la web.

Metodología

1. **Autenticación:** obtención de token de acceso vía OAuth (client credentials)
2. **Extracción:** consulta paginada al endpoint de búsqueda, filtrando por ubicación (Córdoba capital, radio de 5 km), tipo de operación (venta) y tipo de propiedad (vivienda)
3. **Estandarización:** mapeo de los campos devueltos por la API al esquema de variables definido en colaboración con el investigador (geolocalización, superficie, habitaciones, baños, planta, ascensor, piscina, aire acondicionado, entre otros)
4. **Actualización:** el dataset se actualiza de forma periódica para reflejar los anuncios disponibles más recientes

Estructura del repositorio

```
├── notebooks/
│   └── extraccion_api_idealista.ipynb   # Script de extracción y limpieza
├── data/
│   └── viviendas_cordoba_idealista_*.csv   # Dataset actualizado (con fecha)
└── README.md
```

Variables incluidas

Identificador, URL, tipo de operación, precio, superficie construida, número de habitaciones y baños, planta, ascensor, piscina, terraza, garaje, año de construcción, orientación, aire acondicionado, geolocalización (latitud/longitud) y ubicación administrativa (distrito, municipio), entre otras.

Uso de los datos

Este repositorio es **privado** y de acceso restringido a los colaboradores del proyecto. Los datos se utilizan exclusivamente con fines de investigación académica, conforme a los términos de acceso concedidos por la API oficial de Idealista.

Colaboradora técnica

Luana de Morais Cano — Estudiante de Ingeniería Informática en Tecnologías de la Información, Universidad Miguel Hernández de Elche (UMH)

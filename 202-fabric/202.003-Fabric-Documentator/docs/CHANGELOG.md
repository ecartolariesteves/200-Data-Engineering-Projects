# Changelog

Todos los cambios notables del proyecto se documentan en este archivo.

---

## [1.0.0] - 2026-04-30 - Por Edgar Estevez

### Primera version estable

#### Secciones documentadas
- Portada con logo Nunsys y datos del cliente
- Indice estatico con numeros de pagina
- 1. Objeto con texto estandar
- 2. Fabric Workspace
  - 2.1 Areas de trabajo (tabla con todos los workspaces del tenant)
  - 2.2 Propiedades de la capacidad (SKU, region, estado, admins)
  - 2.3 Proceso Autoescalado con diagrama del Runbook
- 3. Capa de datos
  - 3.1 Nomenclatura (esquemas y tablas)
  - 3.2 Bronze con tabla de origen dinamica
  - 3.3 Silver
  - 3.4 Gold (dimensiones TD y hechos TH separados)
- 4. Capa de orquestacion
  - 4.1 Estructura de carpetas con diagrama
  - 4.2 Pipelines con diagrama del orquestador y sub-capas Bronze/Silver/Gold
  - 4.3 Almacenamiento con diagrama de Lakehouses y DW
  - 4.4 Canalizacion de despliegue con diagrama de stages
- 5. Capa de consumo
  - 5.1 Modelo Semantico con textos DirectLake/DW
  - 5.2 Power BI con pestanas en borrador
- Contraportada Nunsys

#### Caracteristicas tecnicas
- Deteccion automatica del workspace actual
- Deteccion automatica del pipeline orquestador (por patron de nombre)
- Deteccion automatica de carpetas Bronze/Silver/Gold
- Deteccion automatica de carpeta de almacenamiento
- Lectura de deployment pipelines y stages desde API
- Diagramas generados con Pillow (sin dependencias SVG)
- Logo cargado desde Lakehouse (sin base64 en el codigo)
- Textos tecnicos inteligentes segun tipo de artefacto
- Soporte para imagenes manuales (FiguraN.png) como override
- Deduplicacion de artefactos cuando hay multiples workspaces
- Archivos de celdas ejecutados via exec() desde Lakehouse

#### Limitaciones conocidas
- El indice es estatico (numeros de pagina aproximados)
- Las tablas y relaciones del Semantic Model no disponibles via API Push
- PDF deshabilitado (pendiente implementacion via LibreOffice)
- El diagrama de relaciones del Semantic Model esta en construccion

---

## [Proxima version]

### Planificado
- Diagrama de relaciones del Semantic Model (via XMLA)
- PDF con indice real via LibreOffice
- Instalador automatico desde GitHub (INSTALL.ipynb)
- Soporte para multiples lakehouses en capas separadas (Bronze/Silver/Gold independientes)

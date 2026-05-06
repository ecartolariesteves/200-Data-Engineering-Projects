# =============================================================================
# DIAGRAMA 4.3 -- Storage items (Lakehouses y DW)
# =============================================================================

def make_storage_diagram_png(lakehouses, warehouses):
    """
    Diagrama de los artefactos de almacenamiento:
    Lakehouse + SQL Endpoint por cada lakehouse real,
    mas DW si los hay.
    """
    from PIL import Image, ImageDraw, ImageFont
    import io

    C_MAGENTA   = (233, 30, 140)
    C_MAGENTA_D = (190, 24, 93)
    C_PINK      = (253, 240, 248)
    C_BLUE      = (59, 130, 246)
    C_BLUE_L    = (239, 246, 255)
    C_BLUE_D    = (30, 64, 175)
    C_GREEN     = (16, 185, 129)
    C_GREEN_L   = (236, 253, 245)
    C_GRAY      = (96, 96, 96)
    C_GRAY_L    = (220, 220, 220)
    C_WHITE     = (255, 255, 255)
    C_BG        = (255, 255, 255)

    STAGING = ("StagingLakehouseForDataflows", "StagingWarehouseForDataflows")
    real_lh = [lh for lh in lakehouses if not lh["name"].startswith(STAGING[0])]
    real_dw = [dw for dw in warehouses if not dw["name"].startswith(STAGING[1])]

    n_items = len(real_lh) * 2 + len(real_dw)  # LH + SQLEndpoint + DW
    ROW_H   = 44
    PAD     = 20
    COL_W   = 260
    ICON_W  = 36
    H       = PAD * 2 + max(n_items, 1) * (ROW_H + 8) + 20
    W       = PAD * 2 + ICON_W + 16 + COL_W
    W       = max(W, 340)
    H       = max(H, 120)
    SCALE   = 2

    img  = Image.new("RGB", (W*SCALE, H*SCALE), C_BG)
    draw = ImageDraw.Draw(img)

    def s(v): return v * SCALE

    def get_font(size, bold=False):
        try:
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                if bold else
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", s(size))
        except Exception:
            return ImageFont.load_default()

    def draw_row(y, icon_color, icon_label, name, item_type, is_endpoint=False):
        # Icono
        draw.rounded_rectangle(
            [s(PAD), s(y), s(PAD+ICON_W), s(y+ROW_H)],
            radius=s(6), fill=icon_color, outline=icon_color)
        draw.text((s(PAD + ICON_W//2), s(y + ROW_H//2)),
                  icon_label, fill=C_WHITE,
                  font=get_font(7, bold=True), anchor="mm")
        # Linea conectora si es endpoint
        if is_endpoint:
            draw.line(
                [(s(PAD + ICON_W//2), s(y - 8)),
                 (s(PAD + ICON_W//2), s(y))],
                fill=C_GRAY_L, width=s(1))
        # Caja de info
        bx = PAD + ICON_W + 12
        draw.rounded_rectangle(
            [s(bx), s(y+2), s(bx + COL_W), s(y+ROW_H-2)],
            radius=s(4), fill=C_PINK if not is_endpoint else C_BLUE_L,
            outline=C_MAGENTA if not is_endpoint else C_BLUE,
            width=s(1))
        # Tipo
        draw.text((s(bx + 8), s(y + 12)),
                  item_type, fill=C_MAGENTA if not is_endpoint else C_BLUE_D,
                  font=get_font(6, bold=True), anchor="lm")
        # Nombre (truncar si es largo)
        display = name if len(name) <= 32 else name[:30] + "..."
        draw.text((s(bx + 8), s(y + 28)),
                  display, fill=C_GRAY,
                  font=get_font(7), anchor="lm")

    y = PAD
    for lh in real_lh:
        draw_row(y, C_MAGENTA, "LH", lh["name"], "Lakehouse")
        y += ROW_H + 8
        ep = lh.get("sqlEndpoint", "") or ""
        ep_display = ep[:38] + "..." if len(ep) > 38 else ep if ep else "(SQL endpoint)"
        draw_row(y, C_BLUE, "SQL", ep_display, "Punto de conexion SQL Analytics",
                 is_endpoint=True)
        y += ROW_H + 16

    for dw in real_dw:
        draw_row(y, C_GREEN, "DW", dw["name"], "Data Warehouse")
        y += ROW_H + 8
        conn = dw.get("connectionString", "") or ""
        conn_display = conn[:38] + "..." if len(conn) > 38 else conn if conn else "(connection string)"
        draw_row(y, C_BLUE, "SQL", conn_display,
                 "Punto de conexion SQL Analytics", is_endpoint=True)
        y += ROW_H + 16

    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()


def get_storage_diagram_path(lakehouses, warehouses):
    import tempfile, os
    png = make_storage_diagram_png(lakehouses, warehouses)
    if not png:
        return None
    path = os.path.join(tempfile.gettempdir(), "storage_items.png")
    with open(path, "wb") as f:
        f.write(png)
    print("  OK Diagrama almacenamiento generado")
    return path


# =============================================================================
# DIAGRAMA 4.4 -- Deployment pipeline (stages)
# =============================================================================

def make_deployment_diagram_png(dp_name, stages):
    """
    Diagrama de despliegue: bloque por stage con flecha entre ellos.
    Leyendo stages reales de la API (sin hardcodear nombres).
    """
    from PIL import Image, ImageDraw, ImageFont
    import io

    C_MAGENTA   = (233, 30, 140)
    C_MAGENTA_D = (190, 24, 93)
    C_PINK      = (253, 240, 248)
    C_BLUE      = (59, 130, 246)
    C_BLUE_L    = (239, 246, 255)
    C_GREEN     = (16, 185, 129)
    C_GREEN_L   = (236, 253, 245)
    C_GRAY      = (96, 96, 96)
    C_WHITE     = (255, 255, 255)
    C_BG        = (255, 255, 255)

    if not stages:
        return None

    N       = len(stages)
    BOX_W   = 160; BOX_H = 80
    GAP     = 50;  PAD   = 30
    W       = PAD*2 + N*BOX_W + (N-1)*GAP
    H       = PAD*2 + BOX_H + 40
    SCALE   = 2

    img  = Image.new("RGB", (W*SCALE, H*SCALE), C_BG)
    draw = ImageDraw.Draw(img)

    def s(v): return v * SCALE

    def get_font(size, bold=False):
        try:
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                if bold else
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", s(size))
        except Exception:
            return ImageFont.load_default()

    # Titulo del pipeline
    draw.text((s(W//2), s(14)), dp_name,
              fill=C_MAGENTA, font=get_font(9, bold=True), anchor="mm")

    for i, stage in enumerate(stages):
        x  = PAD + i * (BOX_W + GAP)
        y  = 28
        sn = stage.get("displayName", f"Stage {i}")
        ws = stage.get("workspaceName", "")

        # Color segun posicion: primero=azul, ultimo=magenta, otros=gris
        if i == 0:
            fill_c    = C_BLUE_L
            outline_c = C_BLUE
            txt_c     = (30, 64, 175)
        elif i == N - 1:
            fill_c    = C_PINK
            outline_c = C_MAGENTA
            txt_c     = C_MAGENTA_D
        else:
            fill_c    = (245, 245, 245)
            outline_c = (150, 150, 150)
            txt_c     = C_GRAY

        # Caja del stage
        draw.rounded_rectangle(
            [s(x), s(y), s(x+BOX_W), s(y+BOX_H)],
            radius=s(8), fill=fill_c, outline=outline_c, width=s(2))

        # Nombre del stage
        draw.text((s(x+BOX_W//2), s(y+22)),
                  sn, fill=txt_c,
                  font=get_font(9, bold=True), anchor="mm")

        # Nombre del workspace (mas pequeno)
        ws_display = ws if len(ws) <= 20 else ws[:18] + "..."
        draw.text((s(x+BOX_W//2), s(y+40)),
                  ws_display, fill=C_GRAY,
                  font=get_font(7), anchor="mm")

        # Icono de check si no es el primero (implementado)
        if i > 0:
            draw.text((s(x+BOX_W//2), s(y+60)),
                      "Implementacion correcta", fill=C_GREEN,
                      font=get_font(6), anchor="mm")

        # Flecha hacia el siguiente
        if i < N - 1:
            ax1 = x + BOX_W + 4
            ax2 = x + BOX_W + GAP - 4
            ay  = y + BOX_H // 2
            draw.line([(s(ax1), s(ay)), (s(ax2-6), s(ay))],
                      fill=C_MAGENTA, width=s(2))
            draw.polygon([
                (s(ax2), s(ay)),
                (s(ax2-8), s(ay-5)),
                (s(ax2-8), s(ay+5))
            ], fill=C_MAGENTA)

    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()


def get_deployment_diagram_path(dp_name, stages, suffix="deploy"):
    import tempfile, os
    png = make_deployment_diagram_png(dp_name, stages)
    if not png:
        return None
    path = os.path.join(tempfile.gettempdir(), f"deployment_{suffix}.png")
    with open(path, "wb") as f:
        f.write(png)
    print(f"  OK Diagrama despliegue '{dp_name}' generado")
    return path


# =============================================================================
# BUILD SECTION 4.3 -- Almacenamiento
# =============================================================================

def build_storage_section(doc, storage_folder, lakehouses, warehouses,
                           figure_n=8):
    """
    Seccion 4.3 Almacenamiento (Lakehouse).
    storage_folder: nombre de la carpeta detectado automaticamente.
    """
    STAGING = ("StagingLakehouseForDataflows", "StagingWarehouseForDataflows")
    real_lh = [lh for lh in lakehouses if not lh["name"].startswith(STAGING[0])]
    real_dw = [dw for dw in warehouses  if not dw["name"].startswith(STAGING[1])]

    add_h2(doc, "4.3 Almacenamiento (Lakehouse)")

    # Construir variables dinamicas para el texto
    has_lh = bool(real_lh)
    has_dw = bool(real_dw)

    if has_lh and has_dw:
        artefactos  = "Lakehouses y Data Warehouses"
        combinacion = "los data lakes y los data warehouses"
    elif has_lh:
        artefactos  = "Lakehouses"
        combinacion = "los data lakes y los data warehouses"
    elif has_dw:
        artefactos  = "Data Warehouses"
        combinacion = "los data warehouses"
    else:
        artefactos  = "artefactos de almacenamiento"
        combinacion = "las capacidades de almacenamiento y analisis"

    # Resumen de artefactos para P2
    lh_names = ", ".join(lh["name"] for lh in real_lh)
    dw_names = ", ".join(dw["name"] for dw in real_dw)
    if has_lh and has_dw:
        resumen = f"un Lakehouse ({lh_names}) y un Data Warehouse ({dw_names})"
    elif has_lh:
        resumen = f"{'un' if len(real_lh)==1 else len(real_lh)} Lakehouse{'s' if len(real_lh)>1 else ''} ({lh_names})"
    elif has_dw:
        resumen = f"{'un' if len(real_dw)==1 else len(real_dw)} Data Warehouse{'s' if len(real_dw)>1 else ''} ({dw_names})"
    else:
        resumen = "los artefactos de almacenamiento definidos"

    # Parrafo 1
    add_body(doc, TEXT_ALMACENAMIENTO_P1.format(
        artefactos  = artefactos,
        combinacion = combinacion))
    doc.add_paragraph()

    # Parrafo 2
    add_body(doc, TEXT_ALMACENAMIENTO_P2.format(
        resumen_artefactos = resumen))
    doc.add_paragraph()

    # Parrafo 3
    add_body(doc, TEXT_ALMACENAMIENTO_P3)
    doc.add_paragraph()

    # Parrafo 4 -- carpeta
    add_body(doc, TEXT_ALMACENAMIENTO_P4.format(
        storage_folder = storage_folder))
    doc.add_paragraph()

    # Diagrama de artefactos de almacenamiento
    diag_path = get_storage_diagram_path(lakehouses, warehouses)
    insert_figure(doc, figure_n, diag_path,
        f"Figura {figure_n}. Nombres del lakehouse y del punto de "
        f"conexion SQL de {DOC_CLIENT}",
        width_inches=4.5)
    doc.add_paragraph()

    # Parrafo SQL Analytics
    add_body(doc, TEXT_ALMACENAMIENTO_SQL)
    doc.add_paragraph()


# =============================================================================
# BUILD SECTION 4.4 -- Canalizacion de despliegue
# =============================================================================

def build_deployment_section(doc, deployment_pipelines, figure_n=9):
    """
    Seccion 4.4 Canalizacion de despliegue.
    deployment_pipelines: lista devuelta por get_deployment_pipelines().
    """
    add_h2(doc, "4.4 Canalizacion de despliegue")

    if not deployment_pipelines:
        add_body(doc, "No se encontraron canalizaciones de despliegue.")
        return

    # Usar el primer deployment pipeline (normalmente solo hay uno)
    dp = deployment_pipelines[0]
    dp_name = dp.get("displayName", "DES - PROD")
    stages  = dp.get("stages", [])

    # Texto introductorio
    add_body(doc, TEXT_DESPLIEGUE_INTRO)
    doc.add_paragraph()

    # Diagrama deployment
    diag_path = get_deployment_diagram_path(dp_name, stages)
    insert_figure(doc, figure_n, diag_path,
        f"Figura {figure_n}. Canalizacion de despliegue "
        f"{dp_name}. Creacion inicial del entorno de Desarrollo "
        f"para garantizar consistencia estructural.",
        width_inches=5.5)
    doc.add_paragraph()

    add_body(doc, TEXT_DESPLIEGUE_P2)
    doc.add_paragraph()

    # Entornos definidos -- dinamico desde stages de la API
    add_body(doc, TEXT_DESPLIEGUE_ENTORNOS_INTRO)
    doc.add_paragraph()

    for stage in stages:
        order   = stage.get("order", 0)
        sname   = stage.get("displayName", f"Entorno {order+1}")
        ws_name = stage.get("workspaceName", "")
        desc    = STAGE_DESCRIPTIONS.get(order,
            "Entorno definido en el flujo de despliegue.")

        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        # Numero + nombre en negrita
        rb = p.add_run(f"{order+1}. Entorno de {sname}")
        rb.font.name = "Arial"; rb.font.size = Pt(9); rb.bold = True
        if ws_name:
            rp = p.add_run(f" ({ws_name})")
            rp.font.name = "Arial"; rp.font.size = Pt(9)
        r_desc = p.add_run(f": {desc}")
        r_desc.font.name = "Arial"; r_desc.font.size = Pt(9)

    doc.add_paragraph()

    # 4.4.1 Limitaciones
    add_h2(doc, "4.4.1 Limitaciones conocidas del pipeline de implementacion")
    add_body(doc, TEXT_LIMITACIONES_INTRO)
    doc.add_paragraph()

    # Elementos automaticos
    lbl_auto = doc.add_paragraph()
    r = lbl_auto.add_run("Elementos que pueden implementarse automaticamente:")
    r.font.name = "Arial"; r.font.size = Pt(9); r.bold = True; r.italic = True
    doc.add_paragraph()
    for item in ITEMS_AUTO:
        _add_bullet_plain(doc, item)
    doc.add_paragraph()

    # Elementos manuales
    lbl_man = doc.add_paragraph()
    r = lbl_man.add_run("Elementos que pueden requerir validacion o ajuste manual:")
    r.font.name = "Arial"; r.font.size = Pt(9); r.bold = True; r.italic = True
    doc.add_paragraph()
    for item in ITEMS_MANUAL:
        _add_bullet_plain(doc, item)
    doc.add_paragraph()

    # 4.4.2 Consideraciones
    add_h2(doc, "4.4.2 Consideraciones adicionales sobre Data Warehouse "
                "y parametrizacion de conexiones")

    for text in [TEXT_CONSIDERACIONES_P1, TEXT_CONSIDERACIONES_P2,
                 TEXT_CONSIDERACIONES_P3]:
        add_body(doc, text)
        doc.add_paragraph()

    add_body(doc, TEXT_CONSIDERACIONES_P4)
    doc.add_paragraph()
    for item in ITEMS_ESTRATEGIA:
        _add_bullet_plain(doc, item)
    doc.add_paragraph()

    for text in [TEXT_CONSIDERACIONES_P5, TEXT_CONSIDERACIONES_P6]:
        add_body(doc, text)
        doc.add_paragraph()


print("OK Funciones 4.3 y 4.4 de Celda 6e cargadas")

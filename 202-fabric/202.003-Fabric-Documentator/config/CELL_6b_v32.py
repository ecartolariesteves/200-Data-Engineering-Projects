import tempfile as _tempfile
import os as _os2

def get_figure_path(n):
    for ext in ["png", "jpg", "jpeg", "PNG", "JPG", "JPEG"]:
        path = f"{IMG_BASE_PATH}/Figura{n}.{ext}"
        if _os.path.exists(path):
            print(f"  Figura{n}: imagen manual -> {path}")
            return path
    print(f"  Figura{n}: no encontrada -> generando diagrama automatico")
    return None


def insert_figure(doc, figure_n, auto_diagram_path, caption_text,
                  width_inches=5.8):
    manual_path = get_figure_path(figure_n)
    img_path    = manual_path or auto_diagram_path
    if not img_path:
        add_body(doc, f"[{caption_text} -- imagen no disponible]")
        return
    try:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(img_path, width=Inches(width_inches))
    except Exception as e:
        add_body(doc, f"[Error insertando imagen: {e}]")
        return
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cr  = cap.add_run(caption_text)
    cr.font.size      = Pt(8)
    cr.font.italic    = True
    cr.font.color.rgb = GRAY_MID


# =============================================================================
# ARCHITECTURE DIAGRAM
# =============================================================================

def make_architecture_diagram_png(cap_info, ws_list):
    from PIL import Image, ImageDraw, ImageFont
    import io

    C_ACCENT    = (0, 120, 212)
    C_ACCENT_D  = (0, 90, 160)
    C_LIGHT     = (240, 246, 255)
    C_BLUE      = (59, 130, 246)
    C_BLUE_L    = (239, 246, 255)
    C_BLUE_D    = (30, 64, 175)
    C_PURPLE    = (124, 58, 237)
    C_WHITE     = (255, 255, 255)

    N           = len(ws_list)
    WS_W        = 200; WS_GAP  = 16; PADDING = 16
    LEFT_W      = 160; ARROW_W = 30
    ARTIFACT_H  = 26;  HEADER_H = 42; BANNER_H = 36

    max_art = max(
        sum([ws.get("_has_lakehouse", False), ws.get("_has_dw", False),
             ws.get("_has_pipelines", False), ws.get("_has_notebooks", False),
             ws.get("_has_semantic_models", False), ws.get("_has_reports", False)])
        for ws in ws_list
    ) if ws_list else 3

    WS_H    = HEADER_H + max_art * ARTIFACT_H + PADDING
    FAB_W   = N * WS_W + (N - 1) * WS_GAP + PADDING * 2
    FAB_H   = BANNER_H + WS_H + PADDING * 2
    TOTAL_W = LEFT_W + ARROW_W + FAB_W + 20
    TOTAL_H = max(FAB_H + 20, 220)
    SCALE   = 2

    img  = Image.new("RGB", (TOTAL_W * SCALE, TOTAL_H * SCALE), (255, 255, 255))
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

    def rect(x, y, w, h, fill, outline, radius=8, width=2):
        draw.rounded_rectangle(
            [s(x), s(y), s(x+w), s(y+h)],
            radius=s(radius), fill=fill, outline=outline, width=s(width)//2)

    def txt(t, x, y, color, size=10, bold=False):
        draw.text((s(x), s(y)), t, fill=color,
                  font=get_font(size, bold), anchor="mm")

    AZ_X = 10; AZ_Y = 10; AZ_W = LEFT_W; AZ_H = TOTAL_H - 20
    FAB_X = AZ_X + AZ_W + ARROW_W; FAB_Y = 10
    ARROW_Y = FAB_Y + FAB_H // 2

    cap_name = cap_info.get("displayName", "Fabric Capacity")[:16]
    cap_sku  = cap_info.get("sku", "--")

    rect(AZ_X, AZ_Y, AZ_W, AZ_H, C_BLUE_L, C_BLUE, radius=10)
    txt("Azure Subscription", AZ_X+AZ_W//2, AZ_Y+14, C_BLUE_D, size=9, bold=True)
    RG_X = AZ_X+10; RG_Y = AZ_Y+28; RG_W = AZ_W-20; RG_H = AZ_H-38
    rect(RG_X, RG_Y, RG_W, RG_H, (219,234,254), C_BLUE, radius=8, width=1)
    txt("Resource Group", RG_X+RG_W//2, RG_Y+14, C_BLUE_D, size=8, bold=True)
    FC_X = RG_X+8; FC_Y = RG_Y+26; FC_W = RG_W-16; FC_H = RG_H-34
    rect(FC_X, FC_Y, FC_W, FC_H, C_ACCENT, C_ACCENT_D, radius=6)
    txt("Fabric Capacity", FC_X+FC_W//2, FC_Y+14, C_WHITE, size=8, bold=True)
    rect(FC_X+6, FC_Y+24, FC_W-12, 18, (255,255,255), (255,255,255), radius=4, width=0)
    txt(cap_name, FC_X+FC_W//2, FC_Y+33, C_ACCENT, size=7)
    rect(FC_X+6, FC_Y+46, FC_W-12, 18, (255,255,255), (255,255,255), radius=4, width=0)
    txt(cap_sku, FC_X+FC_W//2, FC_Y+55, C_ACCENT, size=9, bold=True)

    draw.line([(s(AZ_X+AZ_W), s(ARROW_Y)), (s(FAB_X-4), s(ARROW_Y))],
              fill=C_ACCENT, width=s(2))
    draw.polygon([
        (s(FAB_X), s(ARROW_Y)),
        (s(FAB_X-8), s(ARROW_Y-4)),
        (s(FAB_X-8), s(ARROW_Y+4))
    ], fill=C_ACCENT)

    rect(FAB_X, FAB_Y, FAB_W, FAB_H, C_LIGHT, C_ACCENT, radius=10)
    txt("Microsoft Fabric - Workspaces",
        FAB_X+FAB_W//2, FAB_Y+18, C_ACCENT_D, size=10, bold=True)

    for i, ws in enumerate(ws_list):
        WX = FAB_X + PADDING + i * (WS_W + WS_GAP)
        WY = FAB_Y + BANNER_H + PADDING // 2
        wlabel = ws["name"] if len(ws["name"]) <= 22 else ws["name"][:20] + "..."
        rect(WX, WY, WS_W, WS_H, C_WHITE, C_ACCENT, radius=8)
        rect(WX, WY, WS_W, HEADER_H, C_ACCENT, C_ACCENT, radius=8)
        draw.rectangle([s(WX), s(WY+HEADER_H-8), s(WX+WS_W), s(WY+HEADER_H)],
                       fill=C_ACCENT)
        txt(wlabel, WX+WS_W//2, WY+HEADER_H//2, C_WHITE, size=8, bold=True)
        artifacts = []
        if ws.get("_has_lakehouse"):        artifacts.append("Lakehouse")
        if ws.get("_has_dw"):               artifacts.append("Data Warehouse")
        if ws.get("_has_pipelines"):        artifacts.append("Pipelines")
        if ws.get("_has_notebooks"):        artifacts.append("Notebooks")
        if ws.get("_has_semantic_models"):  artifacts.append("Semantic Models")
        if ws.get("_has_reports"):          artifacts.append("Reports")
        for j, art in enumerate(artifacts):
            AY = WY + HEADER_H + j * ARTIFACT_H + 4
            rect(WX+8, AY, WS_W-16, ARTIFACT_H-4, C_LIGHT, C_LIGHT, radius=4, width=0)
            txt(art, WX+WS_W//2, AY+(ARTIFACT_H-4)//2, C_PURPLE, size=8)

    img = img.resize((TOTAL_W, TOTAL_H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()


def get_architecture_diagram_path(cap_info, ws_list):
    png = make_architecture_diagram_png(cap_info, ws_list)
    if not png:
        return None
    path = _os.path.join(_tempfile.gettempdir(), "fabric_architecture.png")
    with open(path, "wb") as f:
        f.write(png)
    print("  OK Diagrama arquitectura generado")
    return path


# =============================================================================
# FOLDER STRUCTURE DIAGRAM -- FIX: cajas mas anchas, texto ajustado
# =============================================================================

def make_folder_diagram_png(ws_name, folder_names):
    """
    Diagrama de estructura de carpetas del workspace.
    Detecta automaticamente si hay carpeta padre (ej: 1-ETL)
    y la muestra en el diagrama.
    Estructura posible:
      A) Workspace -> Bronze/Silver/Gold (directo)
      B) Workspace -> ETL_Parent -> Bronze/Silver/Gold
    """
    from PIL import Image, ImageDraw, ImageFont
    import io
 
    C_ACCENT    = (0, 120, 212)
    C_ACCENT_D  = (0, 90, 160)
    C_LIGHT     = (240, 246, 255)
    C_GRAY      = (96, 96, 96)
    C_GRAY_L    = (220, 220, 220)
    C_WHITE     = (255, 255, 255)
    C_BG        = (255, 255, 255)
 
    bronze_n   = folder_names.get("bronze",     "001 - Data - Bronze")
    silver_n   = folder_names.get("silver",     "002 - Data - Silver")
    gold_n     = folder_names.get("gold",       "003 - Data - Gold")
    etl_parent = folder_names.get("etl_parent", None)
 
    # Si hay carpeta padre, el canvas necesita mas espacio
    has_parent = bool(etl_parent)
    W     = 750 if has_parent else 680
    H     = 200
    SCALE = 2
 
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
 
    def folder_box(x, y, w, h, label, sub=None):
        # Sombra
        draw.rounded_rectangle(
            [s(x+2), s(y+2), s(x+w+2), s(y+h+2)],
            radius=s(4), fill=C_GRAY_L)
        # Caja
        draw.rounded_rectangle(
            [s(x), s(y), s(x+w), s(y+h)],
            radius=s(4), fill=C_LIGHT, outline=C_ACCENT, width=s(1))
        # Pestana superior
        draw.rounded_rectangle(
            [s(x), s(y-8), s(x+min(w//2, 60)), s(y+4)],
            radius=s(3), fill=C_ACCENT, outline=C_ACCENT, width=s(1))
        # Texto principal
        font_main = get_font(7, bold=True)
        display = label
        while len(display) > 3:
            bbox = draw.textbbox((0, 0), display, font=font_main)
            if (bbox[2] - bbox[0]) <= s(w - 8):
                break
            display = display[:-4] + "..."
        draw.text((s(x+w//2), s(y+h//2 - (5 if sub else 0))),
                  display, fill=C_ACCENT_D, font=font_main, anchor="mm")
        if sub:
            font_sub = get_font(6)
            draw.text((s(x+w//2), s(y+h//2+9)),
                      sub, fill=C_GRAY, font=font_sub, anchor="mm")
 
    def arrow_h(x1, y, x2):
        draw.line([(s(x1), s(y)), (s(x2-6), s(y))],
                  fill=C_ACCENT, width=s(2))
        draw.polygon([
            (s(x2), s(y)), (s(x2-8), s(y-4)), (s(x2-8), s(y+4))
        ], fill=C_ACCENT)
 
    def branch_v(x, y1, y2):
        draw.line([(s(x), s(y1)), (s(x), s(y2))],
                  fill=C_ACCENT, width=s(1))
 
    def branch_h(x1, x2, y):
        draw.line([(s(x1), s(y)), (s(x2-4), s(y))],
                  fill=C_ACCENT, width=s(1))
        draw.polygon([
            (s(x2), s(y)), (s(x2-6), s(y-3)), (s(x2-6), s(y+3))
        ], fill=C_ACCENT)
 
    ws_label = ws_name if len(ws_name) <= 18 else ws_name[:16] + "..."
 
    if has_parent:
        # Estructura: Workspace -> ETL_Parent -> [Bronze, Silver, Gold]
        # Workspace
        folder_box(10, 70, 100, 50, ws_label, "Workspace")
        arrow_h(112, 95, 148)
 
        # ETL Parent
        etl_label = etl_parent if len(etl_parent) <= 14 else etl_parent[:12]+"..."
        folder_box(150, 70, 90, 50, etl_label, "Carpeta")
        arrow_h(242, 95, 278)
 
        # Bifurcacion vertical
        branch_v(293, 50, 148)
 
        # Bronze
        branch_h(293, 313, 55)
        folder_box(313, 32, 420, 44, bronze_n, "Carga datos sin procesar")
 
        # Silver
        branch_h(293, 313, 95)
        folder_box(313, 73, 420, 44, silver_n, "Transformacion y limpieza")
 
        # Gold
        branch_h(293, 313, 143)
        folder_box(313, 120, 420, 44, gold_n, "Tablas finales y modelo")
 
    else:
        # Estructura: Workspace -> Data -> [Bronze, Silver, Gold]
        folder_box(10, 70, 100, 50, ws_label, "Workspace")
        arrow_h(112, 95, 148)
 
        folder_box(150, 70, 72, 50, "Data", "Carpeta")
        arrow_h(224, 95, 258)
 
        branch_v(273, 50, 148)
 
        branch_h(273, 293, 55)
        folder_box(293, 32, 420, 44, bronze_n, "Carga datos sin procesar")
 
        branch_h(273, 293, 95)
        folder_box(293, 73, 420, 44, silver_n, "Transformacion y limpieza")
 
        branch_h(273, 293, 143)
        folder_box(293, 120, 420, 44, gold_n, "Tablas finales y modelo")
 
    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()
 
 
def get_folder_diagram_path(ws_name, folder_names):
    import tempfile, os
    png = make_folder_diagram_png(ws_name, folder_names)
    if not png:
        return None
    path = os.path.join(tempfile.gettempdir(), "folder_structure.png")
    with open(path, "wb") as f:
        f.write(png)
    print("  OK Diagrama carpetas generado")
    return path
 
def get_folder_diagram_path(ws_name, folder_names):
    import tempfile, os
    png = make_folder_diagram_png(ws_name, folder_names)
    if not png:
        return None
    path = os.path.join(tempfile.gettempdir(), "folder_structure.png")
    with open(path, "wb") as f:
        f.write(png)
    print("  OK Diagrama carpetas generado")
    return path
 
def get_folder_diagram_path(ws_name, folder_names):
    import tempfile, os
    png = make_folder_diagram_png(ws_name, folder_names)
    if not png:
        return None
    path = os.path.join(tempfile.gettempdir(), "folder_structure.png")
    with open(path, "wb") as f:
        f.write(png)
    print("  OK Diagrama carpetas generado")
    return path

def get_folder_diagram_path(ws_name, folder_names):
    png = make_folder_diagram_png(ws_name, folder_names)
    if not png:
        return None
    path = _os.path.join(_tempfile.gettempdir(), "folder_structure.png")
    with open(path, "wb") as f:
        f.write(png)
    print("  OK Diagrama carpetas generado")
    return path


# =============================================================================
# RUNBOOK DIAGRAM
# =============================================================================

def make_runbook_diagram_png(cap_info, autoscale_cfg):
    from PIL import Image, ImageDraw, ImageFont
    import io

    C_ACCENT    = (0, 120, 212)
    C_ACCENT_D  = (0, 90, 160)
    C_LIGHT     = (240, 246, 255)
    C_BLUE_L    = (239, 246, 255)
    C_BLUE_D    = (30, 64, 175)
    C_GRAY      = (64, 64, 64)
    C_WHITE     = (255, 255, 255)

    W = 620; H = 220; SCALE = 2
    img  = Image.new("RGB", (W*SCALE, H*SCALE), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    hora_ini = autoscale_cfg.get("hora_inicio", "6:00")
    hora_par = autoscale_cfg.get("hora_parada", "7:00")
    rb_name  = autoscale_cfg.get("runbook_name", "Runbook")
    rb_short = rb_name[:24] + "..." if len(rb_name) > 24 else rb_name
    cap_name = cap_info.get("displayName", "Fabric Capacity")[:14]
    cap_sku  = cap_info.get("sku", "--")

    def s(v): return v * SCALE

    def get_font(size, bold=False):
        try:
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                if bold else
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", s(size))
        except Exception:
            return ImageFont.load_default()

    def rect(x, y, w, h, fill, outline, radius=6, width=2):
        draw.rounded_rectangle(
            [s(x), s(y), s(x+w), s(y+h)],
            radius=s(radius), fill=fill, outline=outline, width=s(width)//2)

    def txt(t, x, y, color, size=8, bold=False):
        draw.text((s(x), s(y)), t, fill=color,
                  font=get_font(size, bold), anchor="mm")

    def arrow(x1, y1, x2, y2):
        draw.line([(s(x1), s(y1)), (s(x2), s(y2))],
                  fill=C_ACCENT, width=s(2))
        import math
        dx = x2-x1; dy = y2-y1
        length = math.sqrt(dx**2 + dy**2)
        if length == 0:
            return
        ux = dx/length; uy = dy/length
        px = -uy; py = ux
        draw.polygon([
            (s(x2), s(y2)),
            (s(x2-ux*8+px*4), s(y2-uy*8+py*4)),
            (s(x2-ux*8-px*4), s(y2-uy*8-py*4))
        ], fill=C_ACCENT)

    rect(10, 70, 130, 80, C_BLUE_L, (59, 130, 246))
    txt("Azure Automation", 75, 95,  C_BLUE_D, size=8, bold=True)
    txt("Account",           75, 108, C_BLUE_D, size=7)
    txt(rb_short[:20],       75, 122, C_BLUE_D, size=6)

    arrow(140, 90,  178, 68)
    arrow(140, 120, 178, 142)

    rect(182, 50,  110, 44, C_LIGHT, C_ACCENT)
    txt("Schedule",              237, 64,  C_ACCENT, size=8, bold=True)
    txt(f"{hora_ini} Reanudar",  237, 78,  C_GRAY,    size=7)

    rect(182, 116, 110, 44, C_LIGHT, C_ACCENT)
    txt("Schedule",              237, 130, C_ACCENT, size=8, bold=True)
    txt(f"{hora_par} Suspender", 237, 144, C_GRAY,    size=7)

    arrow(292, 72,  328, 90)
    arrow(292, 138, 328, 110)

    rect(332, 76, 110, 58, C_ACCENT, C_ACCENT_D)
    txt("Runbook Python", 387, 97,  C_WHITE, size=8, bold=True)
    txt(rb_short[:20],   387, 112, C_WHITE, size=6)

    arrow(442, 90,  478, 70)
    arrow(442, 110, 478, 140)

    rect(482, 50,  126, 44, C_LIGHT, C_ACCENT)
    txt(f"{cap_name} {cap_sku}", 545, 64,  C_ACCENT, size=7, bold=True)
    txt(f"Active  {hora_ini}h",  545, 78,  C_GRAY,    size=7)

    rect(482, 116, 126, 44, C_LIGHT, C_ACCENT)
    txt(f"{cap_name} {cap_sku}", 545, 130, C_ACCENT, size=7, bold=True)
    txt(f"Paused  {hora_par}h",  545, 144, C_GRAY,    size=7)

    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()


def get_runbook_diagram_path(cap_info, autoscale_cfg):
    png = make_runbook_diagram_png(cap_info, autoscale_cfg)
    if not png:
        return None
    path = _os.path.join(_tempfile.gettempdir(), "runbook_diagram.png")
    with open(path, "wb") as f:
        f.write(png)
    print("  OK Diagrama runbook generado")
    return path

# =============================================================================
# Diagramas "En construccion" y "BORRADOR"
# =============================================================================
 
def make_under_construction_png(label="Diagrama en construccion",
                                 width=500, height=200):
    """
    Imagen con mensaje de 'En construccion'.
    Fondo rosa, borde magenta, icono y texto centrado.
    """
    from PIL import Image, ImageDraw, ImageFont
    import io
 
    C_ACCENT    = (0, 120, 212)
    C_ACCENT_D  = (0, 90, 160)
    C_LIGHT     = (240, 246, 255)
    C_GRAY      = (96, 96, 96)
    C_WHITE     = (255, 255, 255)
    SCALE       = 2
 
    W = width; H = height
    img  = Image.new("RGB", (W*SCALE, H*SCALE), C_LIGHT)
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
 
    # Borde exterior
    draw.rounded_rectangle(
        [s(4), s(4), s(W-4), s(H-4)],
        radius=s(12), outline=C_ACCENT, width=s(2))
 
    # Borde interior punteado simulado con rectangulo
    draw.rounded_rectangle(
        [s(10), s(10), s(W-10), s(H-10)],
        radius=s(8), outline=C_ACCENT_D, width=s(1))
 
    # Icono grande centrado (simbolo de construccion)
    icon_y = H // 2 - 28
    draw.text((s(W//2), s(icon_y)),
              "[ ]", fill=C_ACCENT,
              font=get_font(28, bold=True), anchor="mm")
 
    # Texto principal
    draw.text((s(W//2), s(H//2 + 10)),
              label, fill=C_ACCENT_D,
              font=get_font(11, bold=True), anchor="mm")
 
    # Subtexto
    draw.text((s(W//2), s(H//2 + 28)),
              "Imagen pendiente de incorporar",
              fill=C_GRAY, font=get_font(8), anchor="mm")
 
    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()
 
 
def make_draft_png(tab_name="Pestana",
                   width=560, height=320):
    """
    Imagen BORRADOR para pestanas de Power BI.
    Simula el marco de un informe con marca de agua BORRADOR.
    """
    from PIL import Image, ImageDraw, ImageFont
    import io
 
    C_ACCENT    = (0, 120, 212)
    C_ACCENT_D  = (0, 90, 160)
    C_LIGHT     = (240, 246, 255)
    C_GRAY      = (150, 150, 150)
    C_GRAY_L    = (220, 220, 220)
    C_DARK      = (50, 50, 50)
    C_WHITE     = (255, 255, 255)
    SCALE       = 2
 
    W = width; H = height
    img  = Image.new("RGB", (W*SCALE, H*SCALE), C_WHITE)
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
 
    # Marco principal del reporte
    draw.rounded_rectangle(
        [s(4), s(4), s(W-4), s(H-4)],
        radius=s(8), outline=C_GRAY_L, width=s(2),
        fill=C_WHITE)
 
    # Barra superior (simulando cabecera Power BI)
    draw.rectangle([s(4), s(4), s(W-4), s(36)], fill=C_ACCENT)
 
    # Titulo en la barra
    display_name = tab_name if len(tab_name) <= 30 else tab_name[:28] + "..."
    draw.text((s(20), s(20)), display_name,
              fill=C_WHITE, font=get_font(10, bold=True), anchor="lm")
 
    # Pestanas simuladas
    for i, tab_label in enumerate(["Principal", "Tab 2", "Tab 3"]):
        tx = 20 + i * 80
        draw.rounded_rectangle(
            [s(tx), s(36), s(tx+72), s(54)],
            radius=s(4),
            fill=C_ACCENT_D if i == 0 else C_GRAY_L,
            outline=C_GRAY_L, width=s(1))
        draw.text((s(tx+36), s(45)),
                  tab_label,
                  fill=C_WHITE if i == 0 else C_DARK,
                  font=get_font(7), anchor="mm")
 
    # Area de contenido con placeholder de graficos
    content_y = 60
    # Placeholder grafico 1 (izquierda)
    draw.rounded_rectangle(
        [s(16), s(content_y), s(W//2-8), s(content_y+120)],
        radius=s(6), fill=C_LIGHT, outline=C_GRAY_L, width=s(1))
    draw.text((s(W//4), s(content_y+60)),
              "Grafico 1", fill=C_GRAY,
              font=get_font(9), anchor="mm")
 
    # Placeholder grafico 2 (derecha)
    draw.rounded_rectangle(
        [s(W//2+8), s(content_y), s(W-16), s(content_y+120)],
        radius=s(6), fill=C_LIGHT, outline=C_GRAY_L, width=s(1))
    draw.text((s(W*3//4), s(content_y+60)),
              "Grafico 2", fill=C_GRAY,
              font=get_font(9), anchor="mm")
 
    # Placeholder tabla inferior
    draw.rounded_rectangle(
        [s(16), s(content_y+130), s(W-16), s(H-16)],
        radius=s(6), fill=C_LIGHT, outline=C_GRAY_L, width=s(1))
    draw.text((s(W//2), s(content_y+165)),
              "Tabla / Detalle", fill=C_GRAY,
              font=get_font(9), anchor="mm")
 
    # Marca de agua BORRADOR diagonal
    # Rotar imagen para el texto diagonal
    from PIL import Image as PILImage
    watermark = PILImage.new("RGBA", (W*SCALE, H*SCALE), (0, 0, 0, 0))
    wdraw     = ImageDraw.Draw(watermark)
    try:
        wfont = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s(40))
    except Exception:
        wfont = ImageFont.load_default()
    wdraw.text((s(W//2), s(H//2)), "BORRADOR",
               fill=(233, 30, 140, 60),
               font=wfont, anchor="mm")
    watermark = watermark.rotate(30, expand=False)
    img_rgba  = img.convert("RGBA")
    img_rgba.paste(watermark, (0, 0), watermark)
    img       = img_rgba.convert("RGB")
 
    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(150, 150))
    return buf.getvalue()
 
 
def get_under_construction_path(label="Diagrama en construccion",
                                 suffix="construction"):
    import tempfile, os
    png = make_under_construction_png(label)
    if not png:
        return None
    path = os.path.join(tempfile.gettempdir(), f"img_{suffix}.png")
    with open(path, "wb") as f:
        f.write(png)
    return path
 
 
def get_draft_path(tab_name="Pestana", suffix="draft"):
    import tempfile, os
    png = make_draft_png(tab_name)
    if not png:
        return None
    path = os.path.join(tempfile.gettempdir(), f"img_{suffix}.png")
    with open(path, "wb") as f:
        f.write(png)
    return path
 
print("OK Celda 6b cargada -- diagramas Pillow v3.2")

# =============================================================================
# REEMPLAZA build_semantic_models_section en CELL_6e_v33.py
# Y AÑADE build_consumption_section
# =============================================================================

def build_semantic_models_section(doc, all_semantic_models, figure_start=10):
    """
    Seccion 5. CAPA DE CONSUMO / MODELO SEMANTICO
    5.1 por cada modelo semantico
    5.2 Power BI con pestanas configurables
    """
    add_h1(doc, "5. Capa de Consumo / Modelo Semantico")

    if not all_semantic_models:
        if POWERBI_TABS:
            add_h1(doc, "5. Capa de Consumo / Modelo Semantico")
            _build_powerbi_section(doc, figure_start)
        return

    # Deduplicar
    seen = set(); unique_sm = []
    for m in all_semantic_models:
        if m.get("id") not in seen:
            seen.add(m.get("id")); unique_sm.append(m)

    fig_n = figure_start

    # Filtrar SM de Staging
    EXCLUDE_SM = (
        "DataflowsStagingLakehouse",
        "DataflowsStagingWarehouse",
        "StagingLakehouseForDataflows",
        "StagingWarehouseForDataflows",
    )
    unique_sm = [
        m for m in unique_sm
        if not any(m.get("name","").startswith(p) for p in EXCLUDE_SM)
    ]

    # Filtrar SM automaticos de Fabric
    # Solo excluir SM con mismo nombre que un Lakehouse
    # Los SM con nombre igual a DW pueden ser modelos reales -- mantener
    lh_names = set()
    for ws in project_data.get("workspaces", []):
        for lh in ws.get("lakehouses", []):
            lh_names.add(lh.get("name","").lower())

    unique_sm = [
        m for m in unique_sm
        if m.get("name","").lower() not in lh_names
    ]

    if not unique_sm:
        if POWERBI_TABS:
            add_h1(doc, "5. Capa de Consumo / Modelo Semantico")
            _build_powerbi_section(doc, figure_start)
        return

    for idx, m in enumerate(sorted(unique_sm, key=lambda x: x.get("name",""))):
        sm_name     = m.get("name", "")
        details     = m.get("details", {})
        storage     = details.get("storageMode", "")
        datasources = details.get("datasources", [])
        refresh_sch = details.get("refreshSchedule", {})
        last_refresh = details.get("lastRefresh", {})

        # 5.1 MODELO SEMANTICO
        section_num = f"5.{idx+1}"
        add_h2(doc, f"{section_num} Modelo Semantico - {sm_name}")
        doc.add_paragraph()

        # Texto introductorio
        add_body(doc, TEXT_SM_INTRO.format(nombre=sm_name))
        doc.add_paragraph()

        # Texto tecnico segun origen
        has_lh = any("lake" in s.get("type","").lower() or
                     "onelake" in s.get("type","").lower()
                     for s in datasources)
        has_dw = any("warehouse" in s.get("type","").lower() or
                     "sql" in s.get("type","").lower()
                     for s in datasources)

        if storage == "DirectLake" or has_lh:
            _add_technical_text(doc, TEXT_SM_DIRECTLAKE.format(nombre=sm_name))
        elif has_dw:
            _add_technical_text(doc, TEXT_SM_DW.format(nombre=sm_name))
        doc.add_paragraph()

        # Tabla propiedades
        configured_by = details.get("configuredBy","") or m.get("configuredBy","--")
        created_date  = (details.get("createdDate","") or
                         m.get("createdDate","") or "--")[:10]
        src_names = ", ".join(
            s.get("name","") or s.get("type","")
            for s in datasources if s.get("name","") or s.get("type","")
        ) or "--"
        src_types = ", ".join(
            s.get("type","") for s in datasources if s.get("type","")
        ) or "--"
        rs_enabled = refresh_sch.get("enabled", False)
        rs_days    = ", ".join(refresh_sch.get("days",[])) or "--"
        rs_times   = ", ".join(refresh_sch.get("times",[])) or "--"
        rs_tz      = refresh_sch.get("localTimeZoneId","UTC")
        lr_start   = (last_refresh.get("startTime","") or "--")[:19].replace("T"," ")
        lr_status  = last_refresh.get("status","--")
        lr_type    = last_refresh.get("refreshType","--")

        meta_table(doc, {
            "Nombre":              sm_name,
            "ID":                  m.get("id","--"),
            "Configurado por":     configured_by,
            "Modo almacenamiento": storage or "--",
            "Creado":              created_date,
            "Tipo de origen":      src_types,
            "Origen":              src_names,
            "Refresh habilitado":  "Si" if rs_enabled else "No",
            "Dias de refresh":     rs_days if rs_enabled else "--",
            "Horas de refresh":    rs_times if rs_enabled else "--",
            "Zona horaria":        rs_tz if rs_enabled else "--",
            "Ultimo refresh":      f"{lr_start} ({lr_status})" if lr_start != "--" else "--",
            "Tipo de refresh":     lr_type,
        })

        # Relaciones
        rels = m.get("relationships", [])
        if rels:
            add_body(doc, f"Relaciones entre tablas ({len(rels)}):")
            doc.add_paragraph()
            schema_table(doc,
                ["Tabla Origen","Col Origen","Tabla Destino","Col Destino"],
                sorted([
                    [r.get("fromTable",""), r.get("fromColumn",""),
                     r.get("toTable",""),   r.get("toColumn","")]
                    for r in rels
                ], key=lambda r: (r[0], r[2])))

        # Diagrama del modelo -- en construccion hasta tener los datos
        construction_path = get_under_construction_path(
            label="Diagrama de relaciones del modelo semantico",
            suffix=f"sm_{idx}")
        insert_figure(doc, fig_n, construction_path,
            f"Figura {fig_n}. Diagrama de relaciones del modelo "
            f"semantico {sm_name}.",
            width_inches=5.0)
        fig_n += 1
        doc.add_paragraph()

    # 5.2 Power BI
    _build_powerbi_section(doc, fig_n)


def _build_powerbi_section(doc, figure_start):
    """Seccion 5.2 Power BI con pestanas configurables."""

    add_h2(doc, "5.2 Power BI")
    add_body(doc, TEXT_POWERBI_INTRO)
    doc.add_paragraph()

    # Una subseccion por cada pestana definida en POWERBI_TABS
    for i, tab in enumerate(POWERBI_TABS):
        tab_name = tab.get("name", f"Pestana {i+1}")
        tab_desc = tab.get("description", "")
        fig_n    = figure_start + i

        add_h2(doc, f"5.2.{i+1} {tab_name}")

        if tab_desc:
            add_body(doc, tab_desc)
        doc.add_paragraph()

        # Figura BORRADOR -- el analista la reemplaza con la imagen real
        # Si existe Figura manual (ej: Figura11.png) la usa; si no, genera BORRADOR
        manual = get_figure_path(fig_n)
        if manual:
            img_path = manual
        else:
            img_path = get_draft_path(tab_name, suffix=f"tab_{i}")

        if img_path:
            try:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.add_run().add_picture(img_path, width=Inches(5.5))
            except Exception as e:
                add_body(doc, f"[Error insertando imagen: {e}]")
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cr = cap.add_run(
            f"Figura {fig_n}. {tab_name} -- {'Captura de pantalla' if manual else 'BORRADOR'}")
        cr.font.size = Pt(8); cr.font.italic = True
        if not manual:
            cr.font.color.rgb = MAGENTA  # magenta para indicar que es borrador
        else:
            cr.font.color.rgb = GRAY_MID

        doc.add_paragraph()


print("OK Seccion 5 Capa de Consumo cargada -- 5.1 Modelo Semantico + 5.2 Power BI")

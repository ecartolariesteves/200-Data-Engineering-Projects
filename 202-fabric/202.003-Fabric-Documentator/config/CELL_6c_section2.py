import tempfile as _tempfile
import os as _os2
 
# Guardar logo en disco una sola vez al cargar la celda
_LOGO_TMP = None
if LOGO_BYTES:
    _ext = "png" if b'PNG' in LOGO_BYTES[:8] else "jpg"
    _LOGO_TMP = _os2.path.join(_tempfile.gettempdir(), f"nunsys_logo_doc.{_ext}")
    with open(_LOGO_TMP, "wb") as _lf:
        _lf.write(LOGO_BYTES)
    print(f"  Logo guardado: {_LOGO_TMP}")
else:
    print("  AVISO Sin logo")
 
 
def build_cover(doc, data):
    logo_p = doc.add_paragraph()
    logo_p.paragraph_format.space_after = Pt(0)
    logo_p.add_run().add_picture(_LOGO_TMP, width=Inches(1.8))
    for _ in range(6):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
    t   = doc.add_paragraph()
    t.paragraph_format.space_after = Pt(6)
    run = t.add_run("Documentación\ntécnica")
    run.font.name = "Arial"; run.font.size = Pt(36)
    run.font.bold = True; run.font.color.rgb = GRAY_DARK
    doc.add_paragraph()
    sub = doc.add_paragraph()
    r1  = sub.add_run(f"{DOC_CLIENT}\nRef.: {DOC_REF}")
    r1.font.name = "Arial"; r1.font.size = Pt(11)
    r1.font.color.rgb = GRAY_MID
    p    = doc.add_paragraph()
    pPr  = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot  = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single"); bot.set(qn("w:sz"), "16")
    bot.set(qn("w:space"), "4");    bot.set(qn("w:color"), "E91E8C")
    pBdr.append(bot); pPr.append(pBdr)
    doc.add_page_break()
 
def build_doc_info(doc, data):
    add_h1(doc, "Índice")
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    fld = OxmlElement("w:fldChar")
    fld.set(qn("w:fldCharType"), "begin"); run._r.append(fld)
    run2  = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-3" \\h \\z \\u'; run2._r.append(instr)
    run3  = paragraph.add_run()
    fld2  = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "separate"); run3._r.append(fld2)
    ph    = paragraph.add_run()
    ph.text = "  [Índice — generado automáticamente]  "
    ph.font.size = Pt(8); ph.font.italic = True
    ph.font.color.rgb = GRAY_MID
    run4  = paragraph.add_run()
    fld3  = OxmlElement("w:fldChar")
    fld3.set(qn("w:fldCharType"), "end"); run4._r.append(fld3)
    doc.add_paragraph()
 
    add_h1(doc, "Información del documento")
    doc.add_paragraph()
    meta_table(doc, {
        "Título del documento":      "Documentación técnica",
        "Código del documento":      DOC_REF,
        "Cliente":                   DOC_CLIENT,
        "Nivel de seguridad":        DOC_SECURITY,
        "Propietario del documento": DOC_AUTHOR,
    })
    add_h2(doc, "Registro de versiones")
    schema_table(doc,
        ["Autor", "Descripción", "Versión", "Fecha"],
        [[DOC_AUTHOR, "Versión inicial del documento.",
          DOC_VERSION, data["generated_at"][:10]]],
        col_widths=[2300, 4200, 1200, 1700])
    notice = doc.add_paragraph()
    r = notice.add_run(TEXT_AVISO.format(autor=DOC_AUTHOR))
    r.font.size = Pt(8); r.font.name = "Arial"
    r.font.italic = True; r.font.color.rgb = GRAY_MID
    doc.add_page_break()
 
 
def build_autoscale_section(doc, cap_info):
    add_h2(doc, "2.3 Proceso Autoescalado")
    hora_ini = AUTOSCALE_CONFIG.get("hora_inicio", "—")
    hora_par = AUTOSCALE_CONFIG.get("hora_parada", "—")
    rb_name  = AUTOSCALE_CONFIG.get("runbook_name", "—")
 
    add_body(doc, TEXT_AUTOESCALADO)
    doc.add_paragraph()
    for bullet in [f"{hora_ini}, hora española, reanudar la capacidad.",
                   f"{hora_par}, hora española, suspender la capacidad."]:
        p   = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(bullet)
        run.font.name = "Arial"; run.font.size = Pt(9)
    doc.add_paragraph()
 
    rb_p = doc.add_paragraph()
    rb_p.paragraph_format.space_after = Pt(4)
    r1 = rb_p.add_run("El proceso de autoescalado se gestiona a través de un "
                       "Runbook definido en Python llamado ")
    r1.font.name = "Arial"; r1.font.size = Pt(9)
    r2 = rb_p.add_run(rb_name)
    r2.font.name = "Courier New"; r2.font.size = Pt(9); r2.font.bold = True
    r3 = rb_p.add_run(".")
    r3.font.name = "Arial"; r3.font.size = Pt(9)
    doc.add_paragraph()
 
    # Figura 2 — busca manual primero, si no genera diagrama
    auto_diag = get_runbook_diagram_path(cap_info, AUTOSCALE_CONFIG)
    insert_figure(doc, 2, auto_diag,
        f"Figura 2. Información general del Runbook que configura el "
        f"escalado/desescalado de la capacidad de Fabric de {DOC_CLIENT}", 5.5)
    doc.add_paragraph()
    add_body(doc, TEXT_AUTOESCALADO_EXTRA)
    doc.add_paragraph()
 
 
def build_workspace_section(doc, ws_list, all_workspaces, cap_info, cap_id):
    documented_ids = {ws["id"] for ws in ws_list}
 
    add_h1(doc, "2. Fabric Workspace")
    add_body(doc, TEXT_FABRIC_WORKSPACE)
    doc.add_paragraph()
 
    # Figura 1 — busca manual primero, si no genera diagrama
    auto_diag = get_architecture_diagram_path(cap_info, ws_list)
    insert_figure(doc, 1, auto_diag,
                  "Figura 1. Suscripción de Microsoft Fabric en Azure", 5.8)
    doc.add_paragraph()
 
    add_h2(doc, "2.1 Áreas de trabajo")
    add_body(doc, TEXT_AREAS_TRABAJO)
    doc.add_paragraph()
    ws_rows = []
    for w in all_workspaces:
        wname   = w.get("displayName", "—")
        is_doc  = w.get("id") in documented_ids
        purpose = WORKSPACE_PURPOSES.get(wname, "—")
        cap_n   = cap_info.get("displayName","—") if w.get("capacityId") == cap_id else "—"
        ws_rows.append([wname, purpose, cap_n, "✓" if is_doc else ""])
    schema_table(doc,
        ["Área de trabajo", "Función", "Capacidad", "Documentado"],
        ws_rows, col_widths=[2800, 2800, 2000, 1000])
    doc_names = ", ".join(ws["name"] for ws in ws_list)
    nota = doc.add_paragraph()
    rn   = nota.add_run(f"✓ Workspaces documentados en este informe: {doc_names}")
    rn.font.size = Pt(8); rn.font.italic = True; rn.font.color.rgb = GRAY_MID
    doc.add_paragraph()
 
    add_h2(doc, "2.2 Propiedades de la capacidad")
    add_body(doc, TEXT_CAPACIDAD)
    doc.add_paragraph()
    admins_str  = ", ".join(cap_info.get("admins", [])) or "—"
    ws_assigned = ", ".join(
        w.get("displayName","") for w in all_workspaces
        if w.get("capacityId") == cap_id) or "—"
    meta_table(doc, {
        "Nombre":               cap_info.get("displayName","—"),
        "SKU":                  cap_info.get("sku","—"),
        "Región":               cap_info.get("region","—"),
        "Estado":               cap_info.get("state","—"),
        "Capacity ID":          cap_id or "—",
        "Administradores":      admins_str,
        "Workspaces asignados": ws_assigned,
    })
    doc.add_paragraph()
    build_autoscale_section(doc, cap_info)
 
 
print("✅ Celda 6c cargada")
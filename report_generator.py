import io
import sqlite3
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.platypus import KeepTogether
from reportlab.graphics.shapes import Drawing, Line, String, Rect, PolyLine
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics import renderPDF
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib.colors import HexColor
import base64, os

# ── Colors ──
C_BG      = HexColor('#0d1117')
C_PANEL   = HexColor('#161b22')
C_ACCENT  = HexColor('#6fcf3a')
C_BLUE    = HexColor('#4fc3f7')
C_AMBER   = HexColor('#ffb74d')
C_GREEN   = HexColor('#81c784')
C_YELLOW  = HexColor('#ffd54f')
C_RED     = HexColor('#f44336')
C_MUTED   = HexColor('#6b7a99')
C_TEXT    = HexColor('#cdd6f4')
C_WHITE   = colors.white
C_BORDER  = HexColor('#1e3a5f')

def get_logo_path():
    """Save embedded logo to temp file for reportlab."""
    logo_b64 = os.environ.get('LOGO_B64', '')
    if not logo_b64:
        return None
    try:
        path = '/tmp/wago_logo_report.jpg'
        with open(path, 'wb') as f:
            f.write(base64.b64decode(logo_b64))
        return path
    except:
        return None

def query_history(db_path, start_dt, end_dt):
    """Query historical data from SQLite."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
        SELECT timestamp, tensao_L1, tensao_L2, tensao_L3,
               corrente_L1, corrente_L2, corrente_L3,
               potencia_ativa, potencia_reativa, potencia_aparente,
               frequencia, fp_L1, fp_L2, fp_L3
        FROM energy_history
        WHERE timestamp BETWEEN ? AND ?
        ORDER BY timestamp ASC
    ''', (start_dt.timestamp(), end_dt.timestamp()))
    rows = cur.fetchall()
    conn.close()
    return rows

def compute_stats(rows, col_idx):
    """Compute min, max, avg for a column index."""
    vals = [r[col_idx] / 10.0 for r in rows if r[col_idx] is not None]
    if not vals:
        return None, None, None
    return round(min(vals),1), round(max(vals),1), round(sum(vals)/len(vals),1)

def compute_stats_fp(rows, col_idx):
    vals = [r[col_idx] / 100.0 for r in rows if r[col_idx] is not None]
    if not vals:
        return None, None, None
    return round(min(vals),3), round(max(vals),3), round(sum(vals)/len(vals),3)

def count_alerts(rows):
    """Count frequency out-of-range alerts."""
    alerts = []
    for r in rows:
        freq = r[10] / 10.0
        if freq < 59.6 or freq > 60.4:
            ts = datetime.fromtimestamp(r[0]).strftime('%d/%m/%Y %H:%M:%S')
            alerts.append((ts, round(freq,2)))
    return alerts

def make_line_chart(rows, col_indices, colors_list, width, height, scale=10.0, label='', lo_limit=None, hi_limit=None):
    """Generate a ReportLab line chart drawing."""
    drawing = Drawing(width, height)

    # Background
    drawing.add(Rect(0, 0, width, height, fillColor=C_PANEL, strokeColor=C_BORDER, strokeWidth=0.5))

    if not rows or len(rows) < 2:
        drawing.add(String(width/2, height/2, 'Sem dados', textAnchor='middle', fillColor=C_MUTED, fontSize=8))
        return drawing

    # Sample max 120 points for performance
    step = max(1, len(rows) // 120)
    sampled = rows[::step]

    n = len(sampled)
    xs = list(range(n))

    # Compute Y range
    all_vals = []
    for cidx in col_indices:
        all_vals += [r[cidx] / scale for r in sampled if r[cidx] is not None]
    if not all_vals:
        return drawing

    ymin = min(all_vals) * 0.98
    ymax = max(all_vals) * 1.02
    if lo_limit: ymin = min(ymin, lo_limit * 0.99)
    if hi_limit: ymax = max(ymax, hi_limit * 1.01)
    yrange = ymax - ymin if ymax != ymin else 1

    # Margins
    ml, mr, mb, mt = 32, 8, 16, 8
    pw = width - ml - mr
    ph = height - mb - mt

    def tx(i): return ml + (i / (n-1)) * pw
    def ty(v): return mb + ((v - ymin) / yrange) * ph

    # Grid lines
    for i, gv in enumerate([ymin, (ymin+ymax)/2, ymax]):
        gy = ty(gv)
        drawing.add(Line(ml, gy, ml+pw, gy, strokeColor=HexColor('#1e3a5f'), strokeWidth=0.5))
        drawing.add(String(ml-2, gy-3, f'{gv:.1f}', textAnchor='end', fillColor=C_MUTED, fontSize=6))

    # Limit lines
    if lo_limit is not None:
        loy = ty(lo_limit)
        drawing.add(Line(ml, loy, ml+pw, loy, strokeColor=C_RED, strokeWidth=0.8,
                         strokeDashArray=[4,3]))
        drawing.add(String(ml+pw-2, loy+2, f'{lo_limit}', textAnchor='end', fillColor=C_RED, fontSize=6))
    if hi_limit is not None:
        hiy = ty(hi_limit)
        drawing.add(Line(ml, hiy, ml+pw, hiy, strokeColor=C_RED, strokeWidth=0.8,
                         strokeDashArray=[4,3]))
        drawing.add(String(ml+pw-2, hiy+2, f'{hi_limit}', textAnchor='end', fillColor=C_RED, fontSize=6))

    # Lines
    for cidx, col in zip(col_indices, colors_list):
        pts = [(tx(i), ty(sampled[i][cidx] / scale)) for i in range(n) if sampled[i][cidx] is not None]
        if len(pts) > 1:
            flat = []
            for px, py in pts:
                flat += [px, py]
            drawing.add(PolyLine(flat, strokeColor=col, strokeWidth=1.0, strokeLineJoin=1))

    # Time labels
    ts_start = datetime.fromtimestamp(sampled[0][0]).strftime('%H:%M')
    ts_end   = datetime.fromtimestamp(sampled[-1][0]).strftime('%H:%M')
    drawing.add(String(ml, mb-10, ts_start, textAnchor='start', fillColor=C_MUTED, fontSize=6))
    drawing.add(String(ml+pw, mb-10, ts_end, textAnchor='end', fillColor=C_MUTED, fontSize=6))

    return drawing

def generate_report(db_path, start_dt, end_dt):
    """Generate PDF report and return bytes."""
    rows = query_history(db_path, start_dt, end_dt)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12*mm, rightMargin=12*mm,
        topMargin=10*mm, bottomMargin=10*mm,
        title='Relatório de Energia Elétrica',
        author='Wago 762-3405'
    )

    W = landscape(A4)[0] - 24*mm  # usable width

    # ── Styles ──
    s_title  = ParagraphStyle('title',  fontName='Helvetica-Bold', fontSize=16, textColor=C_ACCENT,   spaceAfter=2)
    s_sub    = ParagraphStyle('sub',    fontName='Helvetica',      fontSize=9,  textColor=C_MUTED,    spaceAfter=6)
    s_h2     = ParagraphStyle('h2',     fontName='Helvetica-Bold', fontSize=11, textColor=C_TEXT,     spaceBefore=10, spaceAfter=4)
    s_h3     = ParagraphStyle('h3',     fontName='Helvetica-Bold', fontSize=9,  textColor=C_ACCENT,   spaceBefore=6,  spaceAfter=3)
    s_normal = ParagraphStyle('normal', fontName='Helvetica',      fontSize=8,  textColor=C_TEXT)
    s_alert  = ParagraphStyle('alert',  fontName='Helvetica',      fontSize=8,  textColor=C_RED)
    s_ok     = ParagraphStyle('ok',     fontName='Helvetica',      fontSize=8,  textColor=C_ACCENT)

    story = []

    # ── HEADER ──
    period_str = f"{start_dt.strftime('%d/%m/%Y %H:%M')} — {end_dt.strftime('%d/%m/%Y %H:%M')}"
    header_data = [[
        Paragraph('<b>WAGO</b>', ParagraphStyle('logo', fontName='Helvetica-Bold', fontSize=20, textColor=C_ACCENT)),
        Paragraph(f'<b>RELATÓRIO DE ENERGIA ELÉTRICA</b><br/><font size="8" color="#6b7a99">{period_str} &nbsp;|&nbsp; Modbus TCP FC3 &nbsp;|&nbsp; Wago 762-3405</font>',
                  ParagraphStyle('hdr', fontName='Helvetica-Bold', fontSize=13, textColor=C_TEXT)),
        Paragraph(f'<font size="8" color="#6b7a99">Gerado em<br/></font><b>{datetime.now().strftime("%d/%m/%Y %H:%M")}</b>',
                  ParagraphStyle('date', fontName='Helvetica-Bold', fontSize=9, textColor=C_TEXT, alignment=2)),
    ]]
    hdr_table = Table(header_data, colWidths=[30*mm, W-80*mm, 50*mm])
    hdr_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_PANEL),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [C_PANEL]),
        ('LINEBELOW', (0,0), (-1,-1), 1, C_ACCENT),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (0,-1), 8),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 6))

    if not rows:
        story.append(Paragraph('Nenhum dado encontrado para o período selecionado.', s_normal))
        doc.build(story)
        return buf.getvalue()

    total_pts = len(rows)
    duration_h = (end_dt - start_dt).total_seconds() / 3600

    # ── SUMMARY CARDS ──
    story.append(Paragraph('RESUMO DO PERÍODO', s_h3))

    def stat_cell(label, vmin, vmax, vavg, unit, col):
        if vmin is None:
            return Paragraph(f'<b>{label}</b><br/>Sem dados', s_normal)
        return Paragraph(
            f'<font size="7" color="#6b7a99">{label}</font><br/>'
            f'<font size="14" color="{col}"><b>{vavg}</b></font> <font size="7" color="#6b7a99">{unit}</font><br/>'
            f'<font size="7" color="#6b7a99">Min: {vmin} &nbsp; Max: {vmax}</font>',
            s_normal
        )

    col_map = {'#4fc3f7':'#4fc3f7', '#ffb74d':'#ffb74d', '#81c784':'#81c784'}

    cards = [
        stat_cell('Tensão L1',    *compute_stats(rows,1), 'V', '#4fc3f7'),
        stat_cell('Tensão L2',    *compute_stats(rows,2), 'V', '#ffb74d'),
        stat_cell('Tensão L3',    *compute_stats(rows,3), 'V', '#81c784'),
        stat_cell('Corrente L1',  *compute_stats(rows,4), 'A', '#4fc3f7'),
        stat_cell('Corrente L2',  *compute_stats(rows,5), 'A', '#ffb74d'),
        stat_cell('Corrente L3',  *compute_stats(rows,6), 'A', '#81c784'),
        stat_cell('Pot. Ativa',   *compute_stats(rows,7), 'kW',  '#81c784'),
        stat_cell('Pot. Aparente',*compute_stats(rows,9), 'kVA', '#ffd54f'),
        stat_cell('Frequência',   *compute_stats(rows,10),'Hz',  '#6fcf3a'),
    ]

    cw = W / 9
    card_table = Table([cards], colWidths=[cw]*9)
    card_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_PANEL),
        ('BOX', (0,0), (-1,-1), 0.5, C_BORDER),
        ('INNERGRID', (0,0), (-1,-1), 0.3, C_BORDER),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(card_table)
    story.append(Spacer(1, 8))

    # ── CHARTS: 2 columns ──
    ch_w = (W - 6*mm) / 2
    ch_h = 70

    story.append(Paragraph('GRÁFICOS TEMPORAIS', s_h3))

    charts_row1 = [
        [Paragraph('<font size="7" color="#6b7a99">TENSÃO POR FASE (V)</font>', s_normal),
         make_line_chart(rows, [1,2,3], [C_BLUE, C_AMBER, C_GREEN], ch_w, ch_h)],
        [Paragraph('<font size="7" color="#6b7a99">CORRENTE POR FASE (A)</font>', s_normal),
         make_line_chart(rows, [4,5,6], [C_BLUE, C_AMBER, C_GREEN], ch_w, ch_h)],
    ]

    charts_row2 = [
        [Paragraph('<font size="7" color="#6b7a99">POTÊNCIA ATIVA (kW)</font>', s_normal),
         make_line_chart(rows, [7], [C_GREEN], ch_w, ch_h)],
        [Paragraph('<font size="7" color="#6b7a99">FREQUÊNCIA (Hz) — limites 59,6 / 60,4</font>', s_normal),
         make_line_chart(rows, [10], [C_ACCENT], ch_w, ch_h, scale=10.0, lo_limit=59.6, hi_limit=60.4)],
    ]

    for row_data in [charts_row1, charts_row2]:
        ct = Table([[row_data[0][1], row_data[1][1]]], colWidths=[ch_w, ch_w])
        ct.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_PANEL),
            ('BOX', (0,0), (-1,-1), 0.5, C_BORDER),
            ('INNERGRID', (0,0), (-1,-1), 0.3, C_BORDER),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(ct)
        story.append(Spacer(1, 4))

    # ── FATOR DE POTÊNCIA ──
    story.append(Paragraph('FATOR DE POTÊNCIA', s_h3))
    fp_stats = [
        ['Fase', 'Mínimo', 'Máximo', 'Média'],
        ['L1', *[str(x) if x is not None else '—' for x in compute_stats_fp(rows, 11)]],
        ['L2', *[str(x) if x is not None else '—' for x in compute_stats_fp(rows, 12)]],
        ['L3', *[str(x) if x is not None else '—' for x in compute_stats_fp(rows, 13)]],
    ]
    fp_table = Table(fp_stats, colWidths=[W/4]*4)
    fp_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_BORDER),
        ('BACKGROUND', (0,1), (-1,-1), C_PANEL),
        ('TEXTCOLOR', (0,0), (-1,0), C_ACCENT),
        ('TEXTCOLOR', (0,1), (-1,-1), C_TEXT),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('INNERGRID', (0,0), (-1,-1), 0.3, C_BORDER),
        ('BOX', (0,0), (-1,-1), 0.5, C_BORDER),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(fp_table)
    story.append(Spacer(1, 8))

    # ── ALERTAS ──
    story.append(Paragraph('ALERTAS DE FREQUÊNCIA FORA DE LIMITE (59,6 — 60,4 Hz)', s_h3))
    alerts = count_alerts(rows)
    if not alerts:
        story.append(Paragraph('✓ Nenhum alerta registrado no período. Frequência dentro dos limites.', s_ok))
    else:
        story.append(Paragraph(f'⚠ {len(alerts)} evento(s) fora do limite detectado(s):', s_alert))
        story.append(Spacer(1, 3))
        alert_data = [['Timestamp', 'Frequência (Hz)', 'Status']]
        for ts, fv in alerts[:50]:  # max 50 alertas na tabela
            status = 'BAIXA' if fv < 59.6 else 'ALTA'
            alert_data.append([ts, f'{fv:.2f}', status])
        if len(alerts) > 50:
            alert_data.append(['...', f'+ {len(alerts)-50} eventos adicionais', ''])

        al_table = Table(alert_data, colWidths=[W*0.4, W*0.3, W*0.3])
        al_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_BORDER),
            ('BACKGROUND', (0,1), (-1,-1), C_PANEL),
            ('TEXTCOLOR', (0,0), (-1,0), C_ACCENT),
            ('TEXTCOLOR', (0,1), (-1,-1), C_RED),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 7),
            ('INNERGRID', (0,0), (-1,-1), 0.3, C_BORDER),
            ('BOX', (0,0), (-1,-1), 0.5, C_BORDER),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(al_table)

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width=W, color=C_BORDER, thickness=0.5))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        f'<font size="7" color="#6b7a99">Wago 762-3405 &nbsp;|&nbsp; Modbus TCP FC3 &nbsp;|&nbsp; '
        f'{total_pts} amostras &nbsp;|&nbsp; Duração: {duration_h:.1f}h &nbsp;|&nbsp; '
        f'Gerado: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</font>', s_normal))

    doc.build(story)
    return buf.getvalue()

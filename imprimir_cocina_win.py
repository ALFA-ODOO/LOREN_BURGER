# -*- coding: utf-8 -*-
"""
imprimir_cocina_win.py
Toma líneas de TPV pagadas y no impresas (x_impreso_cocina=False) y las imprime
en la impresora (por defecto, la predeterminada de Windows). Luego marca como impresas.

Uso:
  - Prueba de impresión (sin Odoo):        python imprimir_cocina_win.py --print-test
  - Prueba sin imprimir ni escribir:       python imprimir_cocina_win.py --dry-run
  - Ejecutar real:                         python imprimir_cocina_win.py
  - Filtrar por categoría TPV (ID):        python imprimir_cocina_win.py --pos-categ 12
  - Elegir impresora (no la predeterminada): python imprimir_cocina_win.py --printer "EPSON TM-T20III Receipt"

Requisitos:
  - pywin32
  - python-dotenv
  - Variables .env: ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD
"""

import os
import sys
import argparse
import datetime as dt
import textwrap
import xmlrpc.client
from dotenv import load_dotenv

# =========================
# CLI
# =========================
ap = argparse.ArgumentParser()
ap.add_argument("--dry-run", action="store_true", help="No imprime ni escribe en Odoo")
ap.add_argument("--pos-categ", type=int, default=None, help="ID de Categoría del TPV para filtrar (incluye hijas)")
ap.add_argument("--max-orders", type=int, default=20, help="Máx. pedidos a procesar por corrida")
ap.add_argument("--print-test", action="store_true", help="Imprime una página de prueba en la impresora seleccionada y sale")
ap.add_argument("--printer", type=str, default=None, help="Nombre de impresora Windows (si no se indica, usa la predeterminada)")
args = ap.parse_args()

# =========================
# ENV
# =========================
load_dotenv()
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USERNAME")
ODOO_PWD = os.getenv("ODOO_PASSWORD")

if not all([ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PWD]) and not args.print_test:
    print("Faltan variables en .env (ODOO_URL/DB/USERNAME/PASSWORD).")
    sys.exit(1)

# =========================
# Conexión Odoo (si hace falta)
# =========================
if not args.print_test:
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PWD, {})
    if not uid:
        print("No se pudo autenticar en Odoo. Verificá .env")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
else:
    uid = None
    models = None

# =========================
# Utilidades de formato ticket
# =========================
RAW_ENCODING = "cp437"   # Si acentos salen mal, probá 'cp850'
LINE_CHARS = 42          # Ancho típico de 80mm (42–48)

def trunc_pad(s: str) -> str:
    return s[:LINE_CHARS].ljust(LINE_CHARS)

def center(s: str) -> str:
    s = s[:LINE_CHARS]
    pad = max(0, (LINE_CHARS - len(s)) // 2)
    return " " * pad + s

def linea(ch="=") -> str:
    return ch * LINE_CHARS

def wrap_line(txt: str, indent=2):
    res = []
    for ln in textwrap.wrap(txt, width=LINE_CHARS - indent):
        res.append((" " * indent) + ln)
    return "\n".join(res)

def format_header(order):
    """
    Encabezado: ticket, mesa/cliente, hora.
    """
    name = order.get('name') or ''
    table = (order.get('table_id') or ['',''])[1] if order.get('table_id') else ''
    partner = (order.get('partner_id') or ['',''])[1] if order.get('partner_id') else ''
    dt_str = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    h = []
    h.append(center("COMANDA COCINA"))
    h.append(center(dt_str))
    h.append(linea("-"))
    h.append(trunc_pad(f"Ticket: {name}"))
    if table:
        h.append(trunc_pad(f"Mesa: {table}"))
    if partner:
        h.append(trunc_pad(f"Cliente: {partner}"))
    h.append(linea("="))
    return "\n".join(h) + "\n"

def build_ticket(order, lines):
    """
    Cuerpo del ticket a partir de líneas del pedido.
    Cada ítem: QTY x DESCRIPCION
               (nota)
    """
    out = []
    out.append(format_header(order))
    for l in lines:
        qty = l.get('qty', 0)
        name = l.get('display_name') or (l.get('product_id') or ['',''])[1]
        base = f"{qty:g} x {name}"
        out.append(trunc_pad(base))
        note = (l.get('note') or "").strip()
        if note:
            out.append(wrap_line(f"({note})", indent=2))
        out.append("")  # línea en blanco
    out.append(linea("="))
    out.append(center("FIN COMANDA"))
    out.append("")
    return "\n".join(out)

# =========================
# Impresión Windows (RAW)  (reemplazar este bloque)
# =========================
def escpos_text(txt: str) -> bytes:
    ESC = b'\x1b'
    INIT = ESC + b'@'
    LF = b'\n'
    CUT = b'\x1d\x56\x01'      # podés probar \x00 si no corta
    body = txt.replace('\r\n', '\n').replace('\r', '\n').encode(RAW_ENCODING, errors="ignore")
    return INIT + body + LF*3 + CUT

def _open_printer(printer_name: str):
    import win32print
    return win32print.OpenPrinter(printer_name)

def _start_doc(handle, doc_name="Comanda Cocina", datatype="RAW"):
    """
    Compatibilidad: algunas versiones exigen tupla; otras aceptan dict.
    Forzamos tupla y, si falla, probamos dict.
    """
    import win32print
    try:
        # ✅ Tupla (docname, outputfile, datatype)
        return win32print.StartDocPrinter(handle, 1, (doc_name, None, datatype))
    except TypeError:
        # Fallback por si tu build acepta dict
        doc_info = {"pDocName": doc_name, "pOutputFile": None, "pDatatype": datatype}
        return win32print.StartDocPrinter(handle, 1, doc_info)

def print_raw(printer_name: str, data: bytes):
    import win32print
    h = _open_printer(printer_name)
    try:
        _start_doc(h, "Comanda Cocina", "RAW")
        win32print.StartPagePrinter(h)
        win32print.WritePrinter(h, data)
        win32print.EndPagePrinter(h)
        win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)

def get_default_printer():
    import win32print
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None

def resolve_printer():
    if args.printer:
        return args.printer
    p = get_default_printer()
    if not p:
        raise RuntimeError("Windows no reporta impresora predeterminada. Indique --printer.")
    return p

def print_raw_selected(text: str, verbose=True):
    p = resolve_printer()
    if verbose:
        print(f"[PRINT] Usando impresora: {p}")
    print_raw(p, escpos_text(text))

def print_test_page(msg="PRUEBA COCINA – EPSON TM-T20III"):
    """
    Test simple (sin Odoo). Envía texto plano RAW.
    """
    import win32print
    p = resolve_printer()
    h = _open_printer(p)
    try:
        _start_doc(h, "Test simple", "RAW")
        win32print.StartPagePrinter(h)
        win32print.WritePrinter(h, (msg + "\n\n").encode(RAW_ENCODING, errors="ignore"))
        win32print.EndPagePrinter(h)
        win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)


# =========================
# Odoo: fetch y marcado
# =========================
def fetch_pending_lines(pos_categ_id=None, limit_orders=20):
    """
    Devuelve dict {order_id: {'order': order_read, 'lines': [line_read,...]}}
    Filtros: pedido state='paid', x_impreso_cocina=False, qty>0.
    """
    
    domain_lines = [
        ('x_impreso_cocina', '=', False),
        ('qty', '>', 0),
        ('order_id.state', '=', 'paid'),
    ]
    if pos_categ_id:
        domain_lines.append(('product_id.pos_categ_id', 'child_of', pos_categ_id))

    line_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PWD,
        'pos.order.line', 'search',
        [domain_lines], {'limit': 500}
    )
    if not line_ids:
        return {}

    fields_line = ['id', 'order_id', 'product_id', 'display_name', 'qty', 'note', 'x_impreso_cocina']
    lines = models.execute_kw(
        ODOO_DB, uid, ODOO_PWD,
        'pos.order.line', 'read',
        [line_ids], {'fields': fields_line}
    )

    # agrupar por pedido
    orders_map = {}
    for l in lines:
        oid = l['order_id'][0]
        orders_map.setdefault(oid, []).append(l)

    order_ids = list(orders_map.keys())[:limit_orders]

    fields_order = ['id', 'name', 'partner_id', 'table_id', 'date_order', 'amount_total', 'state']
    orders = models.execute_kw(
        ODOO_DB, uid, ODOO_PWD,
        'pos.order', 'read', [order_ids], {'fields': fields_order}
    )

    out = {}
    for o in orders:
        out[o['id']] = {'order': o, 'lines': orders_map.get(o['id'], [])}
    return out

def mark_printed(line_ids, error_msg=None):
    vals = {'x_impreso_cocina': True}
    try:
        now_str = dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        vals['x_impreso_fecha'] = now_str  # si el campo existe
    except Exception:
        pass
    return models.execute_kw(
        ODOO_DB, uid, ODOO_PWD,
        'pos.order.line', 'write',
        [line_ids, vals]
    )

# =========================
# Main
# =========================
def main():
    # Test de impresión sin Odoo
    if args.print_test:
        print_test_page()
        print("OK: Página de prueba enviada.")
        return

    batches = fetch_pending_lines(pos_categ_id=args.pos_categ, limit_orders=args.max_orders)
    if not batches:
        print("No hay líneas pendientes para imprimir.")
        return

    for oid, payload in batches.items():
        order = payload['order']
        lines = payload['lines']
        txt = build_ticket(order, lines)

        print(f"\n=== Pedido {order.get('name')} (ID {oid}) ===")
        print(txt)

        if args.dry_run:
            print("DRY-RUN: no se imprime ni se marca.")
            continue

        try:
            print_raw_selected(txt, verbose=True)
            mark_printed([l['id'] for l in lines])
            print("OK: Impreso y marcado.")
        except Exception as e:
            print(f"ERROR al imprimir: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")

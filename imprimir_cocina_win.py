# -*- coding: utf-8 -*-
"""
imprimir_cocina_win.py
Toma líneas de TPV cobradas (paid/done/invoiced) y no impresas (x_impreso_cocina=False)
y las imprime en la impresora (por defecto, la predeterminada de Windows). Luego marca como impresas.

Uso:
  - Prueba de impresión (sin Odoo):        python imprimir_cocina_win.py --print-test
  - Prueba sin imprimir ni escribir:       python imprimir_cocina_win.py --dry-run
  - Ejecutar real:                         python imprimir_cocina_win.py
  - Filtrar por categoría TPV (ID):        python imprimir_cocina_win.py --pos-categ 12
  - Elegir impresora (no la predeterminada): python imprimir_cocina_win.py --printer "EPSON TM-T20III Receipt"
  - Abrir interfaz gráfica:                python imprimir_cocina_win.py --gui

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
ap.add_argument("--gui", action="store_true", help="Abre la interfaz gráfica de monitoreo/impr. de comandas")
ap.add_argument("--auto-interval", type=int, default=30, help="Segundos entre ejecuciones automáticas (GUI)")
args = ap.parse_args()

# =========================
# ENV
# =========================
load_dotenv()
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USERNAME")
ODOO_PWD = os.getenv("ODOO_PASSWORD")

if args.gui and args.print_test:
    print("La interfaz gráfica no está disponible con --print-test.")
    sys.exit(1)

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
PENDING_ORDER_STATES = ['paid', 'done', 'invoiced']


def fetch_pending_lines(pos_categ_id=None, limit_orders=20):
    """
    Devuelve dict {order_id: {'order': order_read, 'lines': [line_read,...]}}
    Filtros: pedido state in PENDING_ORDER_STATES, x_impreso_cocina=False, qty>0.
    """

    domain_lines = [
        ('x_impreso_cocina', '=', False),
        ('qty', '>', 0),
        ('order_id.state', 'in', PENDING_ORDER_STATES),
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

def fetch_recent_printed(pos_categ_id=None, limit_orders=20):
    """Obtiene los pedidos del día (impresos o pendientes) ordenados por hora descendente."""
    today_start = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_str = today_start.strftime('%Y-%m-%d %H:%M:%S')

    domain_lines = [
        ('qty', '>', 0),
        ('order_id.state', 'in', ['paid', 'done', 'invoiced']),
        ('order_id.date_order', '>=', today_start_str),
    ]
    if pos_categ_id:
        domain_lines.append(('product_id.pos_categ_id', 'child_of', pos_categ_id))

    # Traemos suficientes líneas para cubrir el límite deseado de pedidos.
    line_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PWD,
        'pos.order.line', 'search',
        [domain_lines], {'limit': max(50, limit_orders * 10), 'order': 'order_id.date_order desc, id desc'}
    )
    if not line_ids:
        return []

    fields_line = [
        'id', 'order_id', 'product_id', 'display_name', 'qty', 'note',
        'x_impreso_cocina', 'write_date'
    ]
    lines = models.execute_kw(
        ODOO_DB, uid, ODOO_PWD,
        'pos.order.line', 'read',
        [line_ids], {'fields': fields_line}
    )

    orders_map = {}
    for line in lines:
        oid = line['order_id'][0]
        orders_map.setdefault(oid, []).append(line)

    order_ids = list(orders_map.keys())
    if not order_ids:
        return []

    fields_order = ['id', 'name', 'partner_id', 'table_id', 'date_order', 'amount_total', 'state']
    orders = models.execute_kw(
        ODOO_DB, uid, ODOO_PWD,
        'pos.order', 'read', [order_ids], {'fields': fields_order}
    )

    orders_by_id = {order['id']: order for order in orders}
    payloads = []
    for oid, lines in orders_map.items():
        order = orders_by_id.get(oid)
        if not order:
            continue
        last_write = ''
        all_printed = True
        for line in lines:
            write_date = line.get('write_date') or ''
            if write_date > last_write:
                last_write = write_date
            if not line.get('x_impreso_cocina'):
                all_printed = False
        date_order = order.get('date_order') or ''
        last_activity = max(last_write, date_order)
        payloads.append({
            'order': order,
            'lines': lines,
            'ticket_text': build_ticket(order, lines),
            'printed': all_printed,
            'last_write_date': last_write,
            'last_activity': last_activity,
        })

    payloads.sort(key=lambda item: item.get('last_activity') or '', reverse=True)
    if limit_orders:
        payloads = payloads[:limit_orders]
    return payloads

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

def process_pending_orders(pos_categ_id=None, max_orders=20, dry_run=False, verbose=True):
    batches = fetch_pending_lines(pos_categ_id=pos_categ_id, limit_orders=max_orders)
    if not batches:
        if verbose:
            print("No hay líneas pendientes para imprimir.")
        return {'printed': [], 'errors': []}

    printed_payloads = []
    errors = []
    for oid, payload in batches.items():
        order = payload['order']
        lines = payload['lines']
        txt = build_ticket(order, lines)

        if verbose:
            print(f"\n=== Pedido {order.get('name')} (ID {oid}) ===")
            print(txt)

        if dry_run:
            if verbose:
                print("DRY-RUN: no se imprime ni se marca.")
        else:
            try:
                print_raw_selected(txt, verbose=verbose)
                mark_printed([l['id'] for l in lines])
                if verbose:
                    print("OK: Impreso y marcado.")
            except Exception as exc:
                if verbose:
                    print(f"ERROR al imprimir pedido {order.get('name')}: {exc}")
                errors.append({
                    'order': order,
                    'lines': lines,
                    'ticket_text': txt,
                    'error': exc,
                })
                continue

        printed_payloads.append({
            'order': order,
            'lines': lines,
            'ticket_text': txt,
        })

    return {'printed': printed_payloads, 'errors': errors}

# =========================
# GUI
# =========================
if args.gui:
    try:
        import threading
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception as gui_err:
        print(f"No se pudo iniciar la interfaz gráfica: {gui_err}")
        sys.exit(1)

    class KitchenPrinterGUI(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("Comandas Cocina")
            self.geometry("900x600")

            self.interval_var = tk.IntVar(value=max(5, args.auto_interval))
            self.auto_thread = None
            self.auto_stop = threading.Event()
            self.printed_orders = []

            self._build_layout()
            self.refresh_printed_orders()

        # ----- UI construction -----
        def _build_layout(self):
            main = ttk.Frame(self, padding=10)
            main.pack(fill=tk.BOTH, expand=True)

            # Upper controls
            controls = ttk.Frame(main)
            controls.pack(fill=tk.X)

            ttk.Label(controls, text="Intervalo automático (segundos):").pack(side=tk.LEFT)
            interval_spin = ttk.Spinbox(
                controls,
                from_=5,
                to=600,
                textvariable=self.interval_var,
                width=5
            )
            interval_spin.pack(side=tk.LEFT, padx=(5, 15))

            ttk.Button(controls, text="Imprimir pendientes", command=self.print_pending_orders).pack(side=tk.LEFT)
            ttk.Button(controls, text="Reimprimir selección", command=self.reprint_selected).pack(side=tk.LEFT, padx=5)
            ttk.Button(controls, text="Refrescar", command=self.refresh_printed_orders).pack(side=tk.LEFT)
            self.auto_btn = ttk.Button(controls, text="Iniciar automático", command=self.toggle_auto)
            self.auto_btn.pack(side=tk.LEFT, padx=(15, 0))

            # Printed orders list
            list_frame = ttk.Frame(main)
            list_frame.pack(fill=tk.BOTH, expand=True, pady=10)

            columns = ("ticket", "mesa", "cliente", "fecha", "estado")
            self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
            self.tree.heading("ticket", text="Ticket")
            self.tree.heading("mesa", text="Mesa")
            self.tree.heading("cliente", text="Cliente")
            self.tree.heading("fecha", text="Hora")
            self.tree.heading("estado", text="Estado")
            self.tree.column("ticket", width=140)
            self.tree.column("mesa", width=120)
            self.tree.column("cliente", width=180)
            self.tree.column("fecha", width=160)
            self.tree.column("estado", width=110, anchor=tk.CENTER)
            self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

            tree_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
            self.tree.configure(yscrollcommand=tree_scroll.set)

            self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

            # Details and log
            bottom = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
            bottom.pack(fill=tk.BOTH, expand=True)

            detail_frame = ttk.Labelframe(bottom, text="Detalle")
            self.detail_text = tk.Text(detail_frame, wrap=tk.WORD, height=12, state=tk.DISABLED)
            self.detail_text.pack(fill=tk.BOTH, expand=True)
            bottom.add(detail_frame, weight=1)

            log_frame = ttk.Labelframe(bottom, text="Eventos")
            self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=12, state=tk.DISABLED)
            self.log_text.pack(fill=tk.BOTH, expand=True)
            bottom.add(log_frame, weight=1)

            self.status_var = tk.StringVar(value="Listo")
            ttk.Label(main, textvariable=self.status_var).pack(fill=tk.X)

        # ----- Helpers -----
        def append_log(self, msg):
            ts = dt.datetime.now().strftime("%H:%M:%S")
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        def set_status(self, msg):
            self.status_var.set(msg)

        def _safe_interval(self):
            try:
                return max(5, int(self.interval_var.get()))
            except (TypeError, ValueError):
                self.interval_var.set(30)
                return 30

        def _run_async(self, target):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            return thread

        # ----- Data handling -----
        def refresh_printed_orders(self):
            def job():
                try:
                    data = fetch_recent_printed(pos_categ_id=args.pos_categ, limit_orders=args.max_orders)
                    self.after(0, lambda: self._load_printed_orders(data))
                except Exception as exc:
                    self.after(0, lambda: messagebox.showerror("Error al refrescar", str(exc)))
                    self.after(0, lambda: self.set_status("Error al refrescar"))
            self.set_status("Actualizando comandas...")
            self._run_async(job)

        def _load_printed_orders(self, orders):
            self.tree.delete(*self.tree.get_children())
            self.printed_orders = orders
            for idx, payload in enumerate(orders):
                order = payload['order']
                table = (order.get('table_id') or ['', ''])
                partner = (order.get('partner_id') or ['', ''])
                mesa = table[1] if len(table) > 1 else ''
                cliente = partner[1] if len(partner) > 1 else ''
                fecha = payload.get('last_activity') or order.get('date_order') or ''
                estado = "Impresa" if payload.get('printed') else "Pendiente"
                self.tree.insert('', tk.END, iid=str(idx), values=(order.get('name'), mesa, cliente, fecha, estado))
            self.set_status(f"Comandas del día: {len(orders)}")
            if orders:
                self.tree.selection_set('0')

        def on_tree_select(self, event=None):
            selection = self.tree.selection()
            if not selection:
                self.detail_text.configure(state=tk.NORMAL)
                self.detail_text.delete('1.0', tk.END)
                self.detail_text.configure(state=tk.DISABLED)
                return
            idx = int(selection[0])
            payload = self.printed_orders[idx]
            self.detail_text.configure(state=tk.NORMAL)
            self.detail_text.delete('1.0', tk.END)
            self.detail_text.insert(tk.END, payload.get('ticket_text', ''))
            self.detail_text.configure(state=tk.DISABLED)

        def print_pending_orders(self):
            def job():
                try:
                    result = process_pending_orders(
                        pos_categ_id=args.pos_categ,
                        max_orders=args.max_orders,
                        dry_run=args.dry_run,
                        verbose=False,
                    )
                    def update_ui():
                        printed = result['printed']
                        errors = result['errors']
                        if printed:
                            self.append_log(f"Impresas {len(printed)} comandas nuevas.")
                            self.refresh_printed_orders()
                        else:
                            self.append_log("No había comandas pendientes.")
                        if errors:
                            for err in errors:
                                self.append_log(f"Error al imprimir {err['order'].get('name')}: {err['error']}")
                            messagebox.showwarning(
                                "Errores de impresión",
                                f"Hubo {len(errors)} errores al imprimir. Ver registro para más detalle."
                            )
                        self.set_status("Listo")
                    self.after(0, update_ui)
                except Exception as exc:
                    self.after(0, lambda: messagebox.showerror("Error al imprimir", str(exc)))
                    self.after(0, lambda: self.set_status("Error al imprimir"))
            self.set_status("Imprimiendo comandas pendientes...")
            self._run_async(job)

        def reprint_selected(self):
            selection = self.tree.selection()
            if not selection:
                messagebox.showinfo("Reimprimir", "Seleccione una comanda de la lista.")
                return
            idx = int(selection[0])
            payload = self.printed_orders[idx]
            if not payload.get('printed'):
                messagebox.showinfo("Reimprimir", "Solo se pueden reimprimir comandas ya impresas.")
                return
            txt = payload.get('ticket_text')
            def job():
                try:
                    print_raw_selected(txt, verbose=False)
                    self.after(0, lambda: self.append_log(f"Reimpresa comanda {payload['order'].get('name')}"))
                except Exception as exc:
                    self.after(0, lambda: messagebox.showerror("Error al reimprimir", str(exc)))
            self._run_async(job)

        def toggle_auto(self):
            if self.auto_thread and self.auto_thread.is_alive():
                self.auto_stop.set()
                thread = self.auto_thread
                thread.join(timeout=2)
                self.auto_thread = None
                self.auto_btn.configure(text="Iniciar automático")
                self.append_log("Auto impresión detenida.")
                self.set_status("Listo")
                return

            self.auto_stop.clear()

            def loop():
                while not self.auto_stop.is_set():
                    self.after(0, lambda: self.set_status("Ejecución automática"))
                    try:
                        result = process_pending_orders(
                            pos_categ_id=args.pos_categ,
                            max_orders=args.max_orders,
                            dry_run=args.dry_run,
                            verbose=False,
                        )
                        printed = result['printed']
                        errors = result['errors']
                        if printed:
                            self.after(0, lambda: self.append_log(f"Automático: impresas {len(printed)} comandas."))
                            self.after(0, self.refresh_printed_orders)
                        else:
                            self.after(0, lambda: self.append_log("Automático: sin comandas pendientes."))
                        if errors:
                            self.after(0, lambda: self.append_log(f"Automático: {len(errors)} errores de impresión."))
                            self.after(0, lambda: messagebox.showwarning(
                                "Errores de impresión",
                                "Revise el registro de eventos para ver los errores de impresión."
                            ))
                    except Exception as exc:
                        self.after(0, lambda: self.append_log(f"Error en automático: {exc}"))
                        self.after(0, lambda: messagebox.showerror("Auto impresión", str(exc)))
                    wait_seconds = self._safe_interval()
                    for _ in range(wait_seconds):
                        if self.auto_stop.wait(1):
                            break
                self.after(0, lambda: self.set_status("Listo"))

            self.auto_thread = threading.Thread(target=loop, daemon=True)
            self.auto_thread.start()
            self.auto_btn.configure(text="Detener automático")
            self.append_log("Auto impresión iniciada.")

        def destroy(self):
            if self.auto_thread and self.auto_thread.is_alive():
                self.auto_stop.set()
                self.auto_thread.join(timeout=2)
            self.auto_thread = None
            super().destroy()

# =========================
# Main
# =========================
def main():
    # Test de impresión sin Odoo
    if args.print_test:
        print_test_page()
        print("OK: Página de prueba enviada.")
        return

    try:
        process_pending_orders(
            pos_categ_id=args.pos_categ,
            max_orders=args.max_orders,
            dry_run=args.dry_run,
            verbose=True,
        )
    except Exception as e:
        print(f"ERROR al imprimir: {e}")

if __name__ == "__main__":
    try:
        if args.gui:
            app = KitchenPrinterGUI()
            app.mainloop()
        else:
            main()
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")

# listar_pos.py
import os, xmlrpc.client, datetime as dt
from dotenv import load_dotenv
load_dotenv()

URL=os.getenv("ODOO_URL"); DB=os.getenv("ODOO_DB"); USR=os.getenv("ODOO_USERNAME"); PWD=os.getenv("ODOO_PASSWORD")

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USR, PWD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# ¿existe el booleano x_impreso_cocina?
fields = models.execute_kw(DB, uid, PWD, 'pos.order.line', 'fields_get', [[], ['type']])
has_flag = 'x_impreso_cocina' in fields

# últimos pedidos pagados (hoy)
hoy0 = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')

domain = [('qty','>',0),
          ('order_id.state','in',['paid','done','invoiced']),
          ('order_id.date_order','>=',hoy0)]
if has_flag:
    domain.insert(0, ('x_impreso_cocina','=',False))

line_ids = models.execute_kw(DB, uid, PWD, 'pos.order.line', 'search', [domain], {'limit': 200})
print("x_impreso_cocina existe?:", has_flag, "| Líneas encontradas:", len(line_ids))

if not line_ids:
    print("No hay líneas que cumplan el dominio.")
    raise SystemExit

lines = models.execute_kw(DB, uid, PWD, 'pos.order.line', 'read', [line_ids],
                          {'fields':['id','order_id','product_id','display_name','qty','note'] + (['x_impreso_cocina'] if has_flag else [])})

# agrupar por pedido
by_order = {}
for l in lines:
    oid = l['order_id'][0]
    by_order.setdefault(oid, []).append(l)

orders = models.execute_kw(DB, uid, PWD, 'pos.order', 'read', [list(by_order)], {'fields':['name','state','date_order','partner_id','table_id']})
omap = {o['id']:o for o in orders}

for oid, lst in by_order.items():
    o = omap[oid]
    print(f"\nPedido: {o['name']} | Estado: {o['state']} | Fecha: {o['date_order']}")
    for l in lst:
        nm = l.get('display_name') or l['product_id'][1]
        print(f"  - {l['qty']} x {nm}  {'(nota: '+l['note']+')' if l.get('note') else ''}")

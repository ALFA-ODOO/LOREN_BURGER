import os, xmlrpc.client
from dotenv import load_dotenv
load_dotenv()  # carga .env del directorio actual

print("ENV:", os.getenv("ODOO_URL"), os.getenv("ODOO_DB"), os.getenv("ODOO_USERNAME"))
url = os.getenv("ODOO_URL"); db = os.getenv("ODOO_DB"); usr = os.getenv("ODOO_USERNAME"); pwd = os.getenv("ODOO_PASSWORD")
assert all([url, db, usr, pwd]), "Faltan variables en .env"

uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, usr, pwd, {})
print("UID:", uid)

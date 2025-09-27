# LOREN_BURGER

## Descripción general
Este repositorio contiene los scripts que automatizan la impresión de comandas de cocina a partir de los pedidos cobrados en Odoo TPV. El flujo principal vive en `imprimir_cocina_win.py`, que consulta los pedidos pendientes de impresión, formatea el ticket para la impresora térmica y marca cada línea como impresa para evitar duplicados.

## Requisitos previos
- **Python 3.9+** instalado en Windows (el proceso de impresión usa librerías específicas de Windows).
- **Dependencias**: `pywin32`, `python-dotenv` y la librería estándar de Python.
- **Variables de entorno Odoo**: crear un archivo `.env` en la raíz del proyecto con las credenciales de acceso.

```env
ODOO_URL=https://tu-instancia.odoo.com
ODOO_DB=nombre_base
ODOO_USERNAME=usuario@example.com
ODOO_PASSWORD=contraseña
```

- **Impresora térmica** configurada en Windows. Si no se especifica una impresora, el script utilizará la predeterminada del sistema.

## Instalación
1. Clonar el repositorio y abrir una terminal en la carpeta del proyecto.
2. (Opcional) Crear y activar un entorno virtual.
3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
   > Si no existe `requirements.txt`, instalar manualmente: `pip install pywin32 python-dotenv`.
4. Crear el archivo `.env` con las variables indicadas.

## Flujo del proceso de comando cocina
1. **Conexión a Odoo**: el script se autentica usando las credenciales del `.env`.
2. **Selección de líneas**: busca líneas de pedidos TPV con cantidad positiva, estado `paid/done/invoiced` y que aún no tengan marcada la bandera `x_impreso_cocina`.
3. **Agrupado por pedido**: junta las líneas por pedido para generar un ticket por comanda.
4. **Generación del ticket**: formatea el contenido (encabezado, productos, notas) respetando el ancho de la impresora.
5. **Impresión**: envía el ticket a la impresora seleccionada. Por defecto usa la impresora predeterminada; se puede elegir otra con `--printer "Nombre"`.
6. **Marcado en Odoo**: tras imprimir, actualiza `x_impreso_cocina=True` para las líneas procesadas, evitando reimpresiones.

> El archivo `imprimir_cocina_config.json` se crea automáticamente para guardar preferencias como la impresora elegida y el intervalo de autoejecución en la GUI.

## Uso del comando principal
```bash
python imprimir_cocina_win.py [opciones]
```

Opciones más frecuentes:
- `--print-test`: imprime una página de prueba sin conectarse a Odoo.
- `--dry-run`: realiza toda la lógica sin imprimir ni escribir en Odoo (útil para pruebas).
- `--pos-categ <ID>`: filtra los productos por categoría de TPV (incluye subcategorías).
- `--printer "Nombre"`: fuerza una impresora distinta a la predeterminada de Windows.
- `--max-orders <N>`: limita la cantidad de pedidos procesados en una corrida.
- `--gui`: abre una interfaz básica para monitorear y ejecutar en intervalos automáticos (configurables con `--auto-interval`).

## Utilidades complementarias
- `listar_pos.py`: permite listar por consola las líneas que cumplen el dominio, útil para diagnosticar qué se imprimiría.

```bash
python listar_pos.py
```

## Buenas prácticas de operación
- Mantener abierta la sesión de Odoo para validar que los estados de los pedidos sean los esperados.
- Ejecutar primero con `--dry-run` cuando se cambien credenciales o categorías para confirmar el alcance.
- Revisar periódicamente la impresora (papel, conexión) y limpiar `imprimir_cocina_config.json` si se quiere restablecer la configuración.

## Solución de problemas
- **Faltan credenciales**: el script se detendrá avisando que faltan variables en `.env`.
- **No imprime**: verificar el nombre exacto de la impresora en Windows y pasarlo con `--printer`.
- **Errores de autenticación**: comprobar usuario y contraseña en Odoo, así como la URL y base de datos configurada.

## Créditos
Scripts y automatización preparados por Dany.

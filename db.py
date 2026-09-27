"""
Acceso a la base de datos (SQLite, sin ORM).

Por que sin ORM (ej. SQLAlchemy): el proyecto es una herramienta de
aprendizaje ademas de una herramienta de negocio, y con sqlite3 puro el
SQL de cada consulta queda explicito y facil de leer para alguien que
esta aprendiendo Python, en vez de quedar escondido detras de objetos y
magia de un ORM.

Por que SQLite: un solo archivo (`almuerzos_marisol.db`), sin servidor
que instalar ni configurar. El negocio de Marisol tiene un volumen bajo
de movimientos al dia, asi que SQLite sobra para este caso.
"""
import sqlite3
from pathlib import Path

# El archivo de base de datos vive junto a este modulo, no depende de
# desde donde se ejecute "python app.py".
DB_PATH = Path(__file__).parent / "almuerzos_marisol.db"

# Categorias fijas en el codigo (no en una tabla administrable) porque
# el paso 2 del plan las deja asi para esta fase: el negocio no necesita
# todavia agregar/quitar categorias desde la interfaz. Cada categoria
# tiene un "valor" interno (se guarda en la base de datos) y una
# "etiqueta" en lenguaje cotidiano (se muestra a Marisol).
CATEGORIAS_INGRESO = [
    ("almuerzo", "Almuerzo del menu del dia"),
    ("a_la_carta", "A la carta"),
    ("domicilio", "Cobro de domicilio"),
    # Las ventas del catalogo (postres, tinto, empanadas) caen aqui.
    # No se escoge a mano en el formulario: se escoge el producto y la
    # app pone esta categoria sola, guardando ademas cual producto fue.
    ("producto", "Productos del catalogo"),
]

CATEGORIAS_GASTO = [
    ("insumos", "Insumos / comida"),
    ("arriendo", "Arriendo"),
    ("servicios", "Servicios (luz, agua, gas)"),
    ("empaques", "Cubiertos y empaques"),
    ("domiciliario", "Pago a domiciliario"),
    # Los pagos a empleados caen aqui. Igual que con los productos, no
    # se escoge a mano: se registra el pago en la pantalla de Empleados
    # y la app crea el gasto con esta categoria.
    ("empleados", "Sueldos y empleados"),
    ("otros", "Otros"),
]

# Categorias que NO se escogen a mano en el formulario de venta/gasto
# porque las pone la app sola desde otra pantalla. Siguen en las listas
# de arriba para que los reportes y el historial sepan como se llaman.
CATEGORIAS_AUTOMATICAS = {"producto", "empleados"}

# Cada cuanto se le paga a un empleado. Es solo una referencia para
# saber cuanto deberia llevar pagado: el monto de cada pago se puede
# cambiar, porque en un negocio asi casi nunca es exacto.
FRECUENCIAS_PAGO = [
    ("dia", "Por dia trabajado"),
    ("semana", "Cada semana"),
    ("quincena", "Cada quincena"),
    ("mes", "Cada mes"),
]

# El medio de pago no estaba definido en los documentos del proyecto;
# es una decision pequena, asi que se toma aqui la opcion mas simple y
# comun para un negocio de este tipo. Queda anotada tambien en el
# README como una suposicion.
MEDIOS_PAGO = [
    ("efectivo", "Efectivo"),
    ("transferencia", "Transferencia"),
    ("otro", "Otro"),
]

# Partes de un almuerzo corriente, en el orden en que se sirven. El
# menu del dia se arma escogiendo platos dentro de estos grupos en vez
# de escribir un parrafo suelto.
#
# Por que grupos fijos y no etiquetas libres: el bot de WhatsApp que se
# va a construir despues necesita saber QUE esta escogiendo el cliente
# ("de las carnes, cual quiere") para poder tomar el pedido. Con
# etiquetas que cambian cada dia, el bot solo podria repetir el texto
# sin entenderlo. El grupo "otro" queda como valvula de escape para lo
# que no encaje en ninguno.
GRUPOS_MENU = [
    ("sopa", "Sopa"),
    ("principio", "Principio"),
    ("carne", "Carne"),
    ("acompanamiento", "Acompanamiento"),
    ("bebida", "Bebida"),
    ("postre", "Postre"),
    ("otro", "Otro"),
]


def get_connection():
    """Abre una conexion nueva a la base de datos.

    Se abre una conexion por peticion (patron estandar de Flask) en vez
    de reusar una sola conexion global, porque sqlite3.Connection no es
    segura para compartir entre hilos, y el servidor de desarrollo de
    Flask puede atender peticiones en hilos distintos.
    """
    conexion = sqlite3.connect(DB_PATH)
    # row_factory en sqlite3.Row permite acceder a las columnas por
    # nombre (fila["monto"]) en vez de por indice numerico, lo cual es
    # mucho mas facil de leer en las plantillas y en las rutas.
    conexion.row_factory = sqlite3.Row
    # Sin esto, SQLite ignora las llaves foraneas por defecto.
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def init_db():
    """Crea las tablas si no existen todavia.

    Se llama al arrancar la app para que la base de datos se
    autoconfigure sola la primera vez que alguien la corre, sin pasos
    manuales de instalacion (ej. sin tener que correr un script de
    migracion aparte).
    """
    conexion = get_connection()
    try:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS transacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
                categoria TEXT NOT NULL,
                descripcion TEXT,
                monto REAL NOT NULL CHECK (monto > 0),
                medio_pago TEXT NOT NULL,
                fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        # Indice por fecha porque el dashboard, el historial y los
        # reportes casi siempre filtran o agrupan por rango de fechas.
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_transacciones_fecha ON transacciones (fecha)"
        )
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_dia (
                fecha TEXT PRIMARY KEY,
                texto TEXT NOT NULL,
                fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )

        # Clientes que deben plata (fiado). El nombre escrito a mano es
        # el identificador (sin cedula ni telefono obligatorio, porque
        # el negocio no maneja esos datos hoy) - si dos clientes
        # distintos tuvieran exactamente el mismo nombre, sus deudas se
        # mezclarian. Es una limitacion simple y aceptada (ver README).
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )

        # Movimientos de fiado: un libro de cargos (lo que un cliente
        # queda debiendo) y abonos (lo que paga despues). El saldo de
        # un cliente se calcula sumando cargos y restando abonos en vez
        # de guardar un "saldo" en la tabla clientes, para que quede un
        # historial auditable de cada movimiento (y para no tener que
        # mantener sincronizado un numero aparte cada vez que algo
        # cambia).
        #
        # "transaccion_id" liga un cargo a la venta que lo origino, con
        # ON DELETE CASCADE: si Marisol borra esa venta del historial
        # (porque se equivoco al registrarla), el cargo de fiado que
        # vino de esa venta se borra con ella - de lo contrario
        # quedaria una deuda "fantasma" sin ninguna venta real detras.
        # Los abonos no tienen transaccion_id (no vienen de una venta
        # nueva, ver README), asi que no se ven afectados por esto.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS movimientos_fiado (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL REFERENCES clientes(id),
                tipo TEXT NOT NULL CHECK (tipo IN ('cargo', 'abono')),
                monto REAL NOT NULL CHECK (monto > 0),
                fecha TEXT NOT NULL,
                nota TEXT,
                transaccion_id INTEGER REFERENCES transacciones(id) ON DELETE CASCADE,
                fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_fiado_cliente ON movimientos_fiado (cliente_id)"
        )

        # Platos del menu de cada dia. Antes el menu era un solo texto
        # suelto; ahora cada plato es una fila con su grupo, para que
        # el bot de WhatsApp pueda ofrecer las opciones una por una en
        # vez de recitar un parrafo.
        #
        # "disponible" permite marcar que algo se acabo a mitad del dia
        # sin tener que borrarlo ni reescribir el menu entero.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                grupo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                disponible INTEGER NOT NULL DEFAULT 1,
                fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_menu_items_fecha ON menu_items (fecha)"
        )

        # El precio del almuerzo del dia se agrega a la tabla que ya
        # existia, sin borrarla: las bases de datos que ya estaban en
        # uso siguen funcionando y no se pierde ningun menu viejo.
        _agregar_columna_si_falta(conexion, "menu_dia", "precio", "REAL")

        # Capital inicial: la plata que Marisol ya tenia en el negocio
        # antes de empezar a usar la app. Es UNA sola fila (id = 1,
        # forzado con CHECK): no es un historial de movimientos, es un
        # punto de partida. Sin esto, la "caja total" empezaria en cero
        # aunque ella ya tuviera plata guardada, y el primer gasto
        # grande se veria como una perdida que en realidad no es.
        # Catalogo: lo que se vende aparte del almuerzo (postres, tinto,
        # empanadas). Guardar el precio sirve para tres cosas: que
        # registrar la venta sea escoger y no escribir, saber cuanto se
        # vendio de cada cosa, y poder mandar la lista por WhatsApp.
        #
        # "activo" en vez de borrar: si se borrara un producto, las
        # ventas viejas quedarian apuntando a algo que ya no existe.
        # Desactivarlo lo saca del formulario y del mensaje de WhatsApp
        # pero deja intacto el historial.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                precio REAL NOT NULL CHECK (precio > 0),
                activo INTEGER NOT NULL DEFAULT 1,
                fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )

        # Una venta puede venir del catalogo. Se guarda cual producto y
        # cuantos, para poder decir "esta semana vendiste 23 empanadas".
        # El monto sigue mandando: es lo que de verdad se cobro, que no
        # siempre es precio x cantidad (a veces se rebaja).
        _agregar_columna_si_falta(conexion, "transacciones", "producto_id", "INTEGER")
        _agregar_columna_si_falta(conexion, "transacciones", "cantidad", "REAL")

        # Empleados y lo que se les paga (la nomina).
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS empleados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                cargo TEXT,
                pago_acordado REAL,
                frecuencia TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )

        # Cada pago a un empleado es TAMBIEN un gasto del negocio. En vez
        # de guardar el monto dos veces (que se podrian desincronizar),
        # el pago apunta a la transaccion de gasto que lo representa,
        # igual que los cargos de fiado apuntan a su venta.
        #
        # ON DELETE CASCADE: si se borra ese gasto del historial, el
        # pago se va con el. De lo contrario la nomina diria que a
        # alguien se le pago una plata que ya no salio de ninguna parte.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos_empleado (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empleado_id INTEGER NOT NULL REFERENCES empleados(id),
                monto REAL NOT NULL CHECK (monto > 0),
                fecha TEXT NOT NULL,
                nota TEXT,
                transaccion_id INTEGER REFERENCES transacciones(id) ON DELETE CASCADE,
                fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_pagos_empleado ON pagos_empleado (empleado_id)"
        )

        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS capital_inicial (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                monto REAL NOT NULL CHECK (monto >= 0),
                fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )

        conexion.commit()
    finally:
        conexion.close()


def _agregar_columna_si_falta(conexion, tabla, columna, tipo):
    """Agrega una columna nueva a una tabla que ya existe, si no la tiene.

    SQLite no tiene "ALTER TABLE ... ADD COLUMN IF NOT EXISTS", asi que
    hay que preguntarle primero que columnas tiene. Esto permite que la
    app se actualice sola en un computador donde ya venia corriendo,
    sin que nadie tenga que borrar la base de datos ni correr un script
    de migracion aparte.

    Los nombres de tabla y columna vienen del codigo de esta misma app
    (nunca de un formulario), por eso se pueden poner directo en el SQL.
    """
    columnas = [fila["name"] for fila in conexion.execute(f"PRAGMA table_info({tabla})")]
    if columna not in columnas:
        conexion.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")

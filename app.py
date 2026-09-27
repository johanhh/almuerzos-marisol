"""
Almuerzos Marisol - app de cuentas del negocio.

Rutas principales: dashboard, registrar venta/gasto, historial (con
filtros y borrado), menu del dia y reportes. Ver README.md para las
decisiones de diseno y seguridad detras de esta app.
"""
import os
from datetime import date, datetime, timedelta
from urllib.parse import quote

from flask import Flask, flash, redirect, render_template, request, url_for

import db

app = Flask(__name__)

# La clave secreta es necesaria para que los mensajes flash (las
# confirmaciones de "Venta registrada", etc.) funcionen: Flask las
# firma para que no se puedan falsificar.
#
# Se lee de una variable de entorno y NO se escribe en el codigo,
# porque este proyecto esta publicado en un repositorio publico: una
# clave escrita aqui la podria ver cualquiera. Hoy solo firma mensajes
# de pantalla (no hay login ni datos de sesion), asi que el valor por
# defecto es suficiente para trabajar en el computador del negocio.
#
# El dia que se agregue login, ESTO YA NO PUEDE QUEDARSE ASI: hay que
# definir ALMUERZOS_SECRET_KEY con un valor largo y aleatorio, porque
# de esa clave dependeria que nadie pueda falsificar una sesion.
app.secret_key = os.environ.get(
    "ALMUERZOS_SECRET_KEY", "clave-solo-para-desarrollo-local"
)

# Se crean las tablas (si no existen) apenas arranca la app, para que
# la base de datos se autoconfigure sola sin pasos manuales de
# instalacion.
db.init_db()


MESES = [
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
]

# Dos letras y no una: "L, M, M" no se distingue, "Lu, Ma, Mi" si.
DIAS_CORTOS = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do"]


@app.template_filter("pesos")
def formato_pesos(valor):
    """Formatea un numero como pesos colombianos: $ 15.000.

    Se usa punto como separador de miles y sin decimales (el negocio
    no maneja centavos), para que los totales sean faciles de leer de
    un vistazo, tal como pide la guia de diseno visual.
    """
    signo = "-" if valor < 0 else ""
    return f"{signo}$ {abs(valor):,.0f}".replace(",", ".")


@app.template_filter("fecha_bonita")
def fecha_bonita(texto_fecha):
    """Convierte '2026-09-16' en algo que se lee facil: 'Hoy', 'Ayer'
    o '16 sep 2026'. Una fecha en formato de base de datos no le dice
    nada a alguien que solo quiere saber cuando fue."""
    try:
        fecha = datetime.strptime(texto_fecha, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return texto_fecha
    hoy = date.today()
    if fecha == hoy:
        return "Hoy"
    if fecha == hoy - timedelta(days=1):
        return "Ayer"
    return f"{fecha.day} {MESES[fecha.month - 1]} {fecha.year}"


@app.template_filter("iniciales")
def iniciales(nombre):
    """Las iniciales de un cliente, para el circulito de color que va
    en vez de una foto (el negocio no tiene fotos de sus clientes)."""
    partes = [p for p in (nombre or "").split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


@app.template_filter("color_avatar")
def color_avatar(nombre):
    """Reparte un color fijo por cliente a partir de su nombre, para
    que el mismo cliente siempre se vea del mismo color."""
    letras = "abcde"
    return letras[sum(ord(c) for c in (nombre or "?")) % len(letras)]


# ---------------------------------------------------------------------
# Validacion de datos que llegan de los formularios.
#
# Estas funciones existen porque la guia de diseno exige que un dato
# invalido (ej. texto en vez de numero) nunca haga que la app se caiga
# con un error tecnico: siempre debe devolver un mensaje claro para que
# Marisol pueda corregir.
# ---------------------------------------------------------------------

def _leer_numero_de_pesos(texto):
    """Lee un numero de pesos escrito a mano.

    En Colombia los miles se escriben con punto ("16.000"), a veces con
    coma ("16,000"), y es comun escribir el signo de pesos. Como el
    negocio no maneja centavos, esos separadores se ignoran y todo se
    lee como pesos enteros: "16.000", "16,000", "$ 16.000" y "16000"
    significan lo mismo.

    Esto es importante y no es un detalle cosmetico: antes se usaba
    float(texto.replace(",", ".")), y ahi float("16.000") daba 16 pesos
    en vez de 16.000 - lo que hacia que las restas del fiado dieran
    numeros que no tenian sentido.

    Devuelve (valor, None) si se pudo leer, o (None, codigo) si no,
    donde codigo es "vacio" o "no_numero" para que cada campo escriba
    el mensaje que le corresponde.
    """
    limpio = (texto or "").strip()
    for sobra in ("$", " ", ".", ","):
        limpio = limpio.replace(sobra, "")
    if not limpio:
        return None, "vacio"
    negativo = limpio.startswith("-")
    if negativo:
        limpio = limpio[1:]
    if not limpio.isdigit():
        return None, "no_numero"
    valor = float(limpio)
    return (-valor if negativo else valor), None


def parsear_monto(texto):
    """Convierte el texto del formulario en un monto valido.

    Devuelve (monto, None) si es valido, o (None, mensaje_error) si no.
    Un monto valido es un numero mayor que cero (no tiene sentido una
    venta o un gasto de $0 o negativo).
    """
    valor, problema = _leer_numero_de_pesos(texto)
    if problema == "vacio":
        return None, "Falta el monto. Escribe cuanto fue, por ejemplo 16000."
    if problema == "no_numero":
        return None, "El monto tiene que ser un numero, por ejemplo 16000."
    if valor <= 0:
        return None, "El monto tiene que ser mayor que cero."
    return valor, None


def parsear_monto_no_negativo(texto):
    """Como parsear_monto, pero permite 0.

    Se usa para "cuanto te dio ahora" cuando alguien queda debiendo: 0
    es valido (lo fio todo), pero un texto no numerico o negativo no.
    """
    valor, problema = _leer_numero_de_pesos(texto)
    if problema == "vacio":
        return 0.0, None
    if problema == "no_numero":
        return None, "Lo que te dio tiene que ser un numero, por ejemplo 5000."
    if valor < 0:
        return None, "Lo que te dio no puede ser negativo."
    return valor, None


def parsear_cantidad(texto):
    """Cuantas unidades se vendieron de un producto del catalogo.

    Si viene vacio se asume 1, que es lo mas comun (una empanada, un
    tinto). Tiene que ser un numero entero mayor que cero.
    """
    texto = (texto or "").strip()
    if not texto:
        return 1, None
    if not texto.isdigit() or int(texto) < 1:
        return None, "La cantidad tiene que ser un numero entero, por ejemplo 3."
    return int(texto), None


def parsear_fecha(texto):
    """Valida una fecha en formato YYYY-MM-DD (el que usa <input type=date>).

    Si el campo viene vacio, se asume que es hoy - asi Marisol no tiene
    que escribir la fecha cada vez que registra algo del dia actual.
    """
    texto = (texto or "").strip()
    if not texto:
        return date.today().isoformat(), None
    try:
        datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        return None, "La fecha no es valida."
    return texto, None


def categorias_validas(tipo):
    """Devuelve la lista de categorias permitidas segun el tipo de movimiento."""
    return db.CATEGORIAS_INGRESO if tipo == "ingreso" else db.CATEGORIAS_GASTO


def obtener_o_crear_cliente(con, nombre, telefono):
    """Busca un cliente por nombre (ignorando mayusculas y espacios de
    mas) y lo devuelve; si no existe, lo crea.

    El nombre es el identificador porque el negocio no maneja un
    documento de identidad de sus clientes. Si dos personas distintas
    tuvieran exactamente el mismo nombre, sus deudas se mezclarian -
    limitacion simple y aceptada, anotada en el README.
    """
    fila = con.execute(
        "SELECT id FROM clientes WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?))",
        (nombre,),
    ).fetchone()
    if fila:
        return fila["id"]
    cursor = con.execute(
        "INSERT INTO clientes (nombre, telefono) VALUES (?, ?)",
        (nombre.strip(), telefono or None),
    )
    return cursor.lastrowid


def total_por_cobrar(con):
    """El neto de todos los fiados: lo que deben menos lo que hay a favor.

    Este numero es el que necesita la caja, porque ahi lo que importa
    es cuanta plata entro de verdad. NO es el que se le muestra a
    Marisol como "te deben": para eso esta total_que_deben().
    """
    fila = con.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN tipo = 'cargo' THEN monto ELSE -monto END), 0) AS total
        FROM movimientos_fiado
        """
    ).fetchone()
    return fila["total"]


def total_que_deben(con):
    """Cuanto le deben a Marisol, contando solo a los que deben.

    Va aparte del neto a proposito. Si una persona debe 50.000 y otra
    tiene 10.000 a favor, a Marisol le deben 50.000, no 40.000: el
    saldo a favor de uno no es plata que le vaya a llegar del otro.
    Mezclarlos hacia que el inicio mostrara cosas como "Te deben
    -$ 11.000" junto a "Nadie te debe nada".
    """
    fila = con.execute(
        """
        SELECT COALESCE(SUM(saldo), 0) AS total FROM (
            SELECT SUM(CASE WHEN tipo = 'cargo' THEN monto ELSE -monto END) AS saldo
            FROM movimientos_fiado
            GROUP BY cliente_id
            HAVING saldo > 0
        )
        """
    ).fetchone()
    return fila["total"]


@app.context_processor
def datos_de_todas_las_pantallas():
    """Datos que aparecen en el marco de la app (barra lateral, avisos)
    sin importar en que pantalla este Marisol.

    Se calculan aqui, en un solo lugar, para no tener que acordarse de
    pasarlos a mano en cada ruta - si una ruta se olvidara, la barra
    lateral se veria incompleta en esa pantalla.
    """
    hoy = date.today()
    con = db.get_connection()
    try:
        grupos_hoy = items_del_dia(con, hoy.isoformat())
        fila_menu = con.execute(
            "SELECT texto FROM menu_dia WHERE fecha = ?", (hoy.isoformat(),)
        ).fetchone()

        deudores = con.execute(
            """
            SELECT c.nombre,
                   SUM(CASE WHEN m.tipo = 'cargo' THEN m.monto ELSE -m.monto END) AS saldo
            FROM clientes c
            JOIN movimientos_fiado m ON m.cliente_id = c.id
            GROUP BY c.id
            HAVING saldo > 0
            """
        ).fetchall()
    finally:
        con.close()

    # Resumen corto del menu para la barra lateral: los platos de cada
    # grupo separados por comas, sin los que ya se acabaron.
    resumen_menu = None
    if grupos_hoy:
        partes = []
        for grupo in grupos_hoy:
            disponibles = [p["nombre"] for p in grupo["platos"] if p["disponible"]]
            if disponibles:
                partes.append(", ".join(disponibles))
        resumen_menu = " · ".join(partes) or None
    elif fila_menu and fila_menu["texto"]:
        # Menus viejos, de cuando el menu era un solo texto suelto.
        resumen_menu = fila_menu["texto"]

    # Avisos reales, no adornos: cada uno sale de algo que de verdad
    # esta pendiente en el negocio hoy.
    avisos = []
    if not resumen_menu:
        avisos.append(
            {
                "titulo": "Falta el menu de hoy",
                "detalle": "Armalo para poder mandarlo por WhatsApp.",
                "enlace": url_for("menu_dia"),
            }
        )
    if deudores:
        total_deuda = sum(d["saldo"] for d in deudores)
        avisos.append(
            {
                "titulo": f"{len(deudores)} persona{'s' if len(deudores) != 1 else ''} te debe"
                          f"{'n' if len(deudores) != 1 else ''} plata",
                "detalle": f"En total {formato_pesos(total_deuda)} por cobrar.",
                "enlace": url_for("fiados"),
            }
        )

    return {
        "menu_de_hoy": resumen_menu,
        "cuantos_deben": len(deudores),
        "avisos": avisos,
        "hoy_bonito": f"{hoy.day} {MESES[hoy.month - 1]} {hoy.year}",
        "hoy_iso": hoy.isoformat(),
    }


def saldo_de_cliente(con, id_cliente):
    """Cuanto debe un cliente: sus cargos menos sus abonos.

    Puede dar negativo ("saldo a favor") si le abonaron mas de lo que
    debia - por ejemplo si se borro la venta que origino la deuda
    despues de que el cliente ya habia abonado. Ese caso NO se esconde
    (ver la ruta fiados): un saldo negativo invisible se comeria
    silenciosamente las deudas nuevas de esa persona.
    """
    fila = con.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN tipo = 'cargo' THEN monto ELSE -monto END), 0) AS saldo
        FROM movimientos_fiado WHERE cliente_id = ?
        """,
        (id_cliente,),
    ).fetchone()
    return fila["saldo"]


# ---------------------------------------------------------------------
# Consultas usadas por varias rutas (dashboard y reportes comparten la
# misma logica de "sumar ventas y gastos entre dos fechas").
# ---------------------------------------------------------------------

def totales_entre(con, fecha_desde, fecha_hasta, categoria=None):
    """Suma ventas, gastos y calcula el balance entre dos fechas (incluidas).

    Si se pasa una categoria, los totales solo cuentan esa categoria -
    lo usan los reportes para que las tarjetas de arriba (ventas,
    gastos, balance) reflejen el mismo filtro que la tabla de abajo.
    """
    consulta = """
        SELECT
            COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN monto END), 0) AS ventas,
            COALESCE(SUM(CASE WHEN tipo = 'gasto' THEN monto END), 0) AS gastos
        FROM transacciones
        WHERE fecha BETWEEN ? AND ?
    """
    parametros = [fecha_desde, fecha_hasta]
    if categoria:
        consulta += " AND categoria = ?"
        parametros.append(categoria)

    fila = con.execute(consulta, parametros).fetchone()
    return {
        "ventas": fila["ventas"],
        "gastos": fila["gastos"],
        "balance": fila["ventas"] - fila["gastos"],
    }


def caja_total(con):
    """Cuanta plata tiene el negocio en total, desde el principio.

    Es una pregunta distinta a la de los reportes: los reportes dicen
    "como me fue este mes" (ventas menos gastos de un periodo); esto
    dice "cuanto hay en caja ahora". Por eso NO se filtra por mes ni
    por categoria.

        en caja = capital inicial + todo lo vendido - todo lo gastado
                  - lo que todavia te deben

    Por que se resta lo que te deben: una venta fiada se cuenta
    completa como vendida el dia que se hace (asi se decidio para los
    reportes), pero esa plata todavia no entro a la caja. Si no se
    restara, la caja mostraria plata que Marisol no tiene en la mano.
    Cuando el cliente abona, lo que te deben baja y la caja sube sola,
    sin registrar una venta nueva. Un saldo a favor (deuda negativa)
    tambien cuadra solo: esa plata si entro, y restar un negativo suma.

    Solo es exacto si toda la plata que entra y sale se registra en la
    app: si se saca efectivo para algo personal sin anotarlo como
    gasto, la caja se va a ver mas llena de lo que esta.
    """
    fila_capital = con.execute(
        "SELECT monto, fecha_actualizacion FROM capital_inicial WHERE id = 1"
    ).fetchone()
    capital = fila_capital["monto"] if fila_capital else 0

    fila = con.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN monto END), 0) AS ventas,
            COALESCE(SUM(CASE WHEN tipo = 'gasto' THEN monto END), 0) AS gastos
        FROM transacciones
        """
    ).fetchone()

    por_cobrar = total_por_cobrar(con)
    en_caja = capital + fila["ventas"] - fila["gastos"] - por_cobrar

    return {
        "capital": capital,
        "capital_definido": fila_capital is not None,
        "ventas": fila["ventas"],
        "gastos": fila["gastos"],
        "por_cobrar": por_cobrar,
        "en_caja": en_caja,
        "si_te_pagan": en_caja + max(por_cobrar, 0),
    }


def serie_por_dia(con, dias=7):
    """Ventas y gastos de cada uno de los ultimos dias, para la grafica.

    Se trae todo en UNA sola consulta agrupada por fecha y luego se
    arma la lista completa en Python, incluyendo los dias en que no
    hubo nada. Si se dejaran por fuera los dias vacios, la grafica
    mentiria: un martes sin ventas se veria igual que un martes que no
    existe.
    """
    hoy = date.today()
    desde = hoy - timedelta(days=dias - 1)

    filas = con.execute(
        """
        SELECT fecha,
               COALESCE(SUM(CASE WHEN tipo = 'ingreso' THEN monto END), 0) AS ventas,
               COALESCE(SUM(CASE WHEN tipo = 'gasto' THEN monto END), 0) AS gastos
        FROM transacciones
        WHERE fecha BETWEEN ? AND ?
        GROUP BY fecha
        """,
        (desde.isoformat(), hoy.isoformat()),
    ).fetchall()
    por_fecha = {f["fecha"]: f for f in filas}

    serie = []
    for paso in range(dias):
        dia = desde + timedelta(days=paso)
        fila = por_fecha.get(dia.isoformat())
        serie.append(
            {
                "fecha": dia.isoformat(),
                "etiqueta": DIAS_CORTOS[dia.weekday()],
                "ventas": fila["ventas"] if fila else 0,
                "gastos": fila["gastos"] if fila else 0,
                "es_hoy": dia == hoy,
            }
        )
    return serie


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------

@app.route("/")
def dashboard():
    hoy = date.today()
    # "La semana" se define como los ultimos 7 dias incluyendo hoy (no
    # el lunes-domingo calendario). Esto no estaba definido en los
    # documentos del proyecto - se elige la version mas simple de
    # entender para alguien que revisa el dashboard rapido: "lo que ha
    # pasado en la ultima semana", sin pensar en calendarios. Queda
    # anotado como suposicion en el README.
    inicio_semana = hoy - timedelta(days=6)

    con = db.get_connection()
    try:
        resumen_hoy = totales_entre(con, hoy.isoformat(), hoy.isoformat())
        resumen_semana = totales_entre(con, inicio_semana.isoformat(), hoy.isoformat())

        grupos_menu_hoy = items_del_dia(con, hoy.isoformat())
        fila_menu_hoy = con.execute(
            "SELECT * FROM menu_dia WHERE fecha = ?", (hoy.isoformat(),)
        ).fetchone()

        ultimos_movimientos = con.execute(
            """
            SELECT * FROM transacciones
            ORDER BY fecha DESC, fecha_creacion DESC
            LIMIT 6
            """
        ).fetchall()

        por_cobrar = total_que_deben(con)
        serie = serie_por_dia(con, dias=7)

        # Los 4 que mas deben, para verlos sin salir del inicio.
        deudores = con.execute(
            """
            SELECT c.id, c.nombre, c.telefono,
                   SUM(CASE WHEN m.tipo = 'cargo' THEN m.monto ELSE -m.monto END) AS saldo
            FROM clientes c
            JOIN movimientos_fiado m ON m.cliente_id = c.id
            GROUP BY c.id
            HAVING saldo > 0
            ORDER BY saldo DESC
            LIMIT 4
            """
        ).fetchall()

        resumen_mes = totales_entre(
            con, hoy.replace(day=1).isoformat(), hoy.isoformat()
        )
    finally:
        con.close()

    # "De cada peso que vendiste este mes, cuanto te queda" - el numero
    # del medidor. Si todavia no hay ventas, no hay nada que medir.
    if resumen_mes["ventas"] > 0:
        margen = round(resumen_mes["balance"] / resumen_mes["ventas"] * 100)
    else:
        margen = 0
    margen_visible = max(0, min(100, margen))

    # La barra mas alta de la grafica marca el 100%; las demas se miden
    # contra ella.
    tope = max([d["ventas"] for d in serie] + [1])

    return render_template(
        "dashboard.html",
        resumen_hoy=resumen_hoy,
        resumen_semana=resumen_semana,
        resumen_mes=resumen_mes,
        grupos_menu_hoy=grupos_menu_hoy,
        precio_hoy=fila_menu_hoy["precio"] if fila_menu_hoy else None,
        ultimos_movimientos=ultimos_movimientos,
        por_cobrar=por_cobrar,
        serie=serie,
        tope_grafica=tope,
        deudores=deudores,
        margen=margen,
        margen_visible=margen_visible,
        categorias_por_valor=_mapa_categorias(),
    )


def _mapa_categorias():
    """Diccionario {valor: etiqueta} de todas las categorias, para mostrar
    la etiqueta en lenguaje cotidiano en vez del valor interno guardado
    en la base de datos (ej. 'a_la_carta' -> 'A la carta')."""
    todas = db.CATEGORIAS_INGRESO + db.CATEGORIAS_GASTO
    return dict(todas)


# ---------------------------------------------------------------------
# Registrar venta / registrar gasto
#
# Comparten la misma plantilla y la misma logica de guardado (la unica
# diferencia real es el "tipo" y la lista de categorias), tal como pide
# el paso 4 del plan ("formulario de movimiento - reutilizable entre
# venta y gasto").
# ---------------------------------------------------------------------

def _clientes_para_datalist(con):
    """Nombres de clientes ya conocidos, para el autocompletar del
    campo "quien debe" (no obliga a escoger uno, solo ayuda a escribir
    el nombre igual que la vez anterior)."""
    filas = con.execute("SELECT nombre FROM clientes ORDER BY nombre").fetchall()
    return [f["nombre"] for f in filas]


def _productos_activos(con):
    """El catalogo que se puede vender hoy, sin lo desactivado."""
    return con.execute(
        "SELECT * FROM productos WHERE activo = 1 ORDER BY nombre"
    ).fetchall()


def _formulario_movimiento(tipo, titulo, url_volver):
    categorias = categorias_validas(tipo)
    # Las categorias que pone la app sola (productos, sueldos) no se
    # ofrecen para escoger a mano: se llegan desde su propia pantalla.
    categorias_escogibles = [
        (valor, etiqueta)
        for valor, etiqueta in categorias
        if valor not in db.CATEGORIAS_AUTOMATICAS
    ]

    if request.method == "POST":
        categoria = request.form.get("categoria", "")
        medio_pago = request.form.get("medio_pago", "")
        descripcion = request.form.get("descripcion", "").strip()

        monto, error_monto = parsear_monto(request.form.get("monto"))
        fecha, error_fecha = parsear_fecha(request.form.get("fecha"))

        errores = []
        if error_monto:
            errores.append(error_monto)
        if error_fecha:
            errores.append(error_fecha)
        if medio_pago not in dict(db.MEDIOS_PAGO):
            errores.append("Escoge un medio de pago de la lista.")

        # Venta del catalogo: el desplegable manda "producto:5" en vez de
        # una categoria normal. Se traduce a la categoria "producto" mas
        # el id del producto, para poder decir despues cuanto se vendio
        # de cada cosa.
        producto_id = None
        cantidad = None
        if tipo == "ingreso" and categoria.startswith("producto:"):
            con = db.get_connection()
            try:
                try:
                    posible_id = int(categoria.split(":", 1)[1])
                except ValueError:
                    posible_id = 0
                producto = con.execute(
                    "SELECT * FROM productos WHERE id = ?", (posible_id,)
                ).fetchone()
            finally:
                con.close()

            if producto is None:
                errores.append("Ese producto del catalogo ya no existe.")
            else:
                producto_id = producto["id"]
                categoria = "producto"
                cantidad, error_cantidad = parsear_cantidad(
                    request.form.get("cantidad")
                )
                if error_cantidad:
                    errores.append(error_cantidad)
                if not descripcion:
                    # Sin esto, el historial mostraria solo "Productos del
                    # catalogo" y no se sabria que fue lo que se vendio.
                    unidades = int(cantidad) if cantidad else 1
                    descripcion = f"{unidades} x {producto['nombre']}"
        elif categoria not in dict(categorias_escogibles):
            errores.append("Escoge una categoria de la lista.")

        # Fiado: solo tiene sentido en una venta (un gasto no se "fia").
        # Si Marisol dice que no le pagaron completo, pide el nombre de
        # quien quedo debiendo y cuanto pago ahora (puede ser 0). El
        # resto (monto de la venta - lo que pago ahora) es lo que se le
        # fio, y se guarda en el libro de fiados del cliente.
        pago_completo = True
        cliente_nombre = ""
        cliente_telefono = ""
        monto_pagado_ahora = None
        if tipo == "ingreso":
            pago_completo = request.form.get("pago_completo", "si") != "no"
            if not pago_completo:
                cliente_nombre = request.form.get("cliente_nombre", "").strip()
                cliente_telefono = request.form.get("cliente_telefono", "").strip()
                monto_pagado_ahora, error_pagado = parsear_monto_no_negativo(
                    request.form.get("monto_pagado_ahora")
                )
                if error_pagado:
                    errores.append(error_pagado)
                if not cliente_nombre:
                    errores.append("Escribe el nombre de quien quedo debiendo.")
                if (
                    monto is not None
                    and monto_pagado_ahora is not None
                    and monto_pagado_ahora > monto
                ):
                    errores.append(
                        "Lo que te dio no puede ser mas de lo que vale la venta."
                    )

        if errores:
            for mensaje in errores:
                flash(mensaje, "error")
            # Se vuelve a mostrar el formulario con lo que ya habia
            # escrito Marisol, para que no tenga que llenarlo de nuevo
            # desde cero por un solo campo mal.
            con = db.get_connection()
            try:
                clientes_existentes = _clientes_para_datalist(con)
                productos = _productos_activos(con)
            finally:
                con.close()
            return render_template(
                "movimiento_form.html",
                tipo=tipo,
                titulo=titulo,
                categorias=categorias_escogibles,
                productos=productos,
                medios_pago=db.MEDIOS_PAGO,
                valores=request.form,
                clientes_existentes=clientes_existentes,
            )

        con = db.get_connection()
        try:
            cursor = con.execute(
                """
                INSERT INTO transacciones
                    (fecha, tipo, categoria, descripcion, monto, medio_pago,
                     producto_id, cantidad)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (fecha, tipo, categoria, descripcion or None, monto, medio_pago,
                 producto_id, cantidad),
            )
            id_transaccion = cursor.lastrowid

            monto_pendiente = 0
            if tipo == "ingreso" and not pago_completo:
                monto_pendiente = round(monto - monto_pagado_ahora, 2)
                if monto_pendiente > 0:
                    id_cliente = obtener_o_crear_cliente(con, cliente_nombre, cliente_telefono)
                    con.execute(
                        """
                        INSERT INTO movimientos_fiado
                            (cliente_id, tipo, monto, fecha, nota, transaccion_id)
                        VALUES (?, 'cargo', ?, ?, ?, ?)
                        """,
                        (id_cliente, monto_pendiente, fecha, descripcion or None, id_transaccion),
                    )
            con.commit()
        finally:
            con.close()

        etiqueta = "Venta registrada" if tipo == "ingreso" else "Gasto registrado"
        mensaje = f"{etiqueta}. Guardamos {formato_pesos(monto)}."
        if monto_pendiente > 0:
            mensaje += f" {cliente_nombre} te queda debiendo {formato_pesos(monto_pendiente)}."
        flash(mensaje, "exito")
        return redirect(url_for(url_volver))

    con = db.get_connection()
    try:
        clientes_existentes = _clientes_para_datalist(con)
        productos = _productos_activos(con)
    finally:
        con.close()

    return render_template(
        "movimiento_form.html",
        tipo=tipo,
        titulo=titulo,
        categorias=categorias_escogibles,
        productos=productos,
        medios_pago=db.MEDIOS_PAGO,
        valores={"fecha": date.today().isoformat(), "pago_completo": "si"},
        clientes_existentes=clientes_existentes,
    )


@app.route("/ventas/nueva", methods=["GET", "POST"])
def venta_nueva():
    return _formulario_movimiento("ingreso", "Registrar venta", "dashboard")


@app.route("/gastos/nueva", methods=["GET", "POST"])
def gasto_nuevo():
    return _formulario_movimiento("gasto", "Registrar gasto", "dashboard")


# ---------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------

@app.route("/historial")
def historial():
    tipo = request.args.get("tipo", "todos")
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")
    buscar = request.args.get("buscar", "").strip()

    condiciones = []
    parametros = []

    if tipo in ("ingreso", "gasto"):
        condiciones.append("tipo = ?")
        parametros.append(tipo)

    # Busqueda libre: es la que usa el buscador de la barra de arriba.
    # Mira la nota y la categoria, que es donde Marisol escribe algo
    # reconocible ("mesa 3", "arriendo").
    if buscar:
        condiciones.append("(descripcion LIKE ? OR categoria LIKE ?)")
        comodin = f"%{buscar}%"
        parametros.extend([comodin, comodin])

    # Fechas invalidas en los filtros no deben tumbar la pagina: se
    # ignoran silenciosamente y se muestra el historial sin ese filtro,
    # ya que un filtro mal escrito no es un error grave, solo se
    # aplica lo que si es valido.
    if desde:
        try:
            datetime.strptime(desde, "%Y-%m-%d")
            condiciones.append("fecha >= ?")
            parametros.append(desde)
        except ValueError:
            desde = ""
    if hasta:
        try:
            datetime.strptime(hasta, "%Y-%m-%d")
            condiciones.append("fecha <= ?")
            parametros.append(hasta)
        except ValueError:
            hasta = ""

    consulta = "SELECT * FROM transacciones"
    if condiciones:
        consulta += " WHERE " + " AND ".join(condiciones)
    consulta += " ORDER BY fecha DESC, fecha_creacion DESC"

    con = db.get_connection()
    try:
        movimientos = con.execute(consulta, parametros).fetchall()
    finally:
        con.close()

    # Totales de lo que se esta viendo con los filtros puestos, para
    # que la pantalla responda "cuanto suma esto que estoy mirando".
    ventas = sum(m["monto"] for m in movimientos if m["tipo"] == "ingreso")
    gastos = sum(m["monto"] for m in movimientos if m["tipo"] == "gasto")

    return render_template(
        "historial.html",
        movimientos=movimientos,
        tipo=tipo,
        desde=desde,
        hasta=hasta,
        buscar=buscar,
        totales={"ventas": ventas, "gastos": gastos, "balance": ventas - gastos},
        categorias_por_valor=_mapa_categorias(),
    )


@app.route("/historial/eliminar/<int:id_movimiento>", methods=["POST"])
def eliminar_movimiento(id_movimiento):
    # Eliminar es una accion que solo debe ocurrir con POST (no con un
    # simple link GET), para que no se pueda borrar un registro por
    # accidente con un clic derecho -> abrir en pestana nueva, o si
    # algo precarga la pagina.
    con = db.get_connection()
    try:
        # Antes de borrar hay que mirar a quien le habia quedado
        # debiendo esta venta, porque al borrarla se borra tambien ese
        # cargo (ON DELETE CASCADE) y el cliente puede quedar con saldo
        # a favor si ya habia abonado algo. Eso hay que avisarlo, no
        # dejarlo pasar en silencio.
        afectados = con.execute(
            """
            SELECT DISTINCT c.id, c.nombre
            FROM movimientos_fiado m
            JOIN clientes c ON c.id = m.cliente_id
            WHERE m.transaccion_id = ?
            """,
            (id_movimiento,),
        ).fetchall()

        con.execute("DELETE FROM transacciones WHERE id = ?", (id_movimiento,))
        con.commit()

        flash("Listo, borramos ese registro.", "exito")
        for cliente in afectados:
            saldo = saldo_de_cliente(con, cliente["id"])
            if saldo < 0:
                flash(
                    f"{cliente['nombre']} ya te habia abonado por esa venta, "
                    f"asi que le quedo un saldo a favor de {formato_pesos(-saldo)}. "
                    f"Revisa su cuenta en 'Quien debe'.",
                    "error",
                )
            else:
                flash(
                    f"Tambien quitamos lo que {cliente['nombre']} debia por esa venta.",
                    "exito",
                )
    finally:
        con.close()

    return redirect(url_for("historial"))


# ---------------------------------------------------------------------
# Menu del dia
# ---------------------------------------------------------------------

def items_del_dia(con, fecha):
    """Los platos de un dia, ya agrupados y en el orden en que se sirven.

    Devuelve una lista de {clave, etiqueta, platos} para poder recorrerla
    directo en la plantilla, en vez de que la plantilla tenga que hacer
    la logica de agrupar.
    """
    filas = con.execute(
        "SELECT * FROM menu_items WHERE fecha = ? ORDER BY id", (fecha,)
    ).fetchall()

    grupos = []
    for clave, etiqueta in db.GRUPOS_MENU:
        platos = [f for f in filas if f["grupo"] == clave]
        if platos:
            grupos.append({"clave": clave, "etiqueta": etiqueta, "platos": platos})
    return grupos


def saludo_segun_la_hora():
    """"Buenos dias", "Buenas tardes" o "Buenas noches" segun la hora.

    Marisol manda el menu a distintas horas (temprano para los que
    encargan, al mediodia para los que pasan). Que el saludo cambie
    solo evita el "buenos dias" a las 4 de la tarde.
    """
    hora = datetime.now().hour
    if hora < 12:
        return "Buenos dias"
    if hora < 19:
        return "Buenas tardes"
    return "Buenas noches"


def texto_del_menu(grupos, precio, nota, productos=None):
    """Arma el mensaje completo que se manda por WhatsApp.

    No es solo la lista de platos: es un mensaje ya escrito, con saludo
    y despedida, listo para mandarle a un cliente sin tener que
    escribir nada. Mientras no exista el bot, esto es lo que hace que
    mandar el menu sea un solo clic.

    Se genera desde los mismos datos que se ven en pantalla, para que
    el menu no se escriba dos veces (una para la app y otra para
    WhatsApp) y nunca queden diciendo cosas distintas. Lo que ya se
    acabo no se incluye: no tiene sentido ofrecerle al cliente algo que
    no hay.
    """
    hay_platos = any(
        any(p["disponible"] for p in grupo["platos"]) for grupo in grupos
    )

    lineas = [f"Hola, {saludo_segun_la_hora().lower()}!", ""]

    if hay_platos:
        lineas.append("Este es el menu de hoy en Almuerzos Marisol:")
        lineas.append("")
        for grupo in grupos:
            disponibles = [p["nombre"] for p in grupo["platos"] if p["disponible"]]
            if disponibles:
                lineas.append(f"{grupo['etiqueta']}: {', '.join(disponibles)}")
    else:
        lineas.append("Le escribimos de Almuerzos Marisol.")

    if precio:
        lineas.append("")
        lineas.append(f"El almuerzo completo vale {formato_pesos(precio)}")

    # El catalogo va en el mismo mensaje: el cliente que pregunta por el
    # almuerzo es el mismo que se lleva el postre o el tinto, y asi no
    # hay que mandar dos mensajes.
    if productos:
        lineas.append("")
        lineas.append("Tambien tenemos:")
        for producto in productos:
            lineas.append(f"{producto['nombre']}: {formato_pesos(producto['precio'])}")

    if nota:
        lineas.append("")
        lineas.append(nota)

    lineas.append("")
    lineas.append("Si quiere pedir, respondame por aqui y con gusto le tomo el pedido.")
    return "\n".join(lineas)


@app.route("/menu")
def menu_dia():
    hoy = date.today().isoformat()

    con = db.get_connection()
    try:
        menu_hoy = con.execute(
            "SELECT * FROM menu_dia WHERE fecha = ?", (hoy,)
        ).fetchone()
        grupos = items_del_dia(con, hoy)

        # Dias anteriores que tuvieron menu, para poder consultarlos y
        # para el boton de "copiar".
        fechas_anteriores = con.execute(
            """
            SELECT DISTINCT fecha FROM menu_items
            WHERE fecha < ? ORDER BY fecha DESC LIMIT 7
            """,
            (hoy,),
        ).fetchall()
        anteriores = []
        for fila in fechas_anteriores:
            anteriores.append(
                {"fecha": fila["fecha"], "grupos": items_del_dia(con, fila["fecha"])}
            )

        # Menus viejos de cuando el menu era un solo texto suelto, para
        # que no se pierdan de vista despues del cambio.
        menus_de_texto = con.execute(
            """
            SELECT fecha, texto FROM menu_dia
            WHERE fecha < ? AND texto IS NOT NULL AND texto <> ''
            ORDER BY fecha DESC LIMIT 7
            """,
            (hoy,),
        ).fetchall()

        # Platos que Marisol ya ha usado antes, para autocompletar y no
        # tener que escribir "sancocho de gallina" entero cada vez.
        ya_usados = con.execute(
            "SELECT DISTINCT nombre FROM menu_items ORDER BY nombre"
        ).fetchall()

        hay_para_copiar = len(fechas_anteriores) > 0
        productos = _productos_activos(con)
    finally:
        con.close()

    precio = menu_hoy["precio"] if menu_hoy else None
    nota = menu_hoy["texto"] if menu_hoy else None

    # Enlace de "click to chat" de WhatsApp (api.whatsapp.com/send): abre
    # WhatsApp con el texto ya escrito y deja que Marisol escoja a quien
    # mandarlo (un contacto, un grupo). No es la API oficial de Meta
    # Cloud API ni un bot - es el mismo mecanismo que un boton de
    # "compartir por WhatsApp" de cualquier pagina web, asi que no
    # necesita cuenta de WhatsApp Business ni tokens. La integracion
    # real con el bot (fuera de esta fase) se explica en el README.
    whatsapp_url = None
    vista_previa = None
    if grupos or nota or productos:
        vista_previa = texto_del_menu(grupos, precio, nota, productos)
        whatsapp_url = "https://api.whatsapp.com/send?text=" + quote(vista_previa)

    return render_template(
        "menu.html",
        grupos=grupos,
        grupos_menu=db.GRUPOS_MENU,
        precio=precio,
        nota=nota,
        anteriores=anteriores,
        menus_de_texto=menus_de_texto,
        platos_conocidos=[f["nombre"] for f in ya_usados],
        hay_para_copiar=hay_para_copiar,
        vista_previa=vista_previa,
        whatsapp_url=whatsapp_url,
    )


@app.route("/menu/agregar", methods=["POST"])
def menu_agregar():
    grupo = request.form.get("grupo", "")
    nombre = request.form.get("nombre", "").strip()

    if grupo not in dict(db.GRUPOS_MENU):
        flash("Escoge de que parte del almuerzo es ese plato.", "error")
    elif not nombre:
        flash("Escribe el nombre del plato antes de agregarlo.", "error")
    else:
        con = db.get_connection()
        try:
            con.execute(
                "INSERT INTO menu_items (fecha, grupo, nombre) VALUES (?, ?, ?)",
                (date.today().isoformat(), grupo, nombre),
            )
            con.commit()
        finally:
            con.close()
        flash(f"Agregamos {nombre} al menu de hoy.", "exito")
    return redirect(url_for("menu_dia"))


@app.route("/menu/item/<int:id_item>/quitar", methods=["POST"])
def menu_quitar(id_item):
    con = db.get_connection()
    try:
        fila = con.execute(
            "SELECT nombre FROM menu_items WHERE id = ?", (id_item,)
        ).fetchone()
        con.execute("DELETE FROM menu_items WHERE id = ?", (id_item,))
        con.commit()
    finally:
        con.close()
    if fila:
        flash(f"Quitamos {fila['nombre']} del menu.", "exito")
    return redirect(url_for("menu_dia"))


@app.route("/menu/item/<int:id_item>/alternar", methods=["POST"])
def menu_alternar(id_item):
    """Marca un plato como agotado, o lo vuelve a poner disponible.

    Se guarda en vez de borrarlo para que quede el registro de que ese
    plato si estuvo en el menu de hoy (y para poder volver a activarlo
    si aparece mas).
    """
    con = db.get_connection()
    try:
        fila = con.execute(
            "SELECT nombre, disponible FROM menu_items WHERE id = ?", (id_item,)
        ).fetchone()
        if fila:
            nuevo = 0 if fila["disponible"] else 1
            con.execute(
                "UPDATE menu_items SET disponible = ? WHERE id = ?", (nuevo, id_item)
            )
            con.commit()
            if nuevo:
                flash(f"{fila['nombre']} vuelve a estar disponible.", "exito")
            else:
                flash(f"Marcamos que se acabo el {fila['nombre']}.", "exito")
    finally:
        con.close()
    return redirect(url_for("menu_dia"))


@app.route("/menu/detalles", methods=["POST"])
def menu_detalles():
    """Guarda el precio del almuerzo del dia y la nota opcional."""
    nota = request.form.get("nota", "").strip()
    texto_precio = request.form.get("precio", "").strip()

    precio = None
    if texto_precio:
        precio, error = parsear_monto(texto_precio)
        if error:
            flash(error, "error")
            return redirect(url_for("menu_dia"))

    con = db.get_connection()
    try:
        # "Ultimo que guarda gana": si dos personas editan el menu del
        # mismo dia, queda lo ultimo guardado. Con una sola persona
        # usando la app esto es mas que suficiente (ver README).
        con.execute(
            """
            INSERT INTO menu_dia (fecha, texto, precio)
            VALUES (?, ?, ?)
            ON CONFLICT(fecha) DO UPDATE SET
                texto = excluded.texto,
                precio = excluded.precio,
                fecha_actualizacion = datetime('now', 'localtime')
            """,
            # La nota se guarda como texto vacio y no como NULL: la
            # columna viene de cuando el menu ERA ese texto y quedo
            # declarada NOT NULL. Guardar NULL aqui tumbaba la app al
            # guardar solo el precio sin escribir nota.
            (date.today().isoformat(), nota, precio),
        )
        con.commit()
    finally:
        con.close()
    flash("Guardamos el precio y la nota.", "exito")
    return redirect(url_for("menu_dia"))


@app.route("/menu/copiar", methods=["POST"])
def menu_copiar():
    """Copia a hoy el menu del ultimo dia que tuvo platos.

    Los menus se repiten mucho de una semana a otra, y Marisol arma
    esto cada manana mientras atiende: copiar y ajustar es mucho mas
    rapido que escribir todo de nuevo.
    """
    hoy = date.today().isoformat()
    fecha_origen = request.form.get("fecha", "").strip()

    con = db.get_connection()
    try:
        if not fecha_origen:
            fila = con.execute(
                "SELECT fecha FROM menu_items WHERE fecha < ? ORDER BY fecha DESC LIMIT 1",
                (hoy,),
            ).fetchone()
            fecha_origen = fila["fecha"] if fila else None

        if not fecha_origen:
            flash("Todavia no hay ningun menu anterior para copiar.", "error")
            return redirect(url_for("menu_dia"))

        # No se duplica lo que ya esta puesto hoy: si Marisol copia dos
        # veces por error, el menu no termina con todo repetido.
        ya_hay = {
            (f["grupo"], f["nombre"].lower())
            for f in con.execute(
                "SELECT grupo, nombre FROM menu_items WHERE fecha = ?", (hoy,)
            )
        }

        copiados = 0
        for fila in con.execute(
            "SELECT grupo, nombre FROM menu_items WHERE fecha = ? ORDER BY id",
            (fecha_origen,),
        ).fetchall():
            if (fila["grupo"], fila["nombre"].lower()) in ya_hay:
                continue
            con.execute(
                "INSERT INTO menu_items (fecha, grupo, nombre) VALUES (?, ?, ?)",
                (hoy, fila["grupo"], fila["nombre"]),
            )
            copiados += 1
        con.commit()
    finally:
        con.close()

    if copiados:
        flash(f"Copiamos {copiados} plato{'s' if copiados != 1 else ''} al menu de hoy.", "exito")
    else:
        flash("Ese menu ya estaba completo en el de hoy.", "exito")
    return redirect(url_for("menu_dia"))


# ---------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------

@app.route("/reportes")
def reportes():
    mes_parametro = request.args.get("mes", "")
    try:
        mes_actual = datetime.strptime(mes_parametro, "%Y-%m")
    except ValueError:
        mes_actual = datetime.today().replace(day=1)
        mes_parametro = mes_actual.strftime("%Y-%m")

    # Filtro opcional por categoria: si Marisol escoge una categoria
    # (ej. "Arriendo"), tanto las tarjetas de arriba como la tabla de
    # abajo deben quedar limitadas a esa categoria - de lo contrario
    # las tarjetas mostrarian el total de TODO el mes mientras la
    # tabla muestra solo una categoria, lo cual confundiria mas de lo
    # que ayuda.
    categoria_parametro = request.args.get("categoria", "")
    if categoria_parametro not in _mapa_categorias():
        categoria_parametro = ""

    desde = mes_actual.replace(day=1).date().isoformat()
    # Primer dia del mes siguiente, menos un dia, calculado sin
    # depender de cuantos dias tiene cada mes.
    if mes_actual.month == 12:
        siguiente = mes_actual.replace(year=mes_actual.year + 1, month=1, day=1)
    else:
        siguiente = mes_actual.replace(month=mes_actual.month + 1, day=1)
    hasta = (siguiente.date() - timedelta(days=1)).isoformat()

    con = db.get_connection()
    try:
        balance_mes = totales_entre(con, desde, hasta, categoria_parametro or None)

        consulta = """
            SELECT tipo, categoria, SUM(monto) AS total
            FROM transacciones
            WHERE fecha BETWEEN ? AND ?
        """
        parametros = [desde, hasta]
        if categoria_parametro:
            consulta += " AND categoria = ?"
            parametros.append(categoria_parametro)
        consulta += " GROUP BY tipo, categoria ORDER BY tipo, total DESC"

        por_categoria = con.execute(consulta, parametros).fetchall()
        caja = caja_total(con)

        # Que tanto se vendio de cada producto del catalogo en el mes.
        por_producto = con.execute(
            """
            SELECT p.nombre,
                   COALESCE(SUM(t.cantidad), 0) AS unidades,
                   SUM(t.monto) AS total
            FROM transacciones t
            JOIN productos p ON p.id = t.producto_id
            WHERE t.fecha BETWEEN ? AND ?
            GROUP BY p.id
            ORDER BY total DESC
            """,
            (desde, hasta),
        ).fetchall()
    finally:
        con.close()

    # La categoria mas grande marca el 100% de la barra; el resto se
    # mide contra ella, para que se vea de un vistazo cual pesa mas.
    tope_categoria = max([f["total"] for f in por_categoria] + [1])

    return render_template(
        "reportes.html",
        caja=caja,
        por_producto=por_producto,
        mes_parametro=mes_parametro,
        tope_categoria=tope_categoria,
        categoria_parametro=categoria_parametro,
        categorias_ingreso=db.CATEGORIAS_INGRESO,
        categorias_gasto=db.CATEGORIAS_GASTO,
        balance_mes=balance_mes,
        por_categoria=por_categoria,
        categorias_por_valor=_mapa_categorias(),
    )


@app.route("/capital-inicial", methods=["POST"])
def guardar_capital_inicial():
    """Guarda (o corrige) la plata con la que arranco el negocio en la app.

    Se permite cero: un negocio puede arrancar sin nada ahorrado. Lo que
    no se permite es negativo o un texto que no sea numero.
    """
    monto, error = parsear_monto_no_negativo(request.form.get("capital"))
    if error:
        flash(error.replace("Lo que te dio", "El capital inicial"), "error")
        return redirect(url_for("reportes"))

    con = db.get_connection()
    try:
        # Una sola fila (id = 1): si ya existia se reemplaza el valor,
        # porque esto es un punto de partida y no un movimiento que se
        # acumule. Corregirlo no borra ninguna venta ni gasto.
        con.execute(
            """
            INSERT INTO capital_inicial (id, monto) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET
                monto = excluded.monto,
                fecha_actualizacion = datetime('now', 'localtime')
            """,
            (monto,),
        )
        con.commit()
    finally:
        con.close()

    flash(f"Guardamos el capital inicial: {formato_pesos(monto)}.", "exito")
    return redirect(url_for("reportes"))


# ---------------------------------------------------------------------
# Fiados (cuentas por cobrar)
#
# Un cliente queda debiendo cuando, al registrar una venta, Marisol
# marca que no le pagaron completo (ver _formulario_movimiento). Esta
# seccion es para ver quien debe y anotar los abonos (pagos) que van
# haciendo despues.
# ---------------------------------------------------------------------

# Formas de ordenar la lista de "quien debe". Se guardan en un
# diccionario (lista blanca) y nunca se pega el texto que llega de la
# URL directamente dentro del SQL: solo se usa la clave para escoger
# uno de estos pedazos de ORDER BY escritos aqui. Asi no hay forma de
# inyectar SQL a traves del parametro "orden".
ORDENES_FIADOS = {
    "nombre": "c.nombre COLLATE NOCASE ASC",
    "nombre_desc": "c.nombre COLLATE NOCASE DESC",
    "telefono": "c.telefono IS NULL, c.telefono ASC",
    "telefono_desc": "c.telefono IS NULL, c.telefono DESC",
    "mas_debe": "saldo DESC",
    "menos_debe": "saldo ASC",
}


@app.route("/fiados")
def fiados():
    buscar = request.args.get("buscar", "").strip()
    orden = request.args.get("orden", "mas_debe")
    if orden not in ORDENES_FIADOS:
        orden = "mas_debe"

    consulta = """
        SELECT
            c.id,
            c.nombre,
            c.telefono,
            SUM(CASE WHEN m.tipo = 'cargo' THEN m.monto ELSE -m.monto END) AS saldo
        FROM clientes c
        JOIN movimientos_fiado m ON m.cliente_id = c.id
    """
    parametros = []
    if buscar:
        # Busca en nombre y telefono a la vez, para que Marisol no tenga
        # que pensar en cual de los dos esta buscando: escribe "juan" o
        # escribe "300" y en ambos casos encuentra.
        consulta += " WHERE c.nombre LIKE ? OR c.telefono LIKE ?"
        comodin = f"%{buscar}%"
        parametros.extend([comodin, comodin])
    # Se traen tambien los saldos negativos (saldo <> 0 en vez de > 0).
    # Un saldo negativo significa que a esa persona le abonaron mas de
    # lo que debia - normalmente porque se borro la venta que origino
    # su deuda despues de que ya habia abonado. Si se escondiera, ese
    # negativo se restaria en silencio de la proxima deuda de esa misma
    # persona y los numeros no cuadrarian sin explicacion.
    consulta += " GROUP BY c.id HAVING saldo <> 0 ORDER BY " + ORDENES_FIADOS[orden]

    con = db.get_connection()
    try:
        filas = con.execute(consulta, parametros).fetchall()
    finally:
        con.close()

    clientes = [f for f in filas if f["saldo"] > 0]
    con_saldo_a_favor = [f for f in filas if f["saldo"] < 0]

    # El total mostrado corresponde a lo que se esta viendo en la tabla:
    # si hay una busqueda activa, suma solo esos clientes (misma logica
    # que el filtro por categoria de los reportes, para que el numero de
    # arriba nunca contradiga la lista de abajo).
    total = sum(c["saldo"] for c in clientes)

    return render_template(
        "fiados.html",
        clientes=clientes,
        con_saldo_a_favor=con_saldo_a_favor,
        total_por_cobrar=total,
        buscar=buscar,
        orden=orden,
    )


@app.route("/fiados/<int:id_cliente>")
def fiado_detalle(id_cliente):
    con = db.get_connection()
    try:
        cliente = con.execute(
            "SELECT * FROM clientes WHERE id = ?", (id_cliente,)
        ).fetchone()
        movimientos = con.execute(
            """
            SELECT * FROM movimientos_fiado
            WHERE cliente_id = ?
            ORDER BY fecha DESC, fecha_creacion DESC
            """,
            (id_cliente,),
        ).fetchall()
    finally:
        con.close()

    if cliente is None:
        flash("Ese cliente no existe.", "error")
        return redirect(url_for("fiados"))

    saldo = sum(m["monto"] if m["tipo"] == "cargo" else -m["monto"] for m in movimientos)

    return render_template(
        "fiado_detalle.html", cliente=cliente, movimientos=movimientos, saldo=saldo
    )


@app.route("/fiados/abono", methods=["POST"])
def registrar_abono():
    id_cliente_texto = request.form.get("cliente_id", "")
    monto, error = parsear_monto(request.form.get("monto"))

    con = db.get_connection()
    try:
        cliente = con.execute(
            "SELECT * FROM clientes WHERE id = ?", (id_cliente_texto,)
        ).fetchone()
        if cliente is None:
            flash("Ese cliente no existe.", "error")
            return redirect(url_for("fiados"))

        saldo_actual = saldo_de_cliente(con, cliente["id"])

        if error:
            flash(error, "error")
        elif monto > saldo_actual:
            # No se permite abonar mas de lo que debe: si Marisol se
            # equivoca al escribir el numero, es mas facil corregirlo
            # aqui que terminar con un saldo negativo confuso.
            flash(
                f"Ese abono es mayor de lo que {cliente['nombre']} debe "
                f"({formato_pesos(saldo_actual)}).",
                "error",
            )
        else:
            con.execute(
                """
                INSERT INTO movimientos_fiado (cliente_id, tipo, monto, fecha)
                VALUES (?, 'abono', ?, ?)
                """,
                (cliente["id"], monto, date.today().isoformat()),
            )
            con.commit()
            nuevo_saldo = saldo_actual - monto
            if nuevo_saldo > 0:
                flash(
                    f"Abono registrado. {cliente['nombre']} ahora debe "
                    f"{formato_pesos(nuevo_saldo)}.",
                    "exito",
                )
            else:
                flash(f"Abono registrado. {cliente['nombre']} ya no debe nada.", "exito")
    finally:
        con.close()

    return redirect(url_for("fiados"))


# ---------------------------------------------------------------------
# Catalogo (lo que se vende aparte del almuerzo)
# ---------------------------------------------------------------------

def _rango_del_mes(hoy=None):
    """Primer y ultimo dia del mes de hoy, en formato de base de datos."""
    hoy = hoy or date.today()
    primero = hoy.replace(day=1)
    if hoy.month == 12:
        siguiente = hoy.replace(year=hoy.year + 1, month=1, day=1)
    else:
        siguiente = hoy.replace(month=hoy.month + 1, day=1)
    return primero.isoformat(), (siguiente - timedelta(days=1)).isoformat()


@app.route("/catalogo")
def catalogo():
    desde, hasta = _rango_del_mes()

    con = db.get_connection()
    try:
        # Se traen las ventas del mes de cada producto en una sola
        # consulta agrupada, y se pegan despues, en vez de preguntar
        # por cada producto dentro de un bucle.
        ventas = {
            fila["producto_id"]: fila
            for fila in con.execute(
                """
                SELECT producto_id,
                       COALESCE(SUM(cantidad), 0) AS unidades,
                       COALESCE(SUM(monto), 0) AS total
                FROM transacciones
                WHERE producto_id IS NOT NULL AND fecha BETWEEN ? AND ?
                GROUP BY producto_id
                """,
                (desde, hasta),
            )
        }
        filas = con.execute(
            "SELECT * FROM productos ORDER BY activo DESC, nombre"
        ).fetchall()
    finally:
        con.close()

    productos = []
    for fila in filas:
        venta = ventas.get(fila["id"])
        productos.append(
            {
                "id": fila["id"],
                "nombre": fila["nombre"],
                "precio": fila["precio"],
                "activo": fila["activo"],
                "unidades": venta["unidades"] if venta else 0,
                "total": venta["total"] if venta else 0,
            }
        )

    return render_template(
        "catalogo.html",
        productos=productos,
        vendido_mes=sum(p["total"] for p in productos),
    )


@app.route("/catalogo/agregar", methods=["POST"])
def catalogo_agregar():
    nombre = request.form.get("nombre", "").strip()
    precio, error = parsear_monto(request.form.get("precio"))

    if not nombre:
        flash("Escribe el nombre del producto.", "error")
    elif error:
        flash(error.replace("El monto", "El precio"), "error")
    else:
        con = db.get_connection()
        try:
            con.execute(
                "INSERT INTO productos (nombre, precio) VALUES (?, ?)",
                (nombre, precio),
            )
            con.commit()
        finally:
            con.close()
        flash(f"Agregamos {nombre} al catalogo, a {formato_pesos(precio)}.", "exito")
    return redirect(url_for("catalogo"))


@app.route("/catalogo/<int:id_producto>/precio", methods=["POST"])
def catalogo_precio(id_producto):
    precio, error = parsear_monto(request.form.get("precio"))
    if error:
        flash(error.replace("El monto", "El precio"), "error")
        return redirect(url_for("catalogo"))

    con = db.get_connection()
    try:
        fila = con.execute(
            "SELECT nombre FROM productos WHERE id = ?", (id_producto,)
        ).fetchone()
        # Cambiar el precio NO toca las ventas ya registradas: cada
        # venta guardo el monto que de verdad se cobro ese dia.
        con.execute(
            "UPDATE productos SET precio = ? WHERE id = ?", (precio, id_producto)
        )
        con.commit()
    finally:
        con.close()

    if fila:
        flash(f"{fila['nombre']} ahora vale {formato_pesos(precio)}.", "exito")
    return redirect(url_for("catalogo"))


@app.route("/catalogo/<int:id_producto>/alternar", methods=["POST"])
def catalogo_alternar(id_producto):
    """Saca un producto del catalogo, o lo vuelve a poner.

    No se borra para no dejar huerfanas las ventas viejas que apuntan a
    el (ver el comentario de la tabla en db.py).
    """
    con = db.get_connection()
    try:
        fila = con.execute(
            "SELECT nombre, activo FROM productos WHERE id = ?", (id_producto,)
        ).fetchone()
        if fila:
            nuevo = 0 if fila["activo"] else 1
            con.execute(
                "UPDATE productos SET activo = ? WHERE id = ?", (nuevo, id_producto)
            )
            con.commit()
    finally:
        con.close()

    if fila:
        if nuevo:
            flash(f"{fila['nombre']} vuelve a estar en el catalogo.", "exito")
        else:
            flash(f"Guardamos {fila['nombre']}. Ya no sale al vender ni en WhatsApp.", "exito")
    return redirect(url_for("catalogo"))


# ---------------------------------------------------------------------
# Empleados (la nomina)
# ---------------------------------------------------------------------

@app.route("/empleados")
def empleados():
    desde, hasta = _rango_del_mes()

    con = db.get_connection()
    try:
        pagos = {
            fila["empleado_id"]: fila
            for fila in con.execute(
                """
                SELECT empleado_id,
                       COALESCE(SUM(monto), 0) AS pagado,
                       MAX(fecha) AS ultimo
                FROM pagos_empleado
                WHERE fecha BETWEEN ? AND ?
                GROUP BY empleado_id
                """,
                (desde, hasta),
            )
        }
        filas = con.execute(
            "SELECT * FROM empleados ORDER BY activo DESC, nombre"
        ).fetchall()
    finally:
        con.close()

    lista = []
    for fila in filas:
        pago = pagos.get(fila["id"])
        lista.append(
            {
                "id": fila["id"],
                "nombre": fila["nombre"],
                "cargo": fila["cargo"],
                "pago_acordado": fila["pago_acordado"],
                "frecuencia": dict(db.FRECUENCIAS_PAGO).get(fila["frecuencia"]),
                "activo": fila["activo"],
                "pagado_mes": pago["pagado"] if pago else 0,
                "ultimo_pago": pago["ultimo"] if pago else None,
            }
        )

    return render_template(
        "empleados.html",
        empleados=lista,
        frecuencias=db.FRECUENCIAS_PAGO,
        nomina_mes=sum(e["pagado_mes"] for e in lista),
    )


@app.route("/empleados/agregar", methods=["POST"])
def empleados_agregar():
    nombre = request.form.get("nombre", "").strip()
    cargo = request.form.get("cargo", "").strip()
    frecuencia = request.form.get("frecuencia", "")
    texto_pago = request.form.get("pago_acordado", "").strip()

    pago = None
    if texto_pago:
        pago, error = parsear_monto(texto_pago)
        if error:
            flash(error.replace("El monto", "El pago acordado"), "error")
            return redirect(url_for("empleados"))

    if not nombre:
        flash("Escribe el nombre del empleado.", "error")
        return redirect(url_for("empleados"))
    if frecuencia not in dict(db.FRECUENCIAS_PAGO):
        frecuencia = None

    con = db.get_connection()
    try:
        con.execute(
            "INSERT INTO empleados (nombre, cargo, pago_acordado, frecuencia)"
            " VALUES (?, ?, ?, ?)",
            (nombre, cargo or None, pago, frecuencia),
        )
        con.commit()
    finally:
        con.close()
    flash(f"Agregamos a {nombre}.", "exito")
    return redirect(url_for("empleados"))


@app.route("/empleados/<int:id_empleado>/pagar", methods=["POST"])
def empleados_pagar(id_empleado):
    """Registra un pago a un empleado.

    El pago se guarda en DOS lugares a la vez y a proposito: como gasto
    del negocio (para que el balance, los reportes y la caja cuenten esa
    plata que salio) y como pago de la nomina (para saber a quien se le
    pago). El gasto es el que manda: el pago solo apunta a el.
    """
    monto, error = parsear_monto(request.form.get("monto"))
    fecha, error_fecha = parsear_fecha(request.form.get("fecha"))
    nota = request.form.get("nota", "").strip()

    if error or error_fecha:
        flash(error or error_fecha, "error")
        return redirect(url_for("empleados"))

    con = db.get_connection()
    try:
        empleado = con.execute(
            "SELECT nombre FROM empleados WHERE id = ?", (id_empleado,)
        ).fetchone()
        if empleado is None:
            flash("Ese empleado no existe.", "error")
            return redirect(url_for("empleados"))

        cursor = con.execute(
            """
            INSERT INTO transacciones
                (fecha, tipo, categoria, descripcion, monto, medio_pago)
            VALUES (?, 'gasto', 'empleados', ?, ?, 'efectivo')
            """,
            (fecha, f"Pago a {empleado['nombre']}" + (f" - {nota}" if nota else ""), monto),
        )
        con.execute(
            """
            INSERT INTO pagos_empleado (empleado_id, monto, fecha, nota, transaccion_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (id_empleado, monto, fecha, nota or None, cursor.lastrowid),
        )
        con.commit()
    finally:
        con.close()

    flash(
        f"Le pagamos {formato_pesos(monto)} a {empleado['nombre']}. "
        "Quedo anotado tambien como gasto.",
        "exito",
    )
    return redirect(url_for("empleados"))


@app.route("/empleados/<int:id_empleado>/alternar", methods=["POST"])
def empleados_alternar(id_empleado):
    """Marca que alguien ya no trabaja aqui (o que volvio).

    No se borra para no perder el historial de lo que se le pago.
    """
    con = db.get_connection()
    try:
        fila = con.execute(
            "SELECT nombre, activo FROM empleados WHERE id = ?", (id_empleado,)
        ).fetchone()
        if fila:
            nuevo = 0 if fila["activo"] else 1
            con.execute(
                "UPDATE empleados SET activo = ? WHERE id = ?", (nuevo, id_empleado)
            )
            con.commit()
    finally:
        con.close()

    if fila:
        if nuevo:
            flash(f"{fila['nombre']} vuelve a estar activo.", "exito")
        else:
            flash(f"{fila['nombre']} queda como que ya no trabaja aqui.", "exito")
    return redirect(url_for("empleados"))


if __name__ == "__main__":
    app.run(debug=True)

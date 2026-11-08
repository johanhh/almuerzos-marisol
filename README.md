# Almuerzos Marisol

App de escritorio (web local) para llevar las cuentas del negocio de
almuerzos de Marisol: registrar ventas y gastos, guardar el menú del
día, ver el historial de movimientos y reportes simples de balance.

Construida en Python con Flask y SQLite, pensada para que la use
alguien que no es programador ni ha usado un software de este tipo
antes.

## Qué hace

- **Registrar venta**: almuerzo del menú del día, a la carta, o cobro
  de domicilio.
- **Registrar gasto**: insumos/comida, arriendo, servicios, cubiertos y
  empaques, pago a domiciliario, otros.
- **Menú del día**: se arma plato por plato dentro de grupos fijos
  (Sopa, Principio, Carne, Acompañamiento, Bebida, Postre, Otro), se le
  pone el precio del almuerzo del día y una nota opcional. Se pueden
  poner varias carnes para que el cliente escoja, marcar que algo "se
  acabó" a mitad del día, copiar el menú de otro día con un clic, y
  consultar los menús anteriores.
- **Mensaje de WhatsApp**: se arma solo desde el menú y el catálogo. No
  es una lista pelada: es un mensaje completo con saludo (que cambia
  según la hora del día), el menú del día, el precio, los productos y
  una invitación a pedir — listo para enviar sin escribir nada. Mientras
  no exista el bot, esto es lo que hace que mandar el menú sea un clic.
- **Historial**: todos los movimientos, con filtro por tipo (venta o
  gasto) y por rango de fechas, y opción de borrar un registro si se
  escribió mal (con confirmación antes de borrar).
- **Reportes**: totales por categoría y balance (ventas menos gastos)
  del mes, con selector de mes.
- **Inicio**: resumen de hoy y de los últimos 7 días, el menú del día
  actual, y los últimos movimientos registrados.
- **Convenios**: empresas que compran almuerzos con bonos pagados por
  adelantado. Se entrega un taco de bonos (que la app imprime), se
  anota cuántos van volviendo, y se ve cuántos quedan sin usar.
- **Reportes con filtro por categoría**: además del mes, se puede
  escoger una sola categoría (ej. "Arriendo") y tanto las tarjetas de
  totales como la tabla de abajo quedan limitadas a esa categoría.
- **Enviar el menú por WhatsApp** (botón "Enviar por WhatsApp" en la
  pantalla de menú del día): abre WhatsApp con el texto del menú ya
  escrito, y Marisol escoge a quién mandarlo (un contacto, un grupo o
  su estado). **Esto NO es el bot de WhatsApp Business** descrito en el
  documento del proyecto — es un enlace público de "click to chat"
  (`api.whatsapp.com/send?text=...`), el mismo mecanismo que un botón
  de "compartir" de cualquier página web. No requiere cuenta de
  WhatsApp Business, ni verificación, ni tokens, y no conversa con
  nadie ni recibe pedidos. El bot real con la API oficial de Meta sigue
  siendo una fase futura separada (ver "Próximos pasos").
- **Quién debe (fiados)**: al registrar una venta, se puede marcar que
  el cliente no pagó completo. La venta completa cuenta como venta de
  hoy desde ya (no se espera a que paguen para contarla), y la parte
  que falta por cobrar queda anotada a nombre de un cliente (nombre y
  teléfono opcional), que acumula su deuda total aunque sea de días
  distintos. En la sección "Quién debe" se ve cuánto debe cada cliente
  y se registran los abonos (pagos) que vaya haciendo — un abono nunca
  se vuelve a contar como venta nueva, porque la venta ya se contó
  completa el día en que se hizo.

## Cómo funciona el menú del día

El menú dejó de ser un solo cuadro de texto y pasó a guardarse plato
por plato. Esto se hizo pensando en el bot de WhatsApp de la fase
siguiente, y queda documentado aquí porque es la decisión de
estructura más importante de esta parte:

- Cada plato es una fila en la tabla `menu_items`, con su **grupo**
  (Sopa, Principio, Carne, Acompañamiento, Bebida, Postre, Otro), su
  nombre, y si está disponible o ya se acabó.
- **Por qué grupos fijos y no etiquetas libres**: el bot necesita saber
  *qué* está escogiendo el cliente ("de las carnes, ¿cuál quiere?")
  para poder tomar un pedido. Con etiquetas distintas cada día, el bot
  solo podría repetir el texto sin entenderlo. El grupo "Otro" queda
  como válvula de escape para lo que no encaje.
- El **precio del almuerzo del día** vive en `menu_dia.precio` y se
  puede cambiar cualquier día (el precio varía). Así el bot podrá
  responder "¿cuánto vale?" sin molestar a Marisol.
- **El mensaje de WhatsApp se genera** desde esos mismos datos
  (`texto_del_menu` en `app.py`), no se escribe aparte. Así el menú
  nunca se escribe dos veces ni queda diciendo dos cosas distintas, y
  lo que ya se acabó no se le ofrece al cliente.
- **Para que armar el menú no sea lento** (Marisol lo hace cada mañana
  mientras atiende): hay botón de "copiar el menú anterior", los
  platos que ya usó antes se autocompletan, y marcar algo como agotado
  es un clic, sin reescribir nada.
- **Compatibilidad con lo anterior**: la columna `menu_dia.texto`, que
  antes era el menú completo, ahora es la "nota del día". Los menús
  viejos no se perdieron: siguen guardados y se muestran aparte en la
  pantalla del menú. La columna `precio` se agrega sola con
  `_agregar_columna_si_falta` (en `db.py`), así que una base de datos
  que ya venía en uso se actualiza sin que nadie tenga que borrarla ni
  correr migraciones a mano.
- **Cuidado al modificar**: `menu_dia.texto` quedó declarada `NOT NULL`
  desde la primera versión, así que la nota se guarda como texto vacío
  y nunca como `NULL`. Guardar `NULL` ahí tumbaba la app al guardar
  solo el precio sin escribir nota.

## Catálogo y empleados (nómina)

Dos secciones que se agregaron después, ambas con la misma idea de
fondo: **una sola fuente de verdad**, para que nada quede contado dos
veces ni se desincronice.

**Catálogo** (`productos`): lo que se vende aparte del almuerzo
(postres, tinto, empanadas), cada uno con su precio.

- Al registrar una venta, el producto se escoge del mismo desplegable
  de siempre (en un grupo aparte) y la app calcula `precio × cantidad`.
  El monto **queda editable**: manda lo que de verdad se cobró, porque
  a veces se rebaja. Por eso la venta guarda el monto real y, aparte,
  `producto_id` y `cantidad` para poder decir "vendiste 23 empanadas".
- Cambiar el precio **no altera las ventas ya registradas**: cada una
  guardó lo que se cobró ese día.
- Los productos no se borran, se desactivan: borrarlos dejaría ventas
  viejas apuntando a algo que ya no existe.
- El catálogo sale en el mensaje de WhatsApp junto con el menú.

**Empleados** (`empleados`, `pagos_empleado`): quién trabaja en el
negocio y cuánto se le ha pagado.

- Registrar un pago crea **al mismo tiempo** un gasto (categoría
  "Sueldos y empleados") y el registro de nómina, y el pago apunta al
  gasto con `transaccion_id`. Así el balance, los reportes y la caja
  cuentan esa plata una sola vez. Es el mismo patrón que usan los
  cargos de fiado con su venta.
- Si se borra ese gasto del historial, el pago de nómina se va con él
  (`ON DELETE CASCADE`): si no, la nómina diría que se pagó una plata
  que ya no salió de ninguna parte.
- El "pago acordado" de cada empleado es solo una referencia que
  rellena el formulario; cada pago puede ser por otro monto.
- Los empleados tampoco se borran, se marcan como que ya no trabajan,
  para no perder el historial de lo que se les pagó.

**Sobre la navegación**: con estas dos, la barra lateral llegó a nueve
secciones, más de las 6-7 que recomendaba la guía de diseño original.
En vez de esconder algunas en un submenú (que la guía prohíbe), se
partió en dos grupos visibles, "Menú" y "El negocio". Todo sigue a un
solo clic.

## Convenios con empresas (bonos de almuerzo)

Una empresa compra almuerzos para sus empleados con bonos de papel. El
negocio le entrega un taco de bonos ("vale por un almuerzo del día") a
comienzo de mes, la empresa los reparte, y cada vez que un empleado
pide, el domiciliario recoge el bono. Los bonos recogidos son la prueba
física de cuántos almuerzos se consumieron.

**La decisión importante es cuándo se cuenta la plata**, y aquí la
empresa paga por adelantado:

- **Entregar el taco sí cobra.** Entregar 140 bonos a $16.000 registra
  una venta de $2.240.000 ese día, con categoría "Bonos de convenio".
  La entrega apunta a esa venta con `transaccion_id`, igual que los
  pagos de nómina apuntan a su gasto.
- **Consumir los bonos NO cobra.** Cuando el domiciliario trae 6 bonos,
  esos 6 almuerzos solo descuentan del saldo. No crean ninguna
  transacción: esa plata ya entró cuando se vendió el taco. Si
  sumaran, se estaría contando la misma plata dos veces y las ventas
  del mes quedarían infladas.
- **Por eso el inicio avisa aparte** cuántos almuerzos de convenio se
  entregaron hoy. Un día con 20 almuerzos de convenio y nada más
  mostraría "$0 en ventas", lo cual es contablemente correcto pero
  confuso: esos almuerzos sí se cocinaron.
- Si se borra del historial la venta del taco, la entrega de bonos se
  va con ella (`ON DELETE CASCADE`).
- Si se anotan más bonos consumidos de los que quedaban, la app **avisa
  pero igual lo guarda**: puede pasar de verdad (un bono viejo, o falta
  registrar una entrega), y es mejor que Marisol se entere en el
  momento y no cuando los números no cuadren a fin de mes.

**Los bonos se imprimen desde la app** (`bonos_imprimir.html`): una hoja
con dos bonos por fila, en blanco y negro, con líneas punteadas para
recortar. Esa plantilla **no usa el estilo del resto de la app** a
propósito — va al papel, no a la pantalla — y trae sus propias reglas
`@media print`.

Los números impresos en cada bono (N 001, N 002...) **no se guardan en
la base de datos**: como el control se lleva contando cuántos bonos
vuelven y no cuál bono, guardarlos uno por uno sería cargar la base con
datos que nadie consulta. El número sirve para el control físico entre
el negocio y la empresa.

## Capital inicial y plata en caja

Los reportes por mes responden "¿cómo me fue este mes?" (ventas menos
gastos de un período). Pero Marisol ya tenía plata en el negocio antes
de usar la app, y sin tenerla en cuenta un gasto grande se vería como
una pérdida que no es. Por eso, arriba de los reportes, hay una sección
aparte que responde otra pregunta: "¿cuánta plata hay en caja ahora?".

- **Capital inicial**: la plata con la que arrancó, escrita una sola
  vez. Vive en la tabla `capital_inicial`, que tiene **una sola fila**
  (forzada con `CHECK (id = 1)`): es un punto de partida, no un
  movimiento que se acumule. Corregirlo no toca ninguna venta ni gasto.
  Se permite cero (arrancar sin nada), no negativo.
- **La cuenta** (`caja_total` en `app.py`), mostrada paso a paso en
  pantalla para que se pueda confiar en el número:

  ```
  en caja = capital inicial + todo lo vendido − todo lo gastado − lo que te deben
  ```

- **Por qué se resta lo que te deben**: una venta fiada se cuenta
  completa como vendida el día que se hace, pero esa plata todavía no
  entró. Sin restarla, la caja mostraría plata que Marisol no tiene en
  la mano. Cuando el cliente abona, lo que debe baja y la caja sube
  sola, sin registrar una venta nueva. También se muestra "si te pagan
  lo que te deben" para ver las dos cosas.
- **Limitación conocida**: el número solo es exacto si toda la plata
  que entra y sale se registra en la app. Si se saca efectivo para algo
  personal sin anotarlo como gasto, la caja se va a ver más llena de lo
  que está. Es un tema de uso, no de programación, y conviene
  explicárselo a Marisol al entregarle la app.

## Modo claro y modo oscuro

Hay un botón en la barra de arriba para cambiar entre los dos.

- Todo el modo oscuro es **un solo bloque de variables CSS**
  (`:root[data-tema="oscuro"]`). Ni una sola regla del resto de la hoja
  de estilos cambia: por eso valió la pena declarar los colores una
  sola vez arriba.
- Los colores de **texto** sobre fondos de color (`--verde-texto` y
  compañía) están declarados aparte de los de **fondo**
  (`--verde-800`), porque en modo oscuro tienen que ir en direcciones
  contrarias: el texto se aclara mientras el fondo del botón se
  mantiene oscuro. Si fueran la misma variable, arreglar uno
  estropearía el otro.
- La elección se guarda en el navegador y **se aplica antes de pintar
  la página** (un script pequeño en el `<head>` de `base.html`). Si se
  aplicara al final, la pantalla daría un flashazo blanco antes de
  ponerse oscura, que es justo lo que el modo oscuro trata de evitar.
- Si nunca se ha escogido nada, se respeta cómo esté configurado el
  computador.

## Cómo funciona "Quién debe" (fiados)

Esto se agregó después de la primera versión, a pedido explícito, así
que queda documentado aparte con más detalle:

- Al registrar una venta, aparece la pregunta "¿Pagó completo?". Si se
  responde que no, se piden el nombre del cliente, su teléfono
  (opcional, solo se guarda si el cliente es nuevo) y cuánto pagó en
  ese momento (puede ser 0 si lo fio todo).
- La venta se guarda por su valor completo (por ejemplo $20.000) y
  cuenta como venta de hoy de inmediato. Lo que falta por cobrar (en
  este ejemplo, si pagó $10.000, faltan $10.000) se guarda como una
  deuda ("cargo") a nombre de ese cliente.
- El cliente se identifica por el nombre escrito (sin distinguir
  mayúsculas ni espacios de más). Si dos clientes distintos tuvieran
  exactamente el mismo nombre, sus deudas se mezclarían — limitación
  simple y aceptada, ya que el negocio no maneja un documento de
  identidad de sus clientes.
- Al escribir el monto, la app muestra la resta en vivo:
  `$ 16.000 − $ 5.000 = queda debiendo $ 11.000`. El campo pide **lo
  que el cliente entregó**, no lo que queda debiendo — la resta la hace
  la app. La cuenta real se hace siempre en el servidor al guardar; la
  resta en pantalla es solo para que no haya duda de cuál número va en
  cuál campo.
- En "Quién debe" se ve el total que le deben a Marisol y la lista de
  clientes con saldo pendiente (los que ya pagaron todo desaparecen de
  la lista). Se puede **buscar por nombre o teléfono** y **ordenar**
  por nombre, teléfono o cuánto debe (haciendo clic en el encabezado de
  la columna, como en Excel). Cuando hay una búsqueda activa, el total
  de arriba corresponde solo a lo que se está viendo.
- Desde el detalle de cada cliente se registra un abono; no se permite
  abonar más de lo que esa persona debe.
- Si se borra (desde el Historial) la venta que originó una deuda, esa
  deuda se borra automáticamente con ella — para no dejar una deuda
  "fantasma" sin ninguna venta real detrás. Los abonos ya registrados
  no se borran, porque son plata que el cliente sí entregó.
- **Saldo a favor**: por lo anterior, un cliente puede quedar con saldo
  negativo (si le borran una venta que ya había abonado). Ese caso
  **no se esconde**: aparece en su propia sección al final de "Quién
  debe", y al borrar la venta sale un aviso explicando lo que pasó. Es
  importante que sea visible — mientras estuvo escondido, ese saldo
  negativo se restaba en silencio de la siguiente deuda de esa misma
  persona y los números no cuadraban sin explicación aparente.
- El dashboard muestra el total por cobrar como una tarjeta más, con un
  enlace a la sección completa cuando hay algo pendiente.

## Cómo instalarla y correrla

Pensado para alguien sin experiencia programando. Se necesita tener
[Python](https://www.python.org/downloads/) instalado (versión 3.10 o
más nueva; al instalarlo en Windows, marcar la casilla "Add Python to
PATH").

1. Abrir una terminal (en Windows, buscar "PowerShell" en el menú de
   inicio) y entrar a la carpeta del proyecto:

   ```
   cd ruta\a\almuerzos-marisol
   ```

2. Crear el entorno virtual (solo la primera vez):

   ```
   py -m venv venv
   ```

3. Instalar las dependencias (solo la primera vez, o cuando cambie
   `requirements.txt`):

   ```
   venv\Scripts\pip.exe install -r requirements.txt
   ```

4. Correr la app:

   ```
   venv\Scripts\python.exe app.py
   ```

5. Abrir el navegador en **http://localhost:5000**

La primera vez que se corre, la app crea sola el archivo de base de
datos (`almuerzos_marisol.db`) con las tablas que necesita — no hay que
instalar ni configurar ninguna base de datos aparte.

Para volver a usar la app otro día, solo hace falta repetir el paso 4
(no hay que recrear el entorno virtual ni reinstalar nada, a menos que
se mueva la carpeta a otro computador).

## Estructura del proyecto

```
almuerzos-marisol/
├── app.py                  # Rutas de Flask: dashboard, ventas, gastos,
│                            # historial, menu del dia, reportes
├── db.py                   # Conexion a SQLite, creacion de tablas,
│                            # listas de categorias y medios de pago
├── requirements.txt        # Dependencias (solo Flask)
├── almuerzos_marisol.db    # Base de datos (se crea sola al arrancar)
├── static/
│   ├── css/
│   │   └── estilo.css      # Todo el diseno visual (ver seccion abajo)
│   └── js/
│       └── app.js          # Interactividad (menu movil, animaciones)
└── templates/
    ├── base.html            # Marco de la app: barra lateral, barra
    │                         # superior, avisos, iconos y mensajes
    ├── dashboard.html        # Inicio
    ├── movimiento_form.html  # Formulario compartido venta/gasto
    ├── historial.html
    ├── menu.html
    ├── reportes.html
    ├── fiados.html          # Quien debe (listado)
    └── fiado_detalle.html   # Quien debe (detalle + registrar abono)
```

## El diseno visual

La interfaz es un panel de escritorio: barra lateral fija con las 7
secciones, barra superior con buscador y avisos, y el contenido en
tarjetas redondeadas sobre un fondo suave.

Puntos importantes para la revision:

- **Todo el aspecto vive en un solo archivo** (`static/css/estilo.css`),
  organizado por secciones numeradas. Los colores estan declarados una
  sola vez como variables CSS en `:root`: para cambiar el verde de la
  marca por otro color se cambia ahi arriba y cambia toda la app, sin
  buscar el color pegado en 40 lugares.
- **Sin frameworks ni librerias** (nada de Bootstrap, Tailwind, React).
  Es CSS y JavaScript propios, sin dependencias que descargar: la app
  arranca igual de rapido en un computador modesto y **funciona sin
  internet**, que es como va a correr en el negocio.
- **Sin fuentes externas**: se usa la fuente del sistema (Segoe UI en
  Windows). Cargar una fuente de Google Drive o similar significaria
  depender de la conexion para que la app se vea bien.
- **Los iconos son SVG dibujados una sola vez** al principio de
  `base.html` y reutilizados con `<use>`, en vez de repetir el mismo
  dibujo en cada plantilla.
- **El JavaScript es opcional**: si fallara, la app sigue sirviendo
  completa (los formularios se envian, los enlaces navegan, los datos
  se ven). `app.js` solo agrega comodidades: el menu lateral en
  celular, las animaciones, la resta a la vista del fiado y la
  confirmacion antes de borrar. Ningun dato depende de el.
- **Las graficas son HTML y CSS, con datos reales** calculados en
  `app.py` (`serie_por_dia`). No hay una libreria de graficas ni datos
  de ejemplo: las barras de ventas por dia y las barras por categoria
  salen de lo que hay en la base de datos, y los dias sin ventas se
  muestran con rayas en vez de dejar un hueco.
- **Nada de adornos falsos**: el buscador de la barra de arriba busca
  de verdad en el historial, y la campana muestra avisos reales
  (falta el menu de hoy, hay gente debiendo). No se puso un perfil de
  usuario inventado porque no hay login.
- **En celular** la barra lateral se convierte en un cajon que se abre
  con el boton de las tres rayas, las tarjetas se acomodan de a dos, y
  las tablas se pueden desplazar de lado en vez de encogerse hasta ser
  ilegibles.
- **Se respetan las reglas de accesibilidad de la guia original**:
  texto de 16px para arriba, los numeros de dinero son lo mas grande de
  cada pantalla, los botones tienen alto suficiente para tocarlos con
  el dedo (44-50px), el color nunca es la unica senal (siempre hay
  texto o icono al lado), y quien tenga activado "reducir movimiento"
  en su sistema no ve las animaciones.

Sobre la paleta: la guia original (`3-guia-diseno-visual.md`) proponia
un naranja calido como color de marca. A pedido de Johan se paso a un
verde profundo, siguiendo una referencia de diseno concreta. Se
conservaron el resto de decisiones de esa guia: rojo terracota para los
gastos, ambar para el fiado, fondos con un punto de calidez (nunca gris
frio ni blanco puro) y texto en un cafe muy oscuro en vez de negro.

## Decisiones de diseño y por qué se tomaron

Esta sección es para la revisión de estructura y seguridad.

- **Flask** en vez de otro framework: es el más simple de entender para
  alguien aprendiendo Python — no esconde el flujo de la petición
  (request → ruta → respuesta).
- **SQLite sin ORM**: se usa `sqlite3` (incluido con Python) en vez de
  SQLAlchemy o similares, para que el SQL de cada consulta quede
  explícito en `app.py` y `db.py`, en vez de escondido detrás de
  objetos. SQLite es un solo archivo, sin servidor que instalar, y
  sobra para el volumen de este negocio.
- **Categorías y medios de pago fijos en el código** (`db.py`), no en
  una tabla administrable: el negocio no necesita todavía agregar o
  quitar categorías desde la interfaz. Si eso cambia, es una migración
  sencilla a futuro (ver "Próximos pasos").
- **Sin sistema de login**: limitación de seguridad conocida y aceptada
  para esta fase. La app corre solo en el computador del negocio, con
  una sola persona usándola, sin acceso desde fuera de la red local.
  Cuando el proyecto crezca (más de un usuario, o acceso remoto), esto
  debe resolverse antes de exponer la app a una red no confiable.
- **Clave secreta de Flask fija en el código** (`app.secret_key` en
  `app.py`): solo se usa para firmar los mensajes flash (las
  confirmaciones de pantalla), no protege datos sensibles ni sesiones
  de usuario, porque no hay login. Si en el futuro se agrega login,
  esta clave debe pasar a una variable de entorno y no quedar en el
  código fuente.
- **`debug=True` en `app.run()`**: útil durante el desarrollo (recarga
  sola al guardar cambios, muestra errores detallados). Antes de dejar
  la app corriendo de forma más permanente en el computador del
  negocio, esto debería cambiarse a `debug=False`, ya que el modo debug
  expone un depurador interactivo que no debe estar accesible si la
  app llegara a exponerse fuera de ese computador.
- **Borrar un movimiento** solo se puede hacer por `POST`, nunca por un
  simple link, para que no se borre un registro sin querer (por
  ejemplo, si algo precarga la página). Además, el botón "Borrar"
  pide confirmación en el navegador antes de enviar la petición.
- **Validación de montos**: un monto vacío, no numérico, negativo o
  igual a cero se rechaza con un mensaje en español y sin tecnicismos,
  y además la base de datos tiene un `CHECK (monto > 0)` como segunda
  barrera, para que ni un error de programación futuro pueda guardar
  un monto inválido.
- **Cómo se leen los montos escritos a mano** (`_leer_numero_de_pesos`
  en `app.py`): en Colombia los miles se escriben con punto
  (`16.000`), a veces con coma (`16,000`), y es común escribir el signo
  de pesos. Como el negocio no maneja centavos, esos separadores se
  ignoran y todo se lee como pesos enteros: `16.000`, `16,000`,
  `$ 16.000` y `16000` significan lo mismo. Esto **no es cosmético**:
  la primera versión usaba `float(texto.replace(",", "."))`, y ahí
  `float("16.000")` daba **16 pesos** en vez de 16.000 — un error serio
  que aparecía justo al hacer las restas del fiado.
- **Consultas SQL parametrizadas** (`?` en vez de armar el texto SQL
  con los valores pegados): evita inyección SQL. Esto aplica incluso a
  los filtros del historial, que arman la consulta de forma dinámica
  según qué filtros use Marisol, pero siempre pasando los valores como
  parámetros, nunca concatenados al texto de la consulta.

## Suposiciones tomadas (decisiones pequeñas no cubiertas en los documentos originales)

Quedan anotadas aquí porque no estaban definidas ni en el documento del
proyecto ni en el de pasos, y se resolvieron de la forma más simple
posible:

- **Medios de pago**: se definieron como Efectivo, Transferencia y
  Otro.
- **"La semana" en el dashboard**: se calcula como los últimos 7 días
  incluyendo hoy (no el lunes a domingo del calendario), porque es más
  fácil de interpretar de un vistazo sin pensar en calendarios.
- **Edición simultánea del menú del día**: si dos personas lo editaran
  al mismo tiempo, gana la última que guarde (no hay bloqueo ni aviso
  de conflicto). Con una sola persona usando la app hoy, esto es
  suficiente.
- **Confirmación antes de borrar**: se agregó un cuadro de
  confirmación del navegador ("¿Borrar este registro? No se puede
  deshacer.") antes de enviar el borrado, aunque no estaba pedido
  explícitamente, como protección adicional contra un clic accidental.

## Próximos pasos (fuera del alcance de esta fase, intencionalmente no construidos)

- **Bot de WhatsApp** (API oficial de Meta Cloud API) que lea el menú
  del día desde la tabla `menu_dia` y notifique a Marisol los pedidos.
- **Integración con una máquina de recibos/POS**, una vez se decida
  cuál se compra y si expone alguna forma de conectarse.
- **Sistema de login**, necesario si más de una persona usa la app o si
  se accede desde fuera de la red local.
- **Categorías administrables** desde la interfaz, en vez de fijas en
  el código.
- **Gráficas en los reportes** (barras o líneas), siguiendo la misma
  paleta de colores, si se necesita ver tendencias en vez de solo
  totales.
- **Facturación electrónica certificada ante la DIAN**: pendiente de
  resolver con un contador según el régimen tributario de Marisol; no
  es un problema de software y no bloquea el uso de esta app.

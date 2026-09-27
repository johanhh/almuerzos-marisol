/* ===================================================================
   Almuerzos Marisol - interactividad
   ===================================================================

   JavaScript sencillo, sin librerias ni frameworks: son pocas cosas y
   asi la app no depende de descargar nada de internet para funcionar.

   Todo lo que hay aqui es "adorno util": si el JavaScript fallara, la
   app sigue sirviendo igual (los formularios se envian, los enlaces
   navegan, los datos se ven). Nada importante depende de este archivo.
   =================================================================== */

(function () {
  "use strict";

  /* ---------------------------------------------------------------
     Modo claro / oscuro.

     El tema ya viene puesto en <html> por el script que corre en el
     <head> antes de pintar. Aqui solo se maneja el boton que lo
     cambia y se guarda la eleccion en el navegador, para que la app
     abra manana como la dejo hoy.
     --------------------------------------------------------------- */
  // Ojo: se busca "data-cambiar-tema" y NO "data-tema". El <html> lleva
  // "data-tema" con el tema actual, asi que buscar ese nombre devolvia
  // el <html> en vez del boton, y el clic terminaba puesto sobre toda
  // la pagina: el tema cambiaba al tocar cualquier parte.
  var botonTema = document.querySelector("[data-cambiar-tema]");

  if (botonTema) {
    botonTema.addEventListener("click", function () {
      var actual = document.documentElement.getAttribute("data-tema");
      var nuevo = actual === "oscuro" ? "claro" : "oscuro";
      document.documentElement.setAttribute("data-tema", nuevo);
      try {
        localStorage.setItem("tema", nuevo);
      } catch (e) {
        // Si el navegador no deja guardar (modo privado, permisos),
        // el cambio igual funciona hasta que se cierre la pagina.
      }
    });
  }

  /* ---------------------------------------------------------------
     Menu lateral en celular: se abre y se cierra como un cajon.
     --------------------------------------------------------------- */
  var botonMenu = document.querySelector("[data-abrir-menu]");
  var sidebar = document.querySelector("[data-sidebar]");
  var velo = document.querySelector("[data-velo]");

  function cerrarMenu() {
    if (!sidebar) return;
    sidebar.classList.remove("sidebar--abierto");
    if (velo) velo.hidden = true;
    if (botonMenu) botonMenu.setAttribute("aria-expanded", "false");
  }

  if (botonMenu && sidebar) {
    botonMenu.addEventListener("click", function () {
      var abierto = sidebar.classList.toggle("sidebar--abierto");
      if (velo) velo.hidden = !abierto;
      botonMenu.setAttribute("aria-expanded", abierto ? "true" : "false");
    });
  }

  if (velo) velo.addEventListener("click", cerrarMenu);

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") {
      cerrarMenu();
      cerrarAvisos();
    }
  });

  /* ---------------------------------------------------------------
     Campana de avisos.
     --------------------------------------------------------------- */
  var botonAvisos = document.querySelector("[data-abrir-avisos]");
  var panelAvisos = document.querySelector("[data-avisos]");

  function cerrarAvisos() {
    if (panelAvisos) panelAvisos.hidden = true;
    if (botonAvisos) botonAvisos.setAttribute("aria-expanded", "false");
  }

  if (botonAvisos && panelAvisos) {
    botonAvisos.addEventListener("click", function (evento) {
      evento.stopPropagation();
      panelAvisos.hidden = !panelAvisos.hidden;
      botonAvisos.setAttribute("aria-expanded", panelAvisos.hidden ? "false" : "true");
    });

    document.addEventListener("click", function (evento) {
      if (!panelAvisos.hidden && !panelAvisos.contains(evento.target)) {
        cerrarAvisos();
      }
    });
  }

  /* ---------------------------------------------------------------
     Mensajes de confirmacion: se pueden cerrar, y los de exito se
     van solos a los 6 segundos. Los de error NO se van solos: si
     algo salio mal, Marisol tiene que alcanzar a leerlo.
     --------------------------------------------------------------- */
  document.querySelectorAll("[data-cerrar-mensaje]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      var mensaje = boton.closest(".mensaje");
      if (mensaje) mensaje.remove();
    });
  });

  document.querySelectorAll(".mensaje--exito").forEach(function (mensaje) {
    setTimeout(function () {
      mensaje.style.transition = "opacity 400ms, transform 400ms";
      mensaje.style.opacity = "0";
      mensaje.style.transform = "translateY(-8px)";
      setTimeout(function () {
        mensaje.remove();
      }, 400);
    }, 6000);
  });

  /* ---------------------------------------------------------------
     Numeros que cuentan hacia arriba al cargar la pagina.
     Es solo un efecto: el numero final ya viene escrito en el HTML,
     asi que si esto no corre, el numero correcto se ve igual.
     --------------------------------------------------------------- */
  var prefiereQuieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function animarNumero(elemento) {
    var destino = parseFloat(elemento.getAttribute("data-contar"));
    if (isNaN(destino) || destino === 0) return;
    var textoFinal = elemento.textContent;
    var negativo = destino < 0;
    var objetivo = Math.abs(destino);
    var duracion = 850;
    var inicio = null;

    function paso(tiempo) {
      if (inicio === null) inicio = tiempo;
      var avance = Math.min((tiempo - inicio) / duracion, 1);
      // Desaceleracion suave al final.
      var suave = 1 - Math.pow(1 - avance, 3);
      var valor = Math.round(objetivo * suave);
      elemento.textContent =
        (negativo ? "-" : "") + "$ " + valor.toLocaleString("es-CO");
      if (avance < 1) {
        requestAnimationFrame(paso);
      } else {
        elemento.textContent = textoFinal;
      }
    }
    requestAnimationFrame(paso);
  }

  if (!prefiereQuieto) {
    document.querySelectorAll("[data-contar]").forEach(animarNumero);
  }

  /* ---------------------------------------------------------------
     Formulario de venta: mostrar/ocultar el detalle del fiado y
     hacer la resta a la vista mientras se escribe.
     --------------------------------------------------------------- */
  var opcionPagoSi = document.getElementById("pago-si");
  var opcionPagoNo = document.getElementById("pago-no");
  var cajaFiado = document.getElementById("detalle-fiado");
  var campoMonto = document.getElementById("monto");
  var campoDio = document.getElementById("monto_pagado_ahora");
  var salidaResta = document.getElementById("resta-fiado");

  function leerPesos(texto) {
    // Mismas reglas que el servidor: los puntos y comas son separadores
    // de miles, no decimales ("16.000" son dieciseis mil pesos).
    var limpio = (texto || "").replace(/[$\s.,]/g, "");
    if (!limpio) return 0;
    var numero = parseInt(limpio, 10);
    return isNaN(numero) ? 0 : numero;
  }

  function enPesos(numero) {
    return "$ " + numero.toLocaleString("es-CO");
  }

  function actualizarResta() {
    if (!salidaResta || !campoMonto || !campoDio) return;
    var total = leerPesos(campoMonto.value);
    var dio = leerPesos(campoDio.value);
    var texto = salidaResta.querySelector("[data-resta-texto]");
    if (!texto) return;

    salidaResta.classList.remove("resta--alerta", "resta--neutro");

    if (total <= 0) {
      salidaResta.classList.add("resta--neutro");
      texto.textContent = "Escribe arriba cuanto valia en total, y aqui te muestro la cuenta.";
      return;
    }
    if (dio > total) {
      salidaResta.classList.add("resta--alerta");
      texto.textContent =
        "Te dio mas de lo que vale la venta (" + enPesos(total) + "). Revisa el numero.";
      return;
    }
    texto.textContent =
      enPesos(total) + "  −  " + enPesos(dio) + "  =  queda debiendo " + enPesos(total - dio);
  }

  function mostrarFiado(mostrar) {
    if (!cajaFiado) return;
    cajaFiado.hidden = !mostrar;
    if (mostrar) actualizarResta();
  }

  if (opcionPagoSi) opcionPagoSi.addEventListener("change", function () { mostrarFiado(false); });
  if (opcionPagoNo) opcionPagoNo.addEventListener("change", function () { mostrarFiado(true); });
  if (campoMonto) campoMonto.addEventListener("input", actualizarResta);
  if (campoDio) campoDio.addEventListener("input", actualizarResta);
  actualizarResta();

  /* ---------------------------------------------------------------
     Venta del catalogo: al escoger un producto aparece "cuantos" y el
     monto se calcula solo (precio x cantidad).

     El monto queda editable a proposito: a veces se rebaja o se cobra
     distinto, y lo que manda es lo que de verdad se cobro. Si este
     JavaScript no corriera, el campo del monto sigue ahi para
     escribirlo a mano.
     --------------------------------------------------------------- */
  var campoCategoria = document.getElementById("categoria");
  var campoCantidad = document.getElementById("cantidad");
  var cajaCantidad = document.getElementById("campo-cantidad");

  function opcionEscogida() {
    if (!campoCategoria) return null;
    return campoCategoria.options[campoCategoria.selectedIndex];
  }

  function precioDelProducto() {
    var opcion = opcionEscogida();
    if (!opcion) return 0;
    var precio = parseInt(opcion.getAttribute("data-precio"), 10);
    return isNaN(precio) ? 0 : precio;
  }

  function recalcularProducto() {
    if (!campoCategoria || !cajaCantidad || !campoMonto) return;
    var precio = precioDelProducto();
    var esProducto = precio > 0;

    cajaCantidad.hidden = !esProducto;
    if (!esProducto) return;

    var cuantos = parseInt((campoCantidad.value || "1").replace(/\D/g, ""), 10);
    if (isNaN(cuantos) || cuantos < 1) cuantos = 1;
    campoMonto.value = enPesos(precio * cuantos).replace("$ ", "");
    actualizarResta();
  }

  if (campoCategoria && cajaCantidad) {
    campoCategoria.addEventListener("change", recalcularProducto);
    if (campoCantidad) campoCantidad.addEventListener("input", recalcularProducto);
    // Al volver de un error, el producto puede venir ya escogido.
    if (precioDelProducto() > 0) cajaCantidad.hidden = false;
  }

  /* ---------------------------------------------------------------
     Confirmacion antes de borrar algo (no se puede deshacer).
     --------------------------------------------------------------- */
  document.querySelectorAll("[data-confirmar]").forEach(function (formulario) {
    formulario.addEventListener("submit", function (evento) {
      if (!window.confirm(formulario.getAttribute("data-confirmar"))) {
        evento.preventDefault();
      }
    });
  });
})();

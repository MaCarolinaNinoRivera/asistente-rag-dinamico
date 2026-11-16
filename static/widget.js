(function () {
  const script = document.currentScript;
  const proyecto = (script && script.dataset.proyecto) || "agro";

  const config = {
    api: (script && script.dataset.api) || "/api/v1", // Funciona en local y en Azure sin tocar nada
    proyecto: proyecto,
    pantalla: (script && script.dataset.pantalla) || "general",
    logo: (script && script.dataset.logo) || "",
    avatar: (script && script.dataset.avatar) || "",
    emoji: (script && script.dataset.emoji) || "💬", // Emoji configurable (🌱, 🩺, 💼, etc.)
    empresa: (script && script.dataset.empresa) || "Asistente Virtual",
    asistente: (script && script.dataset.asistente) || "Asistente",
    descripcion:
      (script && script.dataset.descripcion) ||
      "Haz tus consultas aquí. Responde a cualquier hora.",
    token: null,
  };

  const ICONOS = {
    chat: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2zm3 5h10V7H7v2zm0 4h7v-2H7v2z"/></svg>',
    cerrar:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.4 5 12 10.6 17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6 10.6 12 5 6.4z"/></svg>',
    volver:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15.4 5 17 6.6 11.6 12l5.4 5.4-1.6 1.6-7-7z"/></svg>',
    enviar:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 20.5 21.5 12 3 3.5v6.6L15 12 3 13.9z"/></svg>',
  };

  // ID separado por proyecto para que no se crucen sesiones al probar varios en el navegador
  function usuarioDePrueba() {
    const storageKey = `asistente_usuario_id_${config.proyecto}`;
    let id = localStorage.getItem(storageKey);
    if (!id) {
      id = "usr_" + Math.random().toString(36).substring(2, 11);
      localStorage.setItem(storageKey, id);
    }
    return id;
  }

  function cabeceras() {
    const h = {
      "Content-Type": "application/json",
      accept: "application/json",
    };
    if (config.token) h.Authorization = `Bearer ${config.token}`;
    return h;
  }

  function quien() {
    return config.token ? {} : { usuario_id: usuarioDePrueba() };
  }

  // ---------- Estructura ----------
  const contenedor = document.createElement("div");
  contenedor.innerHTML = `
        <div id="agro-widget-container">
            <button id="agro-chat-btn" type="button" aria-label="Abrir el asistente" aria-expanded="false">${ICONOS.chat}</button>
            <div id="agro-chat-window" role="dialog" aria-modal="false">
                <section id="agro-vista-inicio" class="agro-vista">
                    <div class="agro-portada">
                        <div class="agro-portada-arriba">
                            <img id="agro-logo" alt="" />
                            <button type="button" class="agro-icono agro-cerrar" aria-label="Cerrar">${ICONOS.cerrar}</button>
                        </div>
                        <p class="agro-saludo">¡Hola! 👋 Te damos la bienvenida a <span id="agro-empresa"></span></p>
                        <p class="agro-subtitulo">Estamos aquí para apoyarte</p>
                    </div>
                    <div class="agro-tarjeta">
                        <p class="agro-tarjeta-titulo">Comenzar una conversación</p>
                        <p class="agro-tarjeta-texto" id="agro-descripcion-texto"></p>
                        <button type="button" id="agro-empezar" class="agro-boton">${ICONOS.enviar}<span>Escríbenos un mensaje</span></button>
                    </div>
                </section>
                <section id="agro-vista-chat" class="agro-vista" hidden>
                    <div id="agro-chat-header">
                        <button type="button" class="agro-icono" id="agro-volver" aria-label="Volver al inicio">${ICONOS.volver}</button>
                        <div class="agro-avatar" id="agro-avatar-encabezado" aria-hidden="true"></div>
                        <div class="agro-encabezado-textos">
                            <h4 id="agro-nombre-2"></h4>
                            <span class="agro-estado">En línea · responde en segundos</span>
                        </div>
                        <button type="button" class="agro-icono agro-cerrar" aria-label="Cerrar">${ICONOS.cerrar}</button>
                    </div>
                    <div id="agro-chat-messages" aria-live="polite"></div>
                    <div id="agro-chat-input-area">
                        <input type="text" id="agro-chat-input" maxlength="2000" placeholder="Escribe tu pregunta…" aria-label="Tu pregunta" />
                        <button id="agro-chat-send" type="button" aria-label="Enviar">${ICONOS.enviar}</button>
                    </div>
                </section>
            </div>
        </div>`;
  document.body.appendChild(contenedor);

  // Textos e íconos configurables
  document.getElementById("agro-empresa").textContent = config.empresa;
  document.getElementById("agro-nombre-2").textContent = config.asistente;
  document.getElementById("agro-descripcion-texto").textContent =
    config.descripcion;

  const encabezado = document.getElementById("agro-avatar-encabezado");
  encabezado.textContent = config.emoji;

  const logo = document.getElementById("agro-logo");
  if (config.logo) {
    logo.src = config.logo;
    logo.alt = config.empresa;
  } else {
    logo.remove();
  }
  if (config.avatar) {
    encabezado.textContent = "";
    encabezado.appendChild(crearAvatar());
  }

  const chatBtn = document.getElementById("agro-chat-btn");
  const chatWindow = document.getElementById("agro-chat-window");
  chatWindow.setAttribute("aria-label", config.asistente);
  const vistaInicio = document.getElementById("agro-vista-inicio");
  const vistaChat = document.getElementById("agro-vista-chat");
  const sendBtn = document.getElementById("agro-chat-send");
  const inputField = document.getElementById("agro-chat-input");
  const mensajes = document.getElementById("agro-chat-messages");
  let enviando = false;

  function mostrar(vista) {
    vistaInicio.hidden = vista !== "inicio";
    vistaChat.hidden = vista !== "chat";
    if (vista === "chat") {
      inputField.focus();
      mensajes.scrollTop = mensajes.scrollHeight;
    }
  }
  function abrirVentana(abrir) {
    chatWindow.classList.toggle("abierta", abrir);
    chatBtn.setAttribute("aria-expanded", String(abrir));
    chatBtn.setAttribute(
      "aria-label",
      abrir ? "Cerrar el asistente" : "Abrir el asistente",
    );
    if (abrir)
      mostrar(mensajes.querySelector(".agro-message.user") ? "chat" : "inicio");
  }

  chatBtn.addEventListener("click", () =>
    abrirVentana(!chatWindow.classList.contains("abierta")),
  );
  contenedor
    .querySelectorAll(".agro-cerrar")
    .forEach((b) => b.addEventListener("click", () => abrirVentana(false)));
  document
    .getElementById("agro-empezar")
    .addEventListener("click", () => mostrar("chat"));
  document
    .getElementById("agro-volver")
    .addEventListener("click", () => mostrar("inicio"));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && chatWindow.classList.contains("abierta"))
      abrirVentana(false);
  });
  sendBtn.addEventListener("click", enviarMensaje);
  inputField.addEventListener("keydown", (e) => {
    if (e.key === "Enter") enviarMensaje();
  });

  agregarMensaje(
    `¡Hola! Soy tu ${config.asistente}. ¿En qué te puedo ayudar hoy?`,
    "assistant",
  );

  function escribirTexto(elemento, texto) {
    elemento.textContent = "";
    String(texto)
      .split("\n")
      .forEach((linea, i) => {
        if (i) elemento.appendChild(document.createElement("br"));
        elemento.appendChild(document.createTextNode(linea));
      });
  }

  function crearAvatar() {
    if (config.avatar) {
      const img = document.createElement("img");
      img.className = "agro-avatar-img";
      img.src = config.avatar;
      img.alt = "";
      return img;
    }
    const circulo = document.createElement("div");
    circulo.className = "agro-avatar-img agro-avatar-vacio";
    circulo.textContent = config.emoji; // Usa el emoji configurado
    return circulo;
  }

  function hora() {
    return new Date().toLocaleTimeString("es-CO", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  function crearFila(burbuja, deAsistente, conMeta = true) {
    const fila = document.createElement("div");
    fila.className = `agro-fila ${deAsistente ? "asistente" : "usuario"}`;
    const columna = document.createElement("div");
    columna.className = "agro-columna";
    columna.appendChild(burbuja);
    if (conMeta) {
      const meta = document.createElement("span");
      meta.className = "agro-meta";
      meta.textContent = deAsistente
        ? `${config.asistente} · ${hora()}`
        : hora();
      columna.appendChild(meta);
    }
    if (deAsistente) fila.appendChild(crearAvatar());
    fila.appendChild(columna);
    return fila;
  }

  function agregarMensaje(texto, quien, mensajeId) {
    const div = document.createElement("div");
    div.className = `agro-message ${quien}`;
    const cuerpo = document.createElement("div");
    escribirTexto(cuerpo, texto);
    div.appendChild(cuerpo);
    if (quien === "assistant" && mensajeId)
      div.appendChild(crearCalificacion(mensajeId));
    const fila = crearFila(div, quien.startsWith("assistant"));
    mensajes.appendChild(fila);
    mensajes.scrollTop = mensajes.scrollHeight;
    return fila;
  }

  function crearCalificacion(mensajeId) {
    const caja = document.createElement("div");
    caja.className = "agro-feedback";
    const etiqueta = document.createElement("span");
    etiqueta.textContent = "¿Te sirvió?";
    caja.appendChild(etiqueta);
    [
      ["👍", 5, "Sí me sirvió"],
      ["👎", 1, "No me sirvió"],
    ].forEach(([icono, valor, etiquetaAccesible]) => {
      const boton = document.createElement("button");
      boton.type = "button";
      boton.textContent = icono;
      boton.setAttribute("aria-label", etiquetaAccesible);
      boton.addEventListener("click", () => calificar(valor, caja, mensajeId));
      caja.appendChild(boton);
    });
    return caja;
  }

  function agregarEscribiendo() {
    const div = document.createElement("div");
    div.className = "agro-message assistant agro-escribiendo";
    div.setAttribute("aria-label", "El asistente está escribiendo");
    for (let i = 0; i < 3; i++) div.appendChild(document.createElement("span"));
    const fila = crearFila(div, true, false);
    mensajes.appendChild(fila);
    mensajes.scrollTop = mensajes.scrollHeight;
    return fila;
  }

  async function enviarMensaje() {
    const pregunta = inputField.value.trim();
    if (!pregunta || enviando) return;
    enviando = true;
    sendBtn.disabled = true;
    inputField.value = "";
    agregarMensaje(pregunta, "user");
    const pensando = agregarEscribiendo();

    try {
      const respuesta = await fetch(`${config.api}/chat`, {
        method: "POST",
        headers: cabeceras(),
        body: JSON.stringify({
          ...quien(),
          proyecto_codigo: config.proyecto,
          pantalla_codigo: config.pantalla,
          pregunta,
        }),
      });
      const datos = await respuesta.json().catch(() => ({}));
      pensando.remove();
      if (!respuesta.ok) {
        agregarMensaje(
          datos.detail ||
            "No pude responder en este momento. Intenta de nuevo en un minuto.",
          "assistant",
        );
      } else {
        agregarMensaje(
          datos.respuesta || "No recibí respuesta. Intenta de nuevo.",
          "assistant",
          datos.mensaje_id,
        );
      }
    } catch (error) {
      pensando.remove();
      agregarMensaje(
        "No me pude conectar. Revisa tu conexión e intenta de nuevo.",
        "assistant",
      );
    } finally {
      enviando = false;
      sendBtn.disabled = false;
      inputField.focus();
    }
  }

  async function calificar(puntuacion, caja, mensajeId) {
    caja.querySelectorAll("button").forEach((b) => {
      b.disabled = true;
    });
    try {
      const respuesta = await fetch(`${config.api}/chat/calificar`, {
        method: "POST",
        headers: cabeceras(),
        body: JSON.stringify({
          ...quien(),
          mensaje_id: mensajeId,
          proyecto_codigo: config.proyecto,
          calificacion: puntuacion,
        }),
      });
      caja.textContent = respuesta.ok
        ? "¡Gracias por tu opinión!"
        : "No se pudo guardar la calificación.";
      caja.classList.add(respuesta.ok ? "ok" : "error");
    } catch (error) {
      caja.textContent = "Error de conexión.";
      caja.classList.add("error");
    }
  }

  window.AsistenteAgro = {
    setPantalla(codigo) {
      if (codigo) config.pantalla = String(codigo);
    },
    setToken(token) {
      config.token = token || null;
    },
    abrir() {
      abrirVentana(true);
    },
    cerrar() {
      abrirVentana(false);
    },
  };
})();

(function () {
  function resolveTheme(theme) {
    if (theme === "light" || theme === "dark") return theme;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function injectStyles() {
    if (document.getElementById("ansari-widget-styles")) return;
    var link = document.createElement("link");
    link.id = "ansari-widget-styles";
    link.rel = "stylesheet";
    var base = document.currentScript ? document.currentScript.src : window.location.href;
    link.href = new URL("widget.css", base).toString();
    document.head.appendChild(link);
  }

  function addMessage(container, role, text) {
    var bubble = document.createElement("div");
    bubble.className = "ansari-widget-message " + role;
    bubble.textContent = text;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
  }

  function createWidget(options) {
    var root = document.createElement("div");
    root.className = "ansari-widget";
    root.setAttribute("data-theme", resolveTheme(options.theme));

    var panel = document.createElement("div");
    panel.className = "ansari-widget-panel";

    var header = document.createElement("div");
    header.className = "ansari-widget-header";
    header.textContent = "ANSARI";

    var messages = document.createElement("div");
    messages.className = "ansari-widget-messages";
    addMessage(messages, "assistant", options.greeting || "Hi! How can I help?");

    var form = document.createElement("form");
    form.className = "ansari-widget-form";

    var input = document.createElement("input");
    input.className = "ansari-widget-input";
    input.type = "text";
    input.placeholder = "Ask a question…";

    var send = document.createElement("button");
    send.className = "ansari-widget-send";
    send.type = "submit";
    send.textContent = "Send";

    form.appendChild(input);
    form.appendChild(send);

    panel.appendChild(header);
    panel.appendChild(messages);
    panel.appendChild(form);

    var button = document.createElement("button");
    button.className = "ansari-widget-button";
    button.type = "button";
    button.setAttribute("aria-label", "Open ANSARI support chat");
    button.textContent = "?";
    button.addEventListener("click", function () {
      panel.classList.toggle("open");
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var text = input.value.trim();
      if (!text) return;
      addMessage(messages, "user", text);
      input.value = "";
      // /api/v1/chat lands in M2 — placeholder reply until then.
      addMessage(messages, "assistant", "Chat isn't wired up yet — coming in M2/M3.");
    });

    root.appendChild(panel);
    root.appendChild(button);
    document.body.appendChild(root);
  }

  window.ANSARI = {
    init: function (options) {
      options = options || {};
      injectStyles();
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
          createWidget(options);
        });
      } else {
        createWidget(options);
      }
    },
  };
})();

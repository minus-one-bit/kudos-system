(() => {
  "use strict";

  const csrfToken =
    document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";

  async function api(path, options = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      options.headers || {}
    );
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers,
    });

    let body = null;
    try {
      body = await response.json();
    } catch (error) {
      // Non-JSON error page; fall through with a generic message.
    }

    if (!response.ok) {
      const message =
        body?.error?.message || `Request failed (${response.status})`;
      const failure = new Error(message);
      failure.status = response.status;
      throw failure;
    }
    return body;
  }

  function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  }

  // Build nodes with textContent: user-generated text is never parsed as HTML.
  function buildKudosCard(item) {
    const article = document.createElement("article");
    article.className = "kudos-card";

    const meta = document.createElement("p");
    meta.className = "kudos-meta";

    const sender = document.createElement("strong");
    sender.textContent = item.sender.display_name;

    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = "→";

    const recipient = document.createElement("strong");
    recipient.textContent = item.recipient.display_name;

    const time = document.createElement("time");
    time.dateTime = item.created_at;
    time.textContent = formatTime(item.created_at);

    meta.append(sender, document.createTextNode(" "), arrow,
      document.createTextNode(" "), recipient, time);

    const message = document.createElement("p");
    message.className = "kudos-message";
    message.textContent = item.message;

    article.append(meta, message);
    return article;
  }

  // ------------------------------------------------------------- composer

  const form = document.getElementById("kudos-form");
  if (form) {
    const textarea = document.getElementById("message");
    const counter = document.getElementById("char-counter");
    const status = document.getElementById("form-status");
    const feed = document.getElementById("feed");
    const emptyState = document.getElementById("empty-state");
    const maxLength = Number(textarea.getAttribute("maxlength")) || 500;

    const updateCounter = () => {
      counter.textContent = `${textarea.value.length} / ${maxLength}`;
    };
    textarea.addEventListener("input", updateCounter);
    updateCounter();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      status.textContent = "";
      status.classList.remove("error", "success");

      const recipientId = Number(form.elements.recipient_id.value);
      const message = textarea.value.trim();

      if (!recipientId) {
        status.textContent = "Choose a colleague first.";
        status.classList.add("error");
        return;
      }
      if (!message) {
        status.textContent = "Write a short message first.";
        status.classList.add("error");
        return;
      }

      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      button.textContent = "Sending…";

      try {
        const created = await api("/api/kudos", {
          method: "POST",
          body: JSON.stringify({ recipient_id: recipientId, message }),
        });
        feed.prepend(buildKudosCard(created));
        if (emptyState) emptyState.remove();
        form.reset();
        updateCounter();
        status.textContent = "Kudos sent.";
        status.classList.add("success");
      } catch (error) {
        if (error.status === 401) {
          window.location.href = "/login";
          return;
        }
        status.textContent = error.message;
        status.classList.add("error");
      } finally {
        button.disabled = false;
        button.textContent = "Send kudos";
      }
    });

    // ------------------------------------------------------------ load more

    const loadMore = document.getElementById("load-more");
    if (loadMore) {
      const limit = Number(feed.dataset.limit) || 20;

      loadMore.addEventListener("click", async () => {
        loadMore.disabled = true;
        // Count what is currently rendered so newly prepended kudos are skipped.
        const offset = feed.querySelectorAll(".kudos-card").length;
        try {
          const data = await api(`/api/kudos?limit=${limit}&offset=${offset}`);
          const items = data.items || [];
          items.forEach((item) => feed.append(buildKudosCard(item)));
          if (offset + items.length >= (data.total || 0)) {
            loadMore.hidden = true;
          }
        } catch (error) {
          if (error.status === 401) {
            window.location.href = "/login";
            return;
          }
          status.textContent = error.message;
          status.classList.add("error");
        } finally {
          loadMore.disabled = false;
        }
      });
    }
  }

  // ------------------------------------------------------------ moderation

  document.querySelectorAll("[data-moderation-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const kudosId = button.getAttribute("data-kudos-id");
      const action = button.getAttribute("data-moderation-action");
      if (!kudosId || !action) return;

      let reason = "";
      if (action === "hide" || action === "delete") {
        reason =
          window.prompt(
            "Reason for moderation (required, at least 3 characters):"
          ) || "";
        if (!reason.trim()) return;
      }

      button.disabled = true;
      try {
        if (action === "delete") {
          await api(`/api/admin/kudos/${kudosId}`, {
            method: "DELETE",
            body: JSON.stringify({ reason }),
          });
        } else {
          await api(`/api/admin/kudos/${kudosId}/${action}`, {
            method: "POST",
            body: JSON.stringify({ reason }),
          });
        }
        window.location.reload();
      } catch (error) {
        if (error.status === 401) {
          window.location.href = "/login";
          return;
        }
        window.alert(error.message);
        button.disabled = false;
      }
    });
  });
})();

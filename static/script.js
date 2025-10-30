(function () {
  const pageSize = parseInt(document.body.dataset.pageSize || "5", 10);
  let offset = parseInt(document.body.dataset.initialOffset || "0", 10);
  let currentSource = localStorage.getItem("source_filter") || "";

  const $ = (sel) => document.querySelector(sel);
  const list = $("#list");
  const loadMoreBtn = $("#loadMoreBtn");
  const refreshBtn = $("#refreshBtn");
  const statusEl = $("#status");
  const sourceSel = $("#sourceFilter"); // NEW

  function renderItem(it) {
    const imgHtml = it.image_url
      ? `<div><img src="${it.image_url}" alt="" style="max-width:100%;border-radius:8px;margin-bottom:0.5rem;"></div>`
      : "";
    const dateHtml = it.published_date
      ? `<div style="font-size:0.9rem;color:#666;margin-bottom:0.4rem;">${it.published_date}</div>`
      : (it.published_at ? `<div style="font-size:0.9rem;color:#666;margin-bottom:0.4rem;">${it.published_at}</div>` : "");
    const takeHtml =
      it.takeaways && it.takeaways.length
        ? `<ul class="takeaways">${it.takeaways.map((t) => `<li>${t}</li>`).join("")}</ul>`
        : "";
    return `<div class="card">
      ${imgHtml}
      <div class="title"><a href="${it.url}" target="_blank">${it.title}</a></div>
      ${dateHtml}
      <p>${it.summary}</p>
      ${takeHtml}
    </div>`;
  }

  async function loadMore() {
    loadMoreBtn.disabled = true;
    try {
      const qs = new URLSearchParams({ offset: String(offset), limit: String(pageSize) });
      if (currentSource) qs.set("source", currentSource);
      const res = await fetch(`/home?${qs.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const arr = await res.json();
      for (const it of arr) list.insertAdjacentHTML("beforeend", renderItem(it));
      offset += arr.length;
      if (arr.length === pageSize) {
        loadMoreBtn.disabled = false;
      } else {
        loadMoreBtn.textContent = "No more";
      }
    } catch (e) {
      loadMoreBtn.disabled = false;
      alert("Load failed");
    }
  }

  function clearAndLoadFirstPage() {
    list.innerHTML = "";
    offset = 0;
    loadMoreBtn.textContent = "Load more";
    loadMoreBtn.disabled = false;
    loadMore(); // fetch first page with currentSource
  }

  async function loadSources() {
    try {
      const res = await fetch("/sources");
      const data = await res.json();
      const opts = data.sources || [];
      for (const s of opts) {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s;
        sourceSel.appendChild(opt);
      }
      if (currentSource) {
        sourceSel.value = currentSource;
        clearAndLoadFirstPage(); // refresh list to match selection
      }
    } catch {}
  }

    if (sourceSel) {
    sourceSel.addEventListener("change", () => {
      currentSource = sourceSel.value;
      localStorage.setItem("source_filter", currentSource);   // persist
      clearAndLoadFirstPage();
    });
    loadSources();
  }

  function getToken() {
    let token = localStorage.getItem("refresh_token");
    if (!token) {
      token = prompt("Enter refresh token (only once):");
      if (token) localStorage.setItem("refresh_token", token);
    }
    return token;
  }

  async function doRefresh() {
    refreshBtn.disabled = true;
    statusEl.textContent = "Refreshing…";
    try {
      const headers = { "Content-Type": "application/json" };
      const token = getToken();
      if (token) headers["Authorization"] = "Bearer " + token;

      const res = await fetch("/refresh", {
        method: "POST",
        headers,
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "refresh failed");
      statusEl.textContent = `Done. ${data.stats.summarized} summarized, ${data.stats.cached} cached.`;
      // After refresh, rebuild the list for current filter
      clearAndLoadFirstPage();
    } catch (e) {
      statusEl.textContent = "Error: " + e.message;
      refreshBtn.disabled = false;
    }
  }

  // wire events
  if (loadMoreBtn) loadMoreBtn.addEventListener("click", loadMore);
  if (refreshBtn) refreshBtn.addEventListener("click", doRefresh);
  if (sourceSel) {
    sourceSel.addEventListener("change", () => {
      currentSource = sourceSel.value;
      clearAndLoadFirstPage();
    });
    loadSources();
  }
})();

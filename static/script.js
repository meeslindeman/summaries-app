(function () {
  // Theme toggle functionality
  const themeToggle = document.getElementById('themeToggle');
  const html = document.documentElement;
  
  // Check for saved theme preference or default to light mode
  const currentTheme = localStorage.getItem('theme') || 'light';
  html.setAttribute('data-theme', currentTheme);
  
  themeToggle.addEventListener('click', () => {
    const theme = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  });

  // Existing article loading functionality
  const pageSize = parseInt(document.body.dataset.pageSize || "5", 10);
  let offset = parseInt(document.body.dataset.initialOffset || "0", 10);
  let currentSource = localStorage.getItem("source_filter") || "";
  let sourcesLoaded = false; // guard against double /sources calls

  const $ = (sel) => document.querySelector(sel);
  const list = $("#list");
  const loadMoreBtn = $("#loadMoreBtn");
  const refreshBtn = $("#refreshBtn");
  const sourceSel = $("#sourceFilter");

  function renderItem(it) {
    const imgHtml = it.image_url
      ? `<img src="${it.image_url}" alt="">`
      : "";
    const dateHtml = it.published_date
      ? `<div class="date">${it.published_date}</div>`
      : (it.published_at ? `<div class="date">${it.published_at}</div>` : "");
    const takeHtml =
      it.takeaways && it.takeaways.length
        ? `<ul class="takeaways">${it.takeaways.map((t) => `<li>${t}</li>`).join("")}</ul>`
        : "";
    return `<div class="card">
      ${imgHtml}
      <h2 class="title"><a href="${it.url}" target="_blank">${it.title}</a></h2>
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
    loadMore();
  }

  async function loadSources() {
    if (sourcesLoaded || !sourceSel) return; // prevent double fetch/bind
    sourcesLoaded = true;
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
        clearAndLoadFirstPage();
      }
    } catch {
      // ignore
    }
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
      // Silent refresh; rebuild the list for current filter
      clearAndLoadFirstPage();
    } catch (e) {
      alert("Refresh failed: " + e.message);
      refreshBtn.disabled = false;
    }
  }

  // wire events
  if (loadMoreBtn) loadMoreBtn.addEventListener("click", loadMore);
  if (refreshBtn) refreshBtn.addEventListener("click", doRefresh);
  if (sourceSel) {
    sourceSel.addEventListener("change", () => {
      currentSource = sourceSel.value;
      localStorage.setItem("source_filter", currentSource);
      clearAndLoadFirstPage();
    });
    loadSources();
  }
})();
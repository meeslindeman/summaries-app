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
    
    return `<div class="card">
      ${imgHtml}
      <h2 class="title"><a href="${it.url}" target="_blank">${it.title}</a></h2>
      ${dateHtml}
      <p>${it.summary}</p>
      <div class="save-article">
        <svg viewBox="0 0 24 24" class="heart-icon">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
        <span>Save article</span>
      </div>
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
  if (!sourceSel) return;
  try {
    const res = await fetch("/sources");
    const data = await res.json();
    const opts = data.sources || [];

    // If no cached sources yet: hide the control and clear any stored selection
    if (!opts.length) {
      const wrap = document.getElementById("sourceWrap");
      if (wrap) wrap.style.display = "none";
      currentSource = "";
      localStorage.removeItem("source_filter");
      return;
    }

    // Repopulate options
    for (const s of opts) {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      sourceSel.appendChild(opt);
    }

    // If stored selection isn't available anymore, reset it
    if (currentSource && !opts.includes(currentSource)) {
      currentSource = "";
      localStorage.removeItem("source_filter");
    }

    // Apply current selection and reload if set
    if (currentSource) {
      sourceSel.value = currentSource;
      clearAndLoadFirstPage();
    }
  } catch {
    // swallow
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
      const token = localStorage.getItem("refresh_token");
      if (token) headers["Authorization"] = "Bearer " + token;

      const res = await fetch("/refresh", {
        method: "POST",
        headers,
        body: JSON.stringify({}),
      });

      if (res.status === 401) {
        // token changed/invalid — clear and prompt once
        localStorage.removeItem("refresh_token");
        const newTok = prompt("Enter refresh token:");
        if (newTok) {
          localStorage.setItem("refresh_token", newTok);
          return doRefresh(); // retry immediately with the new token
        }
        refreshBtn.disabled = false;
        return;
      }

      if (res.status === 429) {
        alert("Please wait a bit before refreshing again.");
        refreshBtn.disabled = false;
        return;
      }

      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "refresh failed");

      // Success: silently reload the first page
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
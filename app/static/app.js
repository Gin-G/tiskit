(() => {
  const form = document.getElementById('upload-form');
  const fileInput = document.getElementById('file');
  const btn = document.getElementById('submit-btn');
  const statusEl = document.getElementById('status');
  const resultEl = document.getElementById('result');
  const summaryEl = document.getElementById('summary');
  const tbody = document.querySelector('#fields-table tbody');

  function setStatus(msg, isError) {
    statusEl.textContent = msg || '';
    statusEl.classList.toggle('error', !!isError);
  }

  function renderSummary(r) {
    summaryEl.innerHTML = '';
    const rows = [
      ['Pages', r.page_count],
      ['Form (AcroForm)', r.has_acroform ? 'yes' : 'no'],
      ['Fields detected', r.field_count],
    ];
    for (const [k, v] of rows) {
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd'); dd.textContent = v;
      summaryEl.append(dt, dd);
    }
  }

  function renderFields(fields) {
    tbody.innerHTML = '';
    if (!fields.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 4;
      td.textContent = 'No AcroForm fields detected. This template likely needs coordinate-based filling.';
      td.style.color = 'var(--muted)';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    for (const f of fields) {
      const tr = document.createElement('tr');
      for (const v of [f.name, f.type, f.page == null ? '–' : f.page + 1, f.max_length ?? '–']) {
        const td = document.createElement('td');
        td.textContent = String(v);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    if (!file) return;
    btn.disabled = true;
    setStatus('Uploading and analyzing…');
    resultEl.hidden = true;

    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/templates/analyze', {
        method: 'POST',
        body: fd,
        credentials: 'same-origin',
        cache: 'no-store',
      });
      if (!res.ok) {
        const text = await res.text();
        let detail = text;
        try { detail = JSON.parse(text).detail || text; } catch (_) {}
        throw new Error(detail || (`HTTP ${res.status}`));
      }
      const data = await res.json();
      renderSummary(data);
      renderFields(data.fields || []);
      resultEl.hidden = false;
      setStatus('Done.');
    } catch (err) {
      setStatus(err.message || 'Upload failed.', true);
    } finally {
      btn.disabled = false;
      // Reset the input so the file reference is dropped from the DOM.
      fileInput.value = '';
    }
  });
})();

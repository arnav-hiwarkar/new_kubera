/* =====================================================================
   audit-mapping.js — Ledger Mapping page logic (Hierarchical)
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Ledger Mapping';
  const PAGE_URL = '/audit/mapping.html';

  let engagementId = null;
  let engagement = null;
  let treeData = []; // Hierarchical groups tree
  let ledgers = [];
  
  // Filter state for right panel
  let filterState = 'unmapped'; // 'unmapped', 'all', 'mapped'
  let filterGroup = null; // { level: 'group'|'subgroup'|'sub_subgroup', id: number }
  let selectedLedgerIds = new Set();
  
  // Local transient state for progressive mapping
  let transientMapping = {}; // { ledgerId: { group_id, subgroup_id, sub_subgroup_id } }

  document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    engagementId = urlParams.get('id');

    if (!engagementId) {
      alert('No engagement ID specified.');
      window.location.href = '/audit/index.html';
      return;
    }

    window.AE.initTopbar({ showBack: true, backHref: `/audit/engagement.html?id=${engagementId}` });
    window.AE.initSidebar(PAGE_KEY);
    window.AE.trackVisit(PAGE_KEY, PAGE_LABEL, `${PAGE_URL}?id=${engagementId}`);

    const subnav = document.getElementById('audit-subnav');
    if (subnav) {
      subnav.querySelectorAll('a').forEach(link => {
        const page = link.getAttribute('href').split('?')[0];
        link.setAttribute('href', `${page}?id=${engagementId}`);
      });
    }

    // Attach styling for new components
    const style = document.createElement('style');
    style.innerHTML = `
      .tree-node { cursor: pointer; padding: 4px 0; user-select: none; display: flex; justify-content: space-between; align-items: center; border-radius: 4px; }
      .tree-node summary { outline: none; flex: 1; }
      .tree-node.selected > strong, .tree-node.selected, .leaf.selected .leaf-content { 
        background: var(--bg-primary); color: var(--primary-color);
      }
      .tree-node:hover > strong, .tree-node:hover, .leaf:hover .leaf-content {
        background: var(--bg-secondary);
      }
      .tree-actions { display: none; gap: 4px; padding-right: 4px; }
      .tree-node:hover .tree-actions { display: flex; }
      .tree-btn { background: none; border: none; font-size: 11px; cursor: pointer; color: var(--text-muted); padding: 2px 4px; border-radius: 3px; }
      .tree-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
      
      .pill-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
      .map-pill { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 12px; padding: 2px 8px; font-size: 11px; cursor: pointer; color: var(--text-primary); }
      .map-pill:hover { background: var(--border-color); }
      .btn-clear-map { background: transparent; border: none; color: var(--status-action); font-size: 12px; cursor: pointer; margin-left: 4px; padding: 0 4px; }
      .btn-clear-map:hover { text-decoration: underline; }
      .mapping-select { padding: 3px 6px; font-size: 11px; border: 1px solid var(--border-color); border-radius: 4px; outline: none; }
      .sg-tooltip { position: absolute; z-index: 100; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: 6px; padding: 8px 12px; font-size: 11px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events: none; white-space: nowrap; opacity: 0; transition: opacity 0.15s; max-width: 280px; }
      .sg-tooltip.visible { opacity: 1; }
      .sg-tooltip-title { font-weight: 600; margin-bottom: 4px; color: var(--text-primary); }
      .sg-tooltip-item { color: var(--text-secondary); padding: 1px 0; }
      .sg-tooltip-empty { color: var(--text-muted); font-style: italic; }
      .tree-node[data-level="subgroup"] { position: relative; }
      .tree-node .sg-chevron { font-size: 9px; margin-right: 4px; transition: transform 0.2s; color: var(--text-muted); display: inline-block; width: 10px; }
      .tree-node .sg-badge { font-size: 9px; color: var(--text-muted); margin-left: 4px; }
    `;
    document.head.appendChild(style);

    await loadData();
  });

  async function loadData() {
    try {
      const engRes = await window.AE.apiFetch(`/api/audit/engagements/${engagementId}`);
      if (engRes.ok) engagement = await engRes.json();

      const treeRes = await window.AE.apiFetch(`/api/audit/${engagementId}/groups-tree`);
      if (treeRes.ok) treeData = await treeRes.json();

      const ledgersRes = await window.AE.apiFetch(`/api/audit/${engagementId}/trial-balance`);
      if (ledgersRes.ok) {
        const data = await ledgersRes.json();
        ledgers = data.ledgers || [];
      }

      updateProgressBar();
      renderGroupsPanel();
      renderLedgerPanel();
    } catch (e) {
      console.error(e);
      alert('Error loading mapping data.');
    }
  }

  function updateProgressBar() {
    const total = ledgers.length;
    const mapped = ledgers.filter(l => l.is_mapped).length;
    const pct = total > 0 ? Math.round((mapped / total) * 100) : 0;
    const fill = document.getElementById('mapping-progress-fill');
    const label = document.getElementById('mapping-progress-label');
    if (fill) fill.style.width = `${pct}%`;
    if (label) label.textContent = `${mapped} / ${total} mapped (${pct}%)`;
  }

  // ── Groups Panel ───────────────────────────────────────────────────
  function renderGroupsPanel() {
    const panel = document.getElementById('mapping-left');
    if (!panel) return;

    let html = `
      <div style="margin-bottom:12px;">
        <h3 style="margin:0;font-size:14px;font-weight:600;color:var(--text-primary);">Classification Hierarchy</h3>
      </div>
      <div class="tree-container" style="font-size:12px;">
    `;

    treeData.forEach(group => {
      const isGrpSelected = filterGroup?.level === 'group' && filterGroup.id === group.id;
      html += `
        <details ${isGrpSelected || filterGroup ? 'open' : ''}>
          <summary class="tree-node ${isGrpSelected ? 'selected' : ''}" data-level="group" data-id="${group.id}">
            <strong>${window.AE.escapeHtml(group.name)}</strong>
            <div class="tree-actions">
              <button class="tree-btn btn-add-sg" data-gid="${group.id}" title="Add Subgroup">➕ Subgroup</button>
            </div>
          </summary>
          <div class="tree-children" style="margin-left: 12px; border-left: 1px dashed var(--border-color); padding-left: 6px;">
      `;
      group.subgroups.forEach(subgroup => {
        const isSgSelected = filterGroup?.level === 'subgroup' && filterGroup.id === subgroup.id;
        const hasSsg = subgroup.sub_subgroups.length > 0;
        const sgLedgerCount = subgroup.ledger_count || 0;
        html += `
          <details>
            <summary class="tree-node ${isSgSelected ? 'selected' : ''}" data-level="subgroup" data-id="${subgroup.id}" data-has-ssg="${hasSsg}">
              <span><span class="sg-chevron">${hasSsg ? '▶' : ''}</span>${window.AE.escapeHtml(subgroup.name)} <span class="sg-badge">${sgLedgerCount > 0 ? '(' + sgLedgerCount + ')' : ''}</span></span>
              <div class="tree-actions">
                <button class="tree-btn btn-edit-sg" data-id="${subgroup.id}" data-name="${window.AE.escapeHtml(subgroup.name)}" title="Edit">✏️</button>
                <button class="tree-btn btn-del-sg" data-id="${subgroup.id}" data-name="${window.AE.escapeHtml(subgroup.name)}" title="Delete">🗑️</button>
                <button class="tree-btn btn-add-ssg" data-sgid="${subgroup.id}" title="Add Sub-subgroup">➕ Sub-subgroup</button>
              </div>
            </summary>
            <div class="tree-children" style="margin-left: 12px; border-left: 1px dashed var(--border-color); padding-left: 6px;">
        `;
        if (subgroup.sub_subgroups.length > 0) {
          subgroup.sub_subgroups.forEach(ssg => {
            const isSsgSelected = filterGroup?.level === 'sub_subgroup' && filterGroup.id === ssg.id;
            html += `
              <div class="tree-node leaf ${isSsgSelected ? 'selected' : ''}" data-level="sub_subgroup" data-id="${ssg.id}">
                <span class="leaf-content" style="flex:1; padding:2px 4px; border-radius:4px;">
                  ${window.AE.escapeHtml(ssg.name)} <span style="color:var(--text-muted);font-size:10px;">(${ssg.ledger_count})</span>
                </span>
                <div class="tree-actions">
                  <button class="tree-btn btn-edit-ssg" data-id="${ssg.id}" data-name="${window.AE.escapeHtml(ssg.name)}" title="Edit">✏️</button>
                  <button class="tree-btn btn-del-ssg" data-id="${ssg.id}" data-name="${window.AE.escapeHtml(ssg.name)}" title="Delete">🗑️</button>
                </div>
              </div>
            `;
          });
        } else {
          html += `<div style="font-size:10px;color:var(--text-muted);font-style:italic;padding:2px 4px;">No sub-subgroups</div>`;
        }
        html += `</div></details>`;
      });
      html += `</div></details>`;
    });

    html += `</div>`;
    panel.innerHTML = html;

    // Attach tree node click for filtering
    panel.querySelectorAll('.tree-node').forEach(node => {
      node.addEventListener('click', (e) => {
        if (e.target.closest('.tree-actions') || e.target.tagName === 'SUMMARY' && e.offsetX < 15) {
          return;
        }
        e.preventDefault();
        e.stopPropagation();

        const level = node.dataset.level;
        const id = parseInt(node.dataset.id);
        
        if (filterGroup?.level === level && filterGroup?.id === id) {
          filterGroup = null;
        } else {
          filterGroup = { level, id };
        }
        renderGroupsPanel();
        renderLedgerPanel(false);
      });
    });

    // Action button listeners
    panel.querySelectorAll('.btn-add-sg').forEach(btn => btn.addEventListener('click', (e) => {
      e.stopPropagation(); openCrudModal('subgroup', 'add', { parentId: btn.dataset.gid });
    }));
    panel.querySelectorAll('.btn-edit-sg').forEach(btn => btn.addEventListener('click', (e) => {
      e.stopPropagation(); openCrudModal('subgroup', 'edit', { id: btn.dataset.id, name: btn.dataset.name });
    }));
    panel.querySelectorAll('.btn-del-sg').forEach(btn => btn.addEventListener('click', (e) => {
      e.stopPropagation(); deleteNode('subgroup', btn.dataset.id, btn.dataset.name);
    }));

    panel.querySelectorAll('.btn-add-ssg').forEach(btn => btn.addEventListener('click', (e) => {
      e.stopPropagation(); openCrudModal('sub_subgroup', 'add', { parentId: btn.dataset.sgid });
    }));
    panel.querySelectorAll('.btn-edit-ssg').forEach(btn => btn.addEventListener('click', (e) => {
      e.stopPropagation(); openCrudModal('sub_subgroup', 'edit', { id: btn.dataset.id, name: btn.dataset.name });
    }));
    panel.querySelectorAll('.btn-del-ssg').forEach(btn => btn.addEventListener('click', (e) => {
      e.stopPropagation(); deleteNode('sub_subgroup', btn.dataset.id, btn.dataset.name);
    }));

    // Tooltip for subgroup hover
    let sgTooltip = document.getElementById('sg-hover-tooltip');
    if (!sgTooltip) {
      sgTooltip = document.createElement('div');
      sgTooltip.id = 'sg-hover-tooltip';
      sgTooltip.className = 'sg-tooltip';
      document.body.appendChild(sgTooltip);
    }

    panel.querySelectorAll('.tree-node[data-level="subgroup"]').forEach(node => {
      node.addEventListener('mouseenter', (e) => {
        const sgId = parseInt(node.dataset.id);
        let sgNode = null;
        for (const g of treeData) {
          sgNode = g.subgroups.find(sg => sg.id === sgId);
          if (sgNode) break;
        }
        if (!sgNode) return;

        let tooltipHtml = `<div class="sg-tooltip-title">${window.AE.escapeHtml(sgNode.name)}</div>`;
        if (sgNode.sub_subgroups.length > 0) {
          sgNode.sub_subgroups.forEach(ssg => {
            tooltipHtml += `<div class="sg-tooltip-item">• ${window.AE.escapeHtml(ssg.name)} (${ssg.ledger_count} ledgers)</div>`;
          });
        } else {
          tooltipHtml += `<div class="sg-tooltip-empty">No sub-subgroups defined</div>`;
        }

        sgTooltip.innerHTML = tooltipHtml;
        const rect = node.getBoundingClientRect();
        sgTooltip.style.left = (rect.right + 8) + 'px';
        sgTooltip.style.top = rect.top + 'px';
        sgTooltip.classList.add('visible');
      });

      node.addEventListener('mouseleave', () => {
        sgTooltip.classList.remove('visible');
      });
    });

    // Update chevron rotation on details toggle
    panel.querySelectorAll('details').forEach(det => {
      det.addEventListener('toggle', () => {
        const chevron = det.querySelector('.sg-chevron');
        if (chevron) {
          chevron.textContent = det.open ? '▼' : '▶';
        }
      });
    });
  }

  function openCrudModal(type, action, data) {
    let modal = document.getElementById('crud-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'crud-modal';
      modal.className = 'audit-modal';
      document.body.appendChild(modal);
    }
    
    const isSg = type === 'subgroup';
    const typeLabel = isSg ? 'Subgroup' : 'Sub-subgroup';
    const title = action === 'add' ? `Add ${typeLabel}` : `Rename ${typeLabel}`;
    
    modal.style.display = 'flex';
    modal.innerHTML = `
      <div class="audit-modal-content" style="width: 320px;">
        <h3>${title}</h3>
        <div class="form-group" style="margin-bottom:20px;">
          <label class="form-label">Name</label>
          <input type="text" class="input" id="crud-name" value="${data.name || ''}" placeholder="${typeLabel} name" required>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:12px;">
          <button type="button" class="btn btn-ghost" id="btn-crud-cancel">Cancel</button>
          <button type="button" class="btn btn-primary" id="btn-crud-save">Save</button>
        </div>
      </div>
    `;

    modal.querySelector('#btn-crud-cancel').addEventListener('click', () => modal.style.display = 'none');
    
    const input = modal.querySelector('#crud-name');
    input.focus();

    modal.querySelector('#btn-crud-save').addEventListener('click', async () => {
      const newName = input.value.trim();
      if (!newName) return alert('Name is required');

      const url = action === 'add'
        ? `/api/audit/${engagementId}/${isSg ? 'subgroups' : 'sub-subgroups'}`
        : `/api/audit/${engagementId}/${isSg ? 'subgroups' : 'sub-subgroups'}/${data.id}`;
      const method = action === 'add' ? 'POST' : 'PATCH';
      
      const bodyPayload = action === 'add'
        ? (isSg ? { group_id: data.parentId, name: newName } : { subgroup_id: data.parentId, name: newName })
        : { name: newName };

      try {
        const res = await window.AE.apiFetch(url, {
          method,
          body: JSON.stringify(bodyPayload)
        });
        if (res.ok) {
          modal.style.display = 'none';
          await loadData(); // refresh tree and ledgers
        } else {
          alert('Failed to save.');
        }
      } catch (err) {
        console.error(err);
        alert('Error saving data.');
      }
    });
  }

  async function deleteNode(type, id, name) {
    if (!confirm(`Delete ${type === 'subgroup' ? 'Subgroup' : 'Sub-subgroup'} "${name}"? Any ledgers currently mapped under it will be unmapped. This cannot be undone.`)) return;
    
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/${type === 'subgroup' ? 'subgroups' : 'sub-subgroups'}/${id}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        const data = await res.json();
        if (data.unmapped_count > 0) {
          alert(`Deleted. ${data.unmapped_count} ledger(s) were unmapped as a result.`);
        }
        if (filterGroup?.id === parseInt(id) && filterGroup?.level === type) {
           filterGroup = null;
        }
        await loadData();
      } else {
        alert('Failed to delete node.');
      }
    } catch (e) {
      console.error(e);
      alert('Error deleting node.');
    }
  }

  // ── Ledgers Panel ──────────────────────────────────────────────────
  function renderLedgerPanel(preserveScroll = true) {
    const panel = document.getElementById('mapping-right');
    if (!panel) return;

    let currentScroll = 0;
    if (preserveScroll) {
      const scrollArea = panel.querySelector('.ledger-table-scroll-area');
      if (scrollArea) currentScroll = scrollArea.scrollTop;
    }

    let filtered = ledgers;

    if (filterGroup) {
      if (filterGroup.level === 'group') {
        filtered = ledgers.filter(l => l.group_id === filterGroup.id);
      } else if (filterGroup.level === 'subgroup') {
        filtered = ledgers.filter(l => l.subgroup_id === filterGroup.id);
      } else if (filterGroup.level === 'sub_subgroup') {
        filtered = ledgers.filter(l => l.sub_subgroup_id === filterGroup.id);
      }
    } else {
      if (filterState === 'unmapped') filtered = ledgers.filter(l => !l.is_mapped);
      else if (filterState === 'mapped') filtered = ledgers.filter(l => l.is_mapped);
    }

    const unmappedCount = ledgers.filter(l => !l.is_mapped).length;
    let panelTitle = filterGroup ? 'Filtered Ledgers' : (filterState === 'unmapped' ? `Unmapped Ledgers (${unmappedCount})` : (filterState === 'mapped' ? `Mapped Ledgers (${ledgers.length - unmappedCount})` : 'All Ledgers'));

    const showBulkMapBtn = selectedLedgerIds.size > 0;

    panel.innerHTML = `
      <div style="padding: 12px 16px 0 16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:12px;">
          <h3 style="margin:0;font-size:15px;font-weight:600;color:var(--text-primary);">${panelTitle}</h3>
          <div style="display:flex;gap:8px;align-items:center;">
            <button class="btn btn-secondary btn-sm" id="btn-import-prev-mapping" style="padding:4px 8px;font-size:11px;">Import Previous Year</button>
            ${showBulkMapBtn ? `<button class="btn btn-primary btn-sm" id="btn-bulk-map">Bulk Map (${selectedLedgerIds.size})</button>` : ''}
            <div class="filter-chips">
              <span class="filter-chip ${filterState === 'unmapped' && !filterGroup ? 'active' : ''}" id="chip-unmapped">Unmapped</span>
              <span class="filter-chip ${filterState === 'all' && !filterGroup ? 'active' : ''}" id="chip-all">All</span>
              <span class="filter-chip ${filterState === 'mapped' && !filterGroup ? 'active' : ''}" id="chip-mapped">Mapped</span>
            </div>
          </div>
        </div>
      </div>

      <div class="ledger-table-scroll-area">
        <table class="audit-table" style="table-layout: fixed;">
          <thead>
            <tr>
              <th width="40" style="padding: 8px 12px;"><input type="checkbox" id="chk-select-all-ledgers" /></th>
              <th width="120" style="padding: 8px 12px;">Ledger Code</th>
              <th width="200" style="padding: 8px 12px;">Ledger Name</th>
              <th width="100" class="text-right" style="padding: 8px 12px;">Closing Balance</th>
              <th width="350" style="padding: 8px 12px;">Assign Mapping</th>
            </tr>
          </thead>
          <tbody>
            ${filtered.map(l => {
              const trans = transientMapping[l.id] || {};
              const curGId = trans.group_id || null;
              const curSgId = trans.subgroup_id || null;

              let mappingHtml = '';
              if (l.is_mapped) {
                mappingHtml = `
                  <div class="pill-row">
                    <span class="map-pill" title="Group" data-action="unmap" data-id="${l.id}">${window.AE.escapeHtml(l.group_name)}</span> >
                    <span class="map-pill" title="Subgroup" data-action="unmap" data-id="${l.id}">${window.AE.escapeHtml(l.subgroup_name)}</span>${l.sub_subgroup_name ? ` >
                    <span class="map-pill" title="Sub-subgroup" data-action="unmap" data-id="${l.id}">${window.AE.escapeHtml(l.sub_subgroup_name)}</span>` : ''}
                    <button class="btn-clear-map" data-action="unmap" data-id="${l.id}" title="Clear mapping">✕</button>
                    <span class="save-status" id="status-${l.id}" style="font-size:10px;color:var(--status-verified);opacity:0;transition:opacity 0.2s;">Saved ✓</span>
                  </div>
                `;
              } else {
                let html = `<div class="pill-row progressive-row">`;
                
                // Group selector
                if (curGId) {
                  const gNode = treeData.find(g => g.id === curGId);
                  html += `<span class="map-pill" data-action="reset-g" data-id="${l.id}">${window.AE.escapeHtml(gNode.name)}</span> > `;
                } else {
                  html += `<select class="mapping-select sel-g" data-id="${l.id}">
                    <option value="">Select Group...</option>
                    ${treeData.map(g => `<option value="${g.id}">${window.AE.escapeHtml(g.name)}</option>`).join('')}
                  </select>`;
                }

                // Subgroup selector
                if (curGId) {
                  if (curSgId) {
                    const sgNode = treeData.find(g => g.id === curGId).subgroups.find(sg => sg.id === curSgId);
                    html += `<span class="map-pill" data-action="reset-sg" data-id="${l.id}">${window.AE.escapeHtml(sgNode.name)}</span> > `;
                  } else {
                    const gNode = treeData.find(g => g.id === curGId);
                    html += `<select class="mapping-select sel-sg" data-id="${l.id}">
                      <option value="">Select Subgroup...</option>
                      ${gNode.subgroups.map(sg => `<option value="${sg.id}">${window.AE.escapeHtml(sg.name)}</option>`).join('')}
                    </select>`;
                  }
                }

                // Sub-subgroup selector — only if the selected subgroup HAS sub-subgroups
                if (curSgId) {
                  const sgNode = treeData.find(g => g.id === curGId).subgroups.find(sg => sg.id === curSgId);
                  if (sgNode.sub_subgroups.length > 0) {
                    html += `<select class="mapping-select sel-ssg" data-id="${l.id}">
                      <option value="">Select Sub-subgroup...</option>
                      ${sgNode.sub_subgroups.map(ssg => `<option value="${ssg.id}">${window.AE.escapeHtml(ssg.name)}</option>`).join('')}
                    </select>`;
                  }
                }
                
                html += `</div>`;
                mappingHtml = html;
              }

              return `
                <tr class="${l.is_mapped ? '' : 'unmapped-row'}" id="row-${l.id}">
                  <td style="padding: 6px 12px;"><input type="checkbox" class="chk-ledger" data-id="${l.id}" ${selectedLedgerIds.has(l.id) ? 'checked' : ''} /></td>
                  <td class="mono" style="padding: 6px 12px; overflow:hidden;text-overflow:ellipsis;">${window.AE.escapeHtml(l.ledger_code)}</td>
                  <td style="padding: 6px 12px; overflow:hidden;text-overflow:ellipsis;" title="${window.AE.escapeHtml(l.ledger_name)}">${window.AE.escapeHtml(l.ledger_name)}</td>
                  <td class="text-right mono" style="padding: 6px 12px;">${l.closing_balance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                  <td style="padding: 6px 12px;">${mappingHtml}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;

    // Progressive selectors events
    panel.querySelectorAll('.sel-g').forEach(sel => sel.addEventListener('change', (e) => {
      const lid = parseInt(sel.dataset.id);
      transientMapping[lid] = { group_id: parseInt(sel.value) };
      renderLedgerPanel();
    }));
    
    panel.querySelectorAll('.sel-sg').forEach(sel => sel.addEventListener('change', (e) => {
      const lid = parseInt(sel.dataset.id);
      const sgId = parseInt(sel.value);
      if(transientMapping[lid]) {
         transientMapping[lid].subgroup_id = sgId;
         // If this subgroup has no sub-subgroups, save immediately at subgroup level
         const gId = transientMapping[lid].group_id;
         const gNode = treeData.find(g => g.id === gId);
         const sgNode = gNode?.subgroups.find(sg => sg.id === sgId);
         if (sgNode && sgNode.sub_subgroups.length === 0) {
           saveMapping(lid, { subgroup_id: sgId });
           return;
         }
         renderLedgerPanel();
      }
    }));

    panel.querySelectorAll('.sel-ssg').forEach(sel => sel.addEventListener('change', (e) => {
      const lid = parseInt(sel.dataset.id);
      const ssgId = parseInt(sel.value);
      if (ssgId) saveMapping(lid, { sub_subgroup_id: ssgId });
    }));

    // Reset actions on pills
    panel.querySelectorAll('[data-action="reset-g"]').forEach(btn => btn.addEventListener('click', (e) => {
      const lid = parseInt(btn.dataset.id);
      delete transientMapping[lid];
      renderLedgerPanel();
    }));

    panel.querySelectorAll('[data-action="reset-sg"]').forEach(btn => btn.addEventListener('click', (e) => {
      const lid = parseInt(btn.dataset.id);
      if (transientMapping[lid]) delete transientMapping[lid].subgroup_id;
      renderLedgerPanel();
    }));

    panel.querySelectorAll('[data-action="unmap"]').forEach(btn => btn.addEventListener('click', (e) => {
      const lid = parseInt(btn.dataset.id);
      saveMapping(lid, {});
    }));

    // Checkboxes
    const selectAllChk = panel.querySelector('#chk-select-all-ledgers');
    if (selectAllChk) {
      selectAllChk.checked = filtered.length > 0 && filtered.every(l => selectedLedgerIds.has(l.id));
      selectAllChk.addEventListener('change', (e) => {
        filtered.forEach(l => {
          if (e.target.checked) selectedLedgerIds.add(l.id);
          else selectedLedgerIds.delete(l.id);
        });
        renderLedgerPanel();
      });
    }

    panel.querySelectorAll('.chk-ledger').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const lid = parseInt(chk.dataset.id);
        if (e.target.checked) selectedLedgerIds.add(lid);
        else selectedLedgerIds.delete(lid);
        renderLedgerPanel();
      });
    });

    // Chips
    panel.querySelector('#chip-unmapped')?.addEventListener('click', () => { filterGroup = null; filterState = 'unmapped'; renderGroupsPanel(); renderLedgerPanel(false); });
    panel.querySelector('#chip-all')?.addEventListener('click', () => { filterGroup = null; filterState = 'all'; renderGroupsPanel(); renderLedgerPanel(false); });
    panel.querySelector('#chip-mapped')?.addEventListener('click', () => { filterGroup = null; filterState = 'mapped'; renderGroupsPanel(); renderLedgerPanel(false); });

    panel.querySelector('#btn-bulk-map')?.addEventListener('click', () => openBulkMapModal());
    panel.querySelector('#btn-import-prev-mapping')?.addEventListener('click', importPreviousMapping);

    if (preserveScroll && currentScroll > 0) {
      const newScrollArea = panel.querySelector('.ledger-table-scroll-area');
      if (newScrollArea) newScrollArea.scrollTop = currentScroll;
    }
  }

  async function saveMapping(ledgerId, { sub_subgroup_id, subgroup_id } = {}) {
    try {
      const body = {};
      if (sub_subgroup_id) {
        body.sub_subgroup_id = sub_subgroup_id;
      } else if (subgroup_id) {
        body.subgroup_id = subgroup_id;
      } else {
        body.sub_subgroup_id = null;
      }

      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/ledgers/${ledgerId}/map`, {
        method: 'PATCH',
        body: JSON.stringify(body)
      });

      if (res.ok) {
        const updatedLedger = await res.json();
        const index = ledgers.findIndex(l => l.id === ledgerId);
        if (index !== -1) {
          ledgers[index] = updatedLedger;
        }
        delete transientMapping[ledgerId];
        updateProgressBar();
        renderLedgerPanel();
        
        // Flash status
        setTimeout(() => {
          const flash = document.getElementById(`status-${ledgerId}`);
          if (flash) {
            flash.style.opacity = 1;
            setTimeout(() => flash.style.opacity = 0, 1000);
          }
        }, 50);
      } else {
        alert('Failed to map ledger.');
      }
    } catch (e) {
      console.error(e);
      alert('Error mapping ledger.');
    }
  }

  function openBulkMapModal() {
    let modal = document.getElementById('bulk-map-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'bulk-map-modal';
      modal.className = 'audit-modal';
      document.body.appendChild(modal);
    }
    
    // We will leave the bulk map as 3 stacked dropdowns since it's a modal and the space is fine
    const groupOptionsHtml = '<option value="">Select Group...</option>' + treeData.map(g => `<option value="${g.id}">${window.AE.escapeHtml(g.name)}</option>`).join('');

    modal.style.display = 'flex';
    modal.innerHTML = `
      <div class="audit-modal-content" style="width: 400px;">
        <h3>Bulk Map (${selectedLedgerIds.size} Ledgers Selected)</h3>
        <div class="form-group" style="margin-bottom:12px;">
          <label class="form-label">Map selected ledgers to:</label>
          <select class="input" id="bulk_grp" style="margin-bottom:8px;">${groupOptionsHtml}</select>
          <select class="input" id="bulk_sgrp" style="margin-bottom:8px;" disabled><option value="">Select Subgroup...</option></select>
          <select class="input" id="bulk_ssgrp" disabled><option value="">Select Sub-subgroup...</option></select>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:12px;margin-top:20px;">
          <button type="button" class="btn btn-ghost" id="btn-bulk-cancel">Cancel</button>
          <button type="button" class="btn btn-primary" id="btn-bulk-apply" disabled>Apply Mapping</button>
        </div>
      </div>
    `;

    const selG = modal.querySelector('#bulk_grp');
    const selSg = modal.querySelector('#bulk_sgrp');
    const selSsg = modal.querySelector('#bulk_ssgrp');
    const btnApply = modal.querySelector('#btn-bulk-apply');

    selG.addEventListener('change', () => {
      selSg.innerHTML = '<option value="">Select Subgroup...</option>';
      selSsg.innerHTML = '<option value="">Select Sub-subgroup...</option>';
      selSsg.disabled = true;
      selSsg.style.display = '';
      btnApply.disabled = true;

      const gId = parseInt(selG.value);
      if (gId) {
        selSg.disabled = false;
        const gNode = treeData.find(g => g.id === gId);
        selSg.innerHTML += gNode.subgroups.map(sg => `<option value="${sg.id}">${window.AE.escapeHtml(sg.name)}</option>`).join('');
      } else {
        selSg.disabled = true;
      }
    });

    selSg.addEventListener('change', () => {
      selSsg.innerHTML = '<option value="">Select Sub-subgroup...</option>';
      btnApply.disabled = true;

      const sgId = parseInt(selSg.value);
      if (sgId) {
        const gNode = treeData.find(g => g.id === parseInt(selG.value));
        const sgNode = gNode.subgroups.find(s => s.id === sgId);
        if (sgNode.sub_subgroups.length > 0) {
          selSsg.disabled = false;
          selSsg.style.display = '';
          selSsg.innerHTML += sgNode.sub_subgroups.map(ssg => `<option value="${ssg.id}">${window.AE.escapeHtml(ssg.name)}</option>`).join('');
        } else {
          selSsg.disabled = true;
          selSsg.style.display = 'none';
          btnApply.disabled = false;
        }
      } else {
        selSsg.disabled = true;
        selSsg.style.display = '';
      }
    });

    selSsg.addEventListener('change', () => {
      btnApply.disabled = !selSsg.value;
    });

    modal.querySelector('#btn-bulk-cancel').addEventListener('click', () => modal.style.display = 'none');
    btnApply.addEventListener('click', async () => {
      const ssgId = parseInt(selSsg.value);
      const sgId = parseInt(selSg.value);
      if (!ssgId && !sgId) return;

      try {
        const bodyPayload = ssgId
          ? { ledger_ids: Array.from(selectedLedgerIds), sub_subgroup_id: ssgId }
          : { ledger_ids: Array.from(selectedLedgerIds), subgroup_id: sgId };

        const res = await window.AE.apiFetch(`/api/audit/${engagementId}/ledgers/bulk-map`, {
          method: 'POST',
          body: JSON.stringify(bodyPayload)
        });

        if (res.ok) {
          modal.style.display = 'none';
          selectedLedgerIds.clear();
          await loadData();
        } else {
          alert('Bulk mapping failed.');
        }
      } catch (err) {
        console.error(err);
        alert('Network error during bulk mapping.');
      }
    });
  }

  // ── Import Previous Year Mapping ───────────────────────────────────
  async function importPreviousMapping() {
    if (!engagement) return;
    const btn = document.getElementById('btn-import-prev-mapping');
    if (btn) btn.disabled = true;

    try {
      const listRes = await window.AE.apiFetch('/api/audit/engagements');
      if (!listRes.ok) throw new Error('Failed to search other engagements.');
      const allEng = await listRes.json();

      const matches = allEng
        .filter(e => e.client_name === engagement.client_name && e.id !== engagement.id)
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

      if (matches.length === 0) {
        alert('No previous year engagements found for this client.');
        return;
      }

      const prevEng = matches[0];
      if (!confirm(`Found previous engagement: ${prevEng.financial_year}. Would you like to import its mappings? Note: Missing subgroups will be automatically created.`)) {
        return;
      }

      const prevLedgersRes = await window.AE.apiFetch(`/api/audit/${prevEng.id}/trial-balance`);
      if (!prevLedgersRes.ok) throw new Error('Failed to load previous engagement details.');

      const prevLedgersData = await prevLedgersRes.json();
      const prevLedgers = prevLedgersData.ledgers || [];

      // Create a map of ledger code -> full path from previous year
      const prevMappingMap = {}; 
      prevLedgers.forEach(pl => {
        if (pl.is_mapped) {
          prevMappingMap[pl.ledger_code] = {
            group_name: pl.group_name,
            subgroup_name: pl.subgroup_name,
            sub_subgroup_name: pl.sub_subgroup_name
          };
        }
      });
      
      let matchedCount = 0;
      const ledgerToSSGNameMap = {}; // store mappings we intend to make

      // Figure out what needs creation
      for (const cl of ledgers) {
        if (!cl.is_mapped && prevMappingMap[cl.ledger_code]) {
          const path = prevMappingMap[cl.ledger_code];
          
          // Find matching group
          const gNode = treeData.find(g => g.name === path.group_name);
          if (!gNode) continue; // Should always exist since groups are fixed
          
          // Find/Create subgroup
          let sgNode = gNode.subgroups.find(sg => sg.name === path.subgroup_name);
          if (!sgNode) {
            const sgRes = await window.AE.apiFetch(`/api/audit/${engagementId}/subgroups`, {
              method: 'POST', body: JSON.stringify({ group_id: gNode.id, name: path.subgroup_name })
            });
            if (sgRes.ok) {
              const sgData = await sgRes.json();
              sgNode = { id: sgData.id, name: sgData.name, sub_subgroups: [] };
              gNode.subgroups.push(sgNode);
            }
          }
          
          if (!sgNode) continue;

          if (path.sub_subgroup_name) {
            // Find/Create sub-subgroup
            let ssgNode = sgNode.sub_subgroups.find(ssg => ssg.name === path.sub_subgroup_name);
            if (!ssgNode) {
              const ssgRes = await window.AE.apiFetch(`/api/audit/${engagementId}/sub-subgroups`, {
                method: 'POST', body: JSON.stringify({ subgroup_id: sgNode.id, name: path.sub_subgroup_name })
              });
              if (ssgRes.ok) {
                const ssgData = await ssgRes.json();
                ssgNode = { id: ssgData.id, name: ssgData.name };
                sgNode.sub_subgroups.push(ssgNode);
              }
            }

            if (ssgNode) {
               ledgerToSSGNameMap[cl.id] = { sub_subgroup_id: ssgNode.id };
               matchedCount++;
            }
          } else {
            // Mapped directly to subgroup (no sub-subgroup)
            ledgerToSSGNameMap[cl.id] = { subgroup_id: sgNode.id };
            matchedCount++;
          }
        }
      }

      if (matchedCount === 0) {
        alert('No new ledger code matches found to map.');
        return;
      }

      // Collect by mapping target for bulk mapping
      const bulkBySSG = {};
      const bulkBySG = {};
      for (const [lidStr, mapping] of Object.entries(ledgerToSSGNameMap)) {
        if (mapping.sub_subgroup_id) {
          const key = mapping.sub_subgroup_id;
          bulkBySSG[key] = bulkBySSG[key] || [];
          bulkBySSG[key].push(parseInt(lidStr));
        } else if (mapping.subgroup_id) {
          const key = mapping.subgroup_id;
          bulkBySG[key] = bulkBySG[key] || [];
          bulkBySG[key].push(parseInt(lidStr));
        }
      }

      // Execute bulk mapping queries
      let updatedTotal = 0;
      for (const leafId in bulkBySSG) {
        const res = await window.AE.apiFetch(`/api/audit/${engagementId}/ledgers/bulk-map`, {
          method: 'POST',
          body: JSON.stringify({
            ledger_ids: bulkBySSG[leafId],
            sub_subgroup_id: parseInt(leafId)
          })
        });
        if (res.ok) {
          const resData = await res.json();
          updatedTotal += resData.updated || 0;
        }
      }
      for (const sgId in bulkBySG) {
        const res = await window.AE.apiFetch(`/api/audit/${engagementId}/ledgers/bulk-map`, {
          method: 'POST',
          body: JSON.stringify({
            ledger_ids: bulkBySG[sgId],
            subgroup_id: parseInt(sgId)
          })
        });
        if (res.ok) {
          const resData = await res.json();
          updatedTotal += resData.updated || 0;
        }
      }

      alert(`Successfully matched and imported ${updatedTotal} mappings.`);
      await loadData();
    } catch (err) {
      console.error(err);
      alert(err.message || 'Error during mapping import.');
    } finally {
      if (btn) btn.disabled = false;
    }
  }
})();

const uploadForm = document.getElementById('upload-form');
const uploadStatus = document.getElementById('upload-status');
const componentList = document.getElementById('component-list');
const nodeLimitInput = document.getElementById('node-limit');
const focusInput = document.getElementById('focus-id');
const applyLimitButton = document.getElementById('apply-limit');
const focusButton = document.getElementById('focus-button');
const resetViewButton = document.getElementById('reset-view');
const exportPngButton = document.getElementById('export-png');
const exportSvgButton = document.getElementById('export-svg');
const loadAllButton = document.getElementById('load-all');
const rootInput = document.getElementById('root-account');
const loadRootButton = document.getElementById('load-root');

let currentJobId = null;
let currentComponentId = null;
let jobPoller = null;
let latestSummary = [];
let currentView = null;

const graphElement = document.getElementById('graph');
const graphEngineFactory = window.ForceGraph2D || window.ForceGraph;

if (typeof graphEngineFactory !== 'function') {
  const error = 'ForceGraph renderer failed to load. Please verify the CDN is reachable and refresh the page.';
  console.error(error);
  uploadStatus.textContent = error;
  throw new Error(error);
}

const Graph = graphEngineFactory();
const graph = Graph(graphElement)
  .nodeId('id')
  .nodeLabel(node => `${node.label}\nPast callsigns: ${node.nodeSize}\nShared overlaps: ${node.sharedCallsignCount}\nDegree: ${node.degree}`)
  .nodeVal(node => Math.max(1, node.nodeSize))
  .nodeColor(node => node.color || '#38bdf8')
  .linkWidth(link => Math.min(6, Math.log2(link.weight + 1) + 1))
  .linkDirectionalParticles(2)
  .linkDirectionalParticleSpeed(0.002)
  .linkDirectionalParticleWidth(link => Math.min(6, Math.log2(link.weight + 1) + 1))
  .cooldownTicks(400)
  .cooldownTime(20000)
  .warmupTicks(0)
  .linkColor(link => `rgba(226, 232, 240, ${Math.min(0.8, 0.25 + Math.log(link.weight + 1) * 0.15)})`)
  .graphData({ nodes: [], links: [] });

function createCenterGravityForce(strength = 0.02) {
  let nodes = [];
  const force = () => {
    if (!nodes || !nodes.length) {
      return;
    }
    nodes.forEach(node => {
      const x = node.x || 0;
      const y = node.y || 0;
      node.vx = (node.vx || 0) - x * strength;
      node.vy = (node.vy || 0) - y * strength;
    });
  };
  force.initialize = initNodes => {
    nodes = initNodes || [];
  };
  force.strength = value => {
    if (typeof value === 'undefined') {
      return strength;
    }
    strength = value;
    return force;
  };
  return force;
}

const d3Api = window.d3;
if (graph.d3Force) {
  if (d3Api && typeof d3Api.forceRadial === 'function') {
    const centerGravity = d3Api.forceRadial(0, 0, 0).strength(0.02);
    graph.d3Force('centerGravity', centerGravity);
  } else {
    console.info('Applying fallback center gravity force.');
    graph.d3Force('centerGravity', createCenterGravityForce(0.02));
  }

  const chargeForce = graph.d3Force('charge');
  if (chargeForce && typeof chargeForce.strength === 'function') {
    chargeForce.strength(-45);
    if (typeof chargeForce.distanceMax === 'function') {
      chargeForce.distanceMax(500);
    }
    if (typeof chargeForce.distanceMin === 'function') {
      chargeForce.distanceMin(5);
    }
  } else {
    console.warn('ForceGraph charge force unavailable; nodes may overlap.');
  }
}

graph.onEngineStop(() => {
  if (graph.graphData().nodes.length) {
    graph.zoomToFit(400, 60, node => true);
  }
});

async function uploadDataset(event) {
  event.preventDefault();
  const formData = new FormData(uploadForm);
  const file = formData.get('file');
  if (!file || !file.size) {
    setStatus('Please pick a MongoDB JSON export first.');
    return;
  }
  setStatus('Uploading file… large exports may take a while.');
  disableInteraction(true);
  try {
    const response = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      throw new Error(problem.error || response.statusText);
    }
    const payload = await response.json();
    currentJobId = payload.jobId;
    latestSummary = [];
    currentComponentId = null;
    currentView = null;
    graph.graphData({ nodes: [], links: [] });
    setStatus(`Upload complete. Job ${currentJobId} queued.`);
    pollJobStatus();
  } catch (error) {
    console.error(error);
    setStatus(`Upload failed: ${error.message}`);
    disableInteraction(false);
  }
}

function setStatus(message) {
  uploadStatus.textContent = message;
}

function disableInteraction(isDisabled) {
  uploadForm.querySelector('button[type="submit"]').disabled = isDisabled;
  applyLimitButton.disabled = isDisabled;
  focusButton.disabled = isDisabled;
  resetViewButton.disabled = isDisabled;
  exportPngButton.disabled = isDisabled;
  exportSvgButton.disabled = isDisabled;
  loadAllButton.disabled = isDisabled;
  loadRootButton.disabled = isDisabled;
}

async function pollJobStatus() {
  if (!currentJobId) {
    return;
  }
  if (jobPoller) {
    clearInterval(jobPoller);
  }
  const check = async () => {
    const response = await fetch(`/api/job/${currentJobId}`);
    if (!response.ok) {
      setStatus('Job disappeared or failed.');
      disableInteraction(false);
      clearInterval(jobPoller);
      jobPoller = null;
      return;
    }
    const payload = await response.json();
    setStatus(payload.message || payload.status);
    if (payload.status === 'ready') {
      clearInterval(jobPoller);
      jobPoller = null;
      disableInteraction(false);
      latestSummary = payload.summary || [];
      renderComponentSummary(latestSummary);
    }
  };
  await check();
  jobPoller = setInterval(check, 3000);
}

function renderComponentSummary(summary) {
  if (!summary || !summary.length) {
    componentList.classList.add('empty');
    componentList.textContent = 'No connected components with shared call signs were found.';
    return;
  }
  componentList.classList.remove('empty');
  const table = document.createElement('table');
  table.innerHTML = `
    <thead>
      <tr>
        <th>Component</th>
        <th>Nodes</th>
        <th>Edges</th>
        <th></th>
      </tr>
    </thead>
  `;
  const tbody = document.createElement('tbody');
  summary.forEach(component => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><span class="color-dot" style="background:${component.color}"></span>${component.id}</td>
      <td>${component.nodeCount.toLocaleString()}</td>
      <td>${component.edgeCount.toLocaleString()}</td>
      <td><button data-component="${component.id}">Load</button></td>
    `;
    row.querySelector('button').addEventListener('click', () => loadComponent(component.id));
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  componentList.innerHTML = '';
  componentList.appendChild(table);
}

async function loadComponent(componentId, options = {}) {
  if (!currentJobId) {
    return;
  }
  currentComponentId = componentId;
  currentView = { type: 'component', id: componentId };
  const limit = typeof options.limit === 'number' ? options.limit : parseInt(nodeLimitInput.value, 10) || undefined;
  setStatus(`Loading component ${componentId} with limit ${limit || 'all'}…`);
  try {
    const response = await fetch(`/api/job/${currentJobId}/component/${componentId}${limit ? `?limit=${limit}` : ''}`);
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      throw new Error(problem.error || 'Unable to fetch component');
    }
    const payload = await response.json();
    renderGraph(payload);
  } catch (error) {
    console.error(error);
    setStatus(error.message);
  }
}

function renderGraph(data) {
  if (!data || !data.nodes) {
    return;
  }
  graph.graphData({ nodes: data.nodes, links: data.edges });
  const nodeCount = data.nodes.length.toLocaleString();
  const edgeCount = data.edges.length.toLocaleString();
  if (data.componentId === 'all') {
    setStatus(`All ${data.componentCount} components rendered with ${nodeCount} nodes and ${edgeCount} edges.`);
  } else if (data.rootAccountId) {
    setStatus(`Component ${data.componentId} containing account ${data.rootAccountId} ready with ${nodeCount} nodes and ${edgeCount} edges.`);
  } else {
    setStatus(`Component ${data.componentId} ready with ${nodeCount} nodes and ${edgeCount} edges.`);
  }
}

function applyLimit() {
  const limit = parseInt(nodeLimitInput.value, 10);
  if (!currentView) {
    return;
  }
  if (currentView.type === 'component' && currentComponentId) {
    loadComponent(currentComponentId, { limit });
  } else if (currentView.type === 'all') {
    loadAllComponents({ limit });
  } else if (currentView.type === 'root') {
    loadRootGraph(currentView.id, { limit });
  }
}

async function loadAllComponents(options = {}) {
  if (!currentJobId) {
    return;
  }
  currentView = { type: 'all' };
  currentComponentId = null;
  const limit = typeof options.limit === 'number' ? options.limit : parseInt(nodeLimitInput.value, 10) || undefined;
  setStatus(`Loading all components with limit ${limit || 'all'}…`);
  try {
    const params = new URLSearchParams();
    if (limit) {
      params.set('limit', limit);
    }
    const response = await fetch(`/api/job/${currentJobId}/graph${params.toString() ? `?${params}` : ''}`);
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      throw new Error(problem.error || 'Unable to fetch combined graph');
    }
    const payload = await response.json();
    renderGraph(payload);
  } catch (error) {
    console.error(error);
    setStatus(error.message);
  }
}

async function loadRootGraph(rootAccount, options = {}) {
  if (!currentJobId) {
    return;
  }
  const rootId = (rootAccount || rootInput.value || '').trim();
  if (!rootId) {
    setStatus('Enter an account ID to load its connections.');
    return;
  }
  currentView = { type: 'root', id: rootId };
  const limit = typeof options.limit === 'number' ? options.limit : parseInt(nodeLimitInput.value, 10) || undefined;
  setStatus(`Loading component containing ${rootId} with limit ${limit || 'all'}…`);
  try {
    const params = new URLSearchParams();
    if (limit) {
      params.set('limit', limit);
    }
    params.set('rootAccount', rootId);
    const response = await fetch(`/api/job/${currentJobId}/graph?${params.toString()}`);
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      throw new Error(problem.error || 'Unable to fetch account graph');
    }
    const payload = await response.json();
    currentComponentId = payload.componentId;
    renderGraph(payload);
  } catch (error) {
    console.error(error);
    setStatus(error.message);
  }
}

function focusOnNode() {
  const id = focusInput.value.trim();
  if (!id) {
    return;
  }
  const { nodes } = graph.graphData();
  const target = nodes.find(node => node.id === id || node.accountId === id);
  if (!target) {
    setStatus(`Node ${id} is not loaded. Increase the node limit or load the matching component.`);
    return;
  }
  const x = target.x || 0;
  const y = target.y || 0;
  graph.centerAt(x, y, 1000);
  graph.zoom(6, 1000);
  setStatus(`Focused on node ${id}.`);
}

function resetView() {
  graph.zoomToFit(1000, 80);
}

function exportPNG() {
  const canvas = graphElement.querySelector('canvas');
  if (!canvas) {
    return;
  }
  const url = canvas.toDataURL('image/png');
  downloadDataUrl(url, 'callsign-graph.png');
}

function exportSVG() {
  const graphData = graph.graphData();
  const { nodes, links } = graphData;
  if (!nodes.length) {
    return;
  }
  const xs = nodes.map(node => node.x || 0);
  const ys = nodes.map(node => node.y || 0);
  const minX = Math.min(...xs) - 50;
  const minY = Math.min(...ys) - 50;
  const maxX = Math.max(...xs) + 50;
  const maxY = Math.max(...ys) + 50;
  const width = maxX - minX;
  const height = maxY - minY;
  const svgParts = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${minX} ${minY} ${width} ${height}" width="${width}" height="${height}">`,
    '<g stroke-linecap="round" stroke-linejoin="round">'
  ];
  links.forEach(link => {
    const weight = Math.min(5, Math.log2(link.weight + 1) + 0.5);
    svgParts.push(`<line x1="${link.source.x}" y1="${link.source.y}" x2="${link.target.x}" y2="${link.target.y}" stroke="rgba(148,163,184,0.6)" stroke-width="${weight}" />`);
  });
  nodes.forEach(node => {
    const radius = Math.max(2, Math.log2(node.nodeSize + 1) * 3);
    svgParts.push(`<circle cx="${node.x}" cy="${node.y}" r="${radius}" fill="${node.color || '#38bdf8'}" />`);
  });
  svgParts.push('</g></svg>');
  const blob = new Blob([svgParts.join('\n')], { type: 'image/svg+xml' });
  downloadBlob(blob, 'callsign-graph.svg');
}

function downloadDataUrl(url, filename) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  downloadDataUrl(url, filename);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

uploadForm.addEventListener('submit', uploadDataset);
applyLimitButton.addEventListener('click', applyLimit);
focusButton.addEventListener('click', focusOnNode);
resetViewButton.addEventListener('click', resetView);
exportPngButton.addEventListener('click', exportPNG);
exportSvgButton.addEventListener('click', exportSVG);
loadAllButton.addEventListener('click', () => loadAllComponents());
loadRootButton.addEventListener('click', () => loadRootGraph());

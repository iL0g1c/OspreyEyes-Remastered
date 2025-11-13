const fileInput = document.getElementById('file-input');
const statusEl = document.getElementById('status');
const statsEl = document.getElementById('stats');
const exportSvgBtn = document.getElementById('export-svg');
const exportPngBtn = document.getElementById('export-png');
const minCallsignsInput = document.getElementById('min-callsigns');
const linkThresholdInput = document.getElementById('link-threshold');
const repulsionInput = document.getElementById('repulsion');
const distanceInput = document.getElementById('distance');
const searchInput = document.getElementById('search');

let rawAccounts = [];
let currentGraph = { nodes: [], links: [] };
let adjacencyMap = new Map();
let highlightedNode = null;
let hoverNeighbors = new Set();
let searchTimeout = null;

const graph = ForceGraph()(document.getElementById('graph'))
  .nodeId('id')
  .nodeVal(node => Math.max(1, node.callsignCount))
  .cooldownTicks(200)
  .warmupTicks(100)
  .cooldownTime(20000)
  .linkWidth(link => 0.5 + Math.log2(1 + link.weight))
  .linkColor(link => applyOpacity(link.color, 0.4))
  .nodeLabel(node => node.tooltip)
  .onEngineStop(() => setStatus('Layout stabilized. You can now explore or export the map.'))
  .onNodeHover(node => {
    highlightedNode = node || null;
    hoverNeighbors = collectNeighbors(node);
  })
  .onNodeClick(node => focusOnNode(node));

if (typeof graph.linkDirectionalParticles === 'function') {
  graph.linkDirectionalParticles(0);
}

graph.d3Force('charge').strength(() => parseInt(repulsionInput.value, 10));
graph.d3Force('link').distance(link => link.distance).strength(0.1);
graph.d3Force('center');

graph.nodeCanvasObject((node, ctx, globalScale) => {
  const size = Math.max(3, Math.sqrt(node.callsignCount) * 2.2);
  ctx.beginPath();
  ctx.arc(node.x, node.y, size, 0, 2 * Math.PI, false);
  ctx.fillStyle = node.color;
  ctx.fill();

  if (highlightedNode && (node === highlightedNode || hoverNeighbors.has(node.id))) {
    ctx.lineWidth = Math.max(1.5 / globalScale, 0.5);
    ctx.strokeStyle = '#ffffff';
    ctx.stroke();
  }
});

graph.nodePointerAreaPaint((node, color, ctx) => {
  const size = Math.max(3, Math.sqrt(node.callsignCount) * 2.2);
  ctx.beginPath();
  ctx.arc(node.x, node.y, size, 0, 2 * Math.PI, false);
  ctx.fillStyle = color;
  ctx.fill();
});

fileInput.addEventListener('change', event => {
  const [file] = event.target.files;
  if (!file) return;
  resetGraph();
  setStatus(`Loading ${file.name}...`);
  const reader = new FileReader();
  reader.onload = ({ target }) => {
    try {
      rawAccounts = normalizeDataset(target.result);
      setStatus(`Loaded ${rawAccounts.length.toLocaleString()} accounts. Building graph...`);
      regenerateGraph();
    } catch (error) {
      console.error(error);
      setStatus(`Unable to parse file: ${error.message}`);
    }
  };
  reader.onerror = () => setStatus('Failed to read file. Please try again.');
  reader.readAsText(file);
});

[minCallsignsInput, linkThresholdInput].forEach(input => {
  input.addEventListener('change', () => regenerateGraph());
});

[repulsionInput, distanceInput].forEach(input => {
  input.addEventListener('input', () => {
    if (input === repulsionInput) {
      graph.d3Force('charge').strength(() => parseInt(repulsionInput.value, 10));
    }
    if (input === distanceInput) {
      graph.d3Force('link').distance(link =>
        Math.max(40, parseInt(distanceInput.value, 10) - Math.log2(1 + link.weight) * 5)
      );
    }
    graph.d3ReheatSimulation();
  });
});

searchInput.addEventListener('keydown', event => {
  if (event.key === 'Enter') {
    focusOnNode(findNodeByQuery(searchInput.value));
  }
});

exportSvgBtn.addEventListener('click', () => exportSvg());
exportPngBtn.addEventListener('click', () => exportPng());

function regenerateGraph() {
  if (!rawAccounts.length) return;
  setStatus('Rebuilding graph with current parameters...');
  runWhenIdle(() => {
    currentGraph = buildGraph(rawAccounts, {
      minCallsigns: parseInt(minCallsignsInput.value, 10),
      maxAccountsPerCallsign: parseInt(linkThresholdInput.value, 10),
      preferredDistance: parseInt(distanceInput.value, 10)
    });
    adjacencyMap = buildAdjacency(currentGraph.links);
    graph.graphData(currentGraph);
    updateStats(currentGraph);
    exportSvgBtn.disabled = currentGraph.nodes.length === 0;
    exportPngBtn.disabled = currentGraph.nodes.length === 0;
    setStatus(`Rendered ${currentGraph.nodes.length.toLocaleString()} nodes and ${currentGraph.links.length.toLocaleString()} links.`);
  });
}

function buildGraph(accounts, options) {
  const nodes = [];
  const nodeById = new Map();
  const callsignIndex = new Map();
  const minCalls = Math.max(1, options.minCallsigns || 1);
  const maxPerCallsign = Math.max(2, options.maxAccountsPerCallsign || 12);

  accounts.forEach((account, index) => {
    const normalised = normalizeAccount(account, index);
    if (!normalised || normalised.callsignCount < minCalls) return;

    nodes.push(normalised);
    nodeById.set(normalised.id, normalised);

    normalised.callsigns.forEach(entry => {
      const key = entry.value;
      if (!key) return;
      if (!callsignIndex.has(key)) {
        callsignIndex.set(key, []);
      }
      callsignIndex.get(key).push({ nodeId: normalised.id, timestamp: entry.timestamp, score: entry.score });
    });
  });

  const linkMap = new Map();
  for (const [callsign, entryList] of callsignIndex.entries()) {
    if (entryList.length < 2) continue;
    entryList.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
    const limit = Math.min(entryList.length, maxPerCallsign);
    for (let i = 0; i < limit; i += 1) {
      for (let j = i + 1; j < limit; j += 1) {
        const first = entryList[i];
        const second = entryList[j];
        const key = makeLinkKey(first.nodeId, second.nodeId);
        if (!linkMap.has(key)) {
          linkMap.set(key, {
            source: first.nodeId,
            target: second.nodeId,
            weight: 0,
            callsigns: new Set()
          });
        }
        const link = linkMap.get(key);
        link.weight += first.score + second.score;
        link.callsigns.add(callsign);
      }
    }
  }

  const links = Array.from(linkMap.values()).map(link => ({
    source: link.source,
    target: link.target,
    weight: link.weight,
    callsigns: Array.from(link.callsigns),
    distance: Math.max(40, (options.preferredDistance || 140) - Math.log2(1 + link.weight) * 8)
  }));

  assignComponentColors(nodes, links, nodeById);

  links.forEach(link => {
    const source = nodeById.get(link.source);
    const target = nodeById.get(link.target);
    link.color = mixColors(source.color, target.color);
  });

  return { nodes, links };
}

function normalizeDataset(text) {
  const trimmed = text.trim();
  if (!trimmed) return [];
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) return parsed;
    return [parsed];
  } catch (error) {
    const lines = trimmed.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (!lines.length) throw error;
    return lines.map(line => JSON.parse(line));
  }
}

function normalizeAccount(account, fallbackIndex) {
  if (!account) return null;
  const id = account.accountID ?? account._id?.$oid ?? `account-${fallbackIndex}`;
  const callsigns = normalizeCallsigns(account.pastCallsigns || []);
  if (!callsigns.length) return null;

  const deduped = dedupeCallsigns(callsigns);
  const callsignCount = deduped.length;
  const tooltip = [
    `Account ID: ${account.accountID ?? 'Unknown'}`,
    account.currentCallsign ? `Current callsign: ${account.currentCallsign}` : null,
    `Tracked callsigns: ${callsignCount}`,
    deduped.slice(0, 4).map(entry => entry.value).join(', ')
  ]
    .filter(Boolean)
    .join('\n');

  return {
    id: id.toString(),
    accountID: account.accountID,
    currentCallsign: account.currentCallsign,
    callsignCount,
    callsigns: deduped,
    tooltip,
    color: '#ffffff'
  };
}

function normalizeCallsigns(rawList) {
  if (!Array.isArray(rawList)) return [];
  return rawList
    .map(entry => {
      if (!entry) return null;
      if (typeof entry === 'string') {
        return buildCallsignEntry(entry);
      }
      if (typeof entry === 'object') {
        const value = entry.callsign || entry.value || entry.name || entry.past || entry[0];
        const timestamp = extractDate(entry.timestamp || entry.date || entry.updatedAt || entry.$date);
        return buildCallsignEntry(value, timestamp);
      }
      return null;
    })
    .filter(Boolean);
}

function buildCallsignEntry(value, timestamp) {
  if (!value || typeof value !== 'string') return null;
  const sanitized = value.trim();
  if (!sanitized) return null;
  const ts = extractDate(timestamp);
  return {
    value: sanitized,
    timestamp: ts ? ts.getTime() : null,
    score: computeRecencyScore(ts)
  };
}

function dedupeCallsigns(entries) {
  const seen = new Map();
  entries.forEach(entry => {
    const existing = seen.get(entry.value);
    if (!existing || (entry.timestamp || 0) > (existing.timestamp || 0)) {
      seen.set(entry.value, entry);
    }
  });
  return Array.from(seen.values());
}

function computeRecencyScore(date) {
  if (!date) return 0.5;
  const now = Date.now();
  const deltaDays = Math.max(0, (now - date.getTime()) / 86_400_000);
  return 1 / (1 + deltaDays / 30);
}

function extractDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value === 'number') return new Date(value);
  if (typeof value === 'string') {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  if (typeof value === 'object') {
    if (value.$date) return extractDate(value.$date);
    if (value.iso) return extractDate(value.iso);
  }
  return null;
}

function assignComponentColors(nodes, links, nodeById) {
  if (!nodes.length) return;
  const adjacency = buildAdjacency(links);
  const visited = new Set();
  let hueSeed = 0.12;
  const golden = 0.61803398875;

  nodes.forEach(node => {
    if (visited.has(node.id)) return;
    hueSeed = (hueSeed + golden) % 1;
    const baseHue = hueSeed * 360;
    const queue = [{ id: node.id, depth: 0 }];
    visited.add(node.id);
    while (queue.length) {
      const { id, depth } = queue.shift();
      const current = nodeById.get(id);
      if (!current) continue;
      current.color = hslToHex(baseHue, 60, clamp(30 + depth * 4, 25, 65));
      const neighbors = adjacency.get(id);
      if (!neighbors) continue;
      neighbors.forEach(neighborId => {
        if (visited.has(neighborId)) return;
        visited.add(neighborId);
        queue.push({ id: neighborId, depth: depth + 1 });
      });
    }
  });
}

function buildAdjacency(links) {
  const adjacency = new Map();
  links.forEach(link => {
    const source = typeof link.source === 'object' ? link.source.id : link.source;
    const target = typeof link.target === 'object' ? link.target.id : link.target;
    if (!adjacency.has(source)) adjacency.set(source, new Set());
    if (!adjacency.has(target)) adjacency.set(target, new Set());
    adjacency.get(source).add(target);
    adjacency.get(target).add(source);
  });
  return adjacency;
}

function collectNeighbors(node) {
  if (!node) return new Set();
  const neighbors = adjacencyMap.get(node.id);
  if (!neighbors) return new Set();
  return new Set(neighbors);
}

function mixColors(colorA, colorB) {
  const a = hexToRgb(colorA);
  const b = hexToRgb(colorB);
  if (!a || !b) return '#7dd3fc';
  const mixed = {
    r: Math.round((a.r + b.r) / 2),
    g: Math.round((a.g + b.g) / 2),
    b: Math.round((a.b + b.b) / 2)
  };
  return rgbToHex(mixed.r, mixed.g, mixed.b);
}

function hslToHex(h, s, l) {
  const a = s * Math.min(l, 100 - l) / 100;
  const f = n => {
    const k = (n + h / 30) % 12;
    const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * color / 100)
      .toString(16)
      .padStart(2, '0');
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function hexToRgb(hex) {
  if (!hex) return null;
  const normalized = hex.replace('#', '');
  if (normalized.length !== 6) return null;
  const bigint = parseInt(normalized, 16);
  return {
    r: (bigint >> 16) & 255,
    g: (bigint >> 8) & 255,
    b: bigint & 255
  };
}

function rgbToHex(r, g, b) {
  return `#${[r, g, b]
    .map(value => value.toString(16).padStart(2, '0'))
    .join('')}`;
}

function applyOpacity(hexColor, alpha = 1) {
  const rgb = hexToRgb(hexColor);
  if (!rgb) {
    return `rgba(125, 211, 252, ${alpha})`;
  }
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
}

function makeLinkKey(a, b) {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function setStatus(message) {
  statusEl.textContent = message;
}

function updateStats(graphData) {
  const { nodes, links } = graphData;
  if (!nodes.length) {
    statsEl.textContent = '';
    return;
  }
  const averageCallsigns = (
    nodes.reduce((total, node) => total + node.callsignCount, 0) / nodes.length
  ).toFixed(2);
  statsEl.textContent = `Average callsigns per node: ${averageCallsigns} • Components: ${countComponents(nodes, links)} • Max link weight: ${links.reduce((max, link) => Math.max(max, link.weight), 0).toFixed(2)}`;
}

function countComponents(nodes, links) {
  const adjacency = buildAdjacency(links);
  const visited = new Set();
  let count = 0;
  nodes.forEach(node => {
    if (visited.has(node.id)) return;
    count += 1;
    const stack = [node.id];
    visited.add(node.id);
    while (stack.length) {
      const current = stack.pop();
      const neighbors = adjacency.get(current);
      if (!neighbors) continue;
      neighbors.forEach(neighbor => {
        if (visited.has(neighbor)) return;
        visited.add(neighbor);
        stack.push(neighbor);
      });
    }
  });
  return count;
}

function focusOnNode(node) {
  if (!node) return;
  highlightedNode = node;
  hoverNeighbors = collectNeighbors(node);
  graph.centerAt(node.x, node.y, 600);
  graph.zoom(4, 600);
  if (searchTimeout) clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    highlightedNode = null;
    hoverNeighbors = new Set();
  }, 6000);
}

function findNodeByQuery(query) {
  if (!query || !currentGraph.nodes.length) return null;
  const normalised = query.trim().toLowerCase();
  if (!normalised) return null;
  return (
    currentGraph.nodes.find(node => node.id.toLowerCase() === normalised) ||
    currentGraph.nodes.find(node => (node.accountID ?? '').toString() === normalised) ||
    currentGraph.nodes.find(node => node.callsigns.some(entry => entry.value.toLowerCase().includes(normalised))) ||
    null
  );
}

function exportPng() {
  if (!currentGraph.nodes.length) return;
  const canvas = graph.renderer().domElement;
  const dataUrl = canvas.toDataURL('image/png');
  downloadBlob(dataUrl, `callsign-network-${Date.now()}.png`);
}

function exportSvg() {
  if (!currentGraph.nodes.length) return;
  const nodes = currentGraph.nodes;
  const links = currentGraph.links;
  const positionedNodes = nodes.filter(
    node => Number.isFinite(node.x) && Number.isFinite(node.y)
  );
  if (!positionedNodes.length) {
    setStatus('Graph layout is still initializing. Please wait a moment before exporting.');
    return;
  }
  const nodeLookup = new Map(nodes.map(node => [node.id, node]));
  const xs = positionedNodes.map(node => node.x);
  const ys = positionedNodes.map(node => node.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const padding = 40;
  const width = maxX - minX + padding * 2;
  const height = maxY - minY + padding * 2;

  const svgParts = [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${minX - padding} ${minY - padding} ${width} ${height}" width="${width}" height="${height}">`,
    '<rect fill="#05060a" x="-10000" y="-10000" width="20000" height="20000" />'
  ];

  links.forEach(link => {
    const source = typeof link.source === 'object' ? link.source : nodeLookup.get(link.source);
    const target = typeof link.target === 'object' ? link.target : nodeLookup.get(link.target);
    if (!source || !target || !Number.isFinite(source.x) || !Number.isFinite(source.y) || !Number.isFinite(target.x) || !Number.isFinite(target.y)) {
      return;
    }
    svgParts.push(
      `<line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" stroke="${link.color}" stroke-opacity="0.4" stroke-width="${0.5 + Math.log2(1 + link.weight)}" />`
    );
  });

  nodes.forEach(node => {
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;
    const radius = Math.max(3, Math.sqrt(node.callsignCount) * 2.2);
    svgParts.push(
      `<circle cx="${node.x}" cy="${node.y}" r="${radius}" fill="${node.color}" />`
    );
  });

  svgParts.push('</svg>');
  const blob = new Blob(svgParts, { type: 'image/svg+xml' });
  const url = URL.createObjectURL(blob);
  triggerDownload(url, `callsign-network-${Date.now()}.svg`);
}

function downloadBlob(dataUrl, filename) {
  triggerDownload(dataUrl, filename);
}

function triggerDownload(url, filename) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  if (url.startsWith('blob:')) {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function resetGraph() {
  rawAccounts = [];
  currentGraph = { nodes: [], links: [] };
  adjacencyMap = new Map();
  graph.graphData(currentGraph);
  statsEl.textContent = '';
  exportSvgBtn.disabled = true;
  exportPngBtn.disabled = true;
}

function runWhenIdle(cb) {
  if (typeof window.requestIdleCallback === 'function') {
    window.requestIdleCallback(cb);
  } else {
    setTimeout(cb, 0);
  }
}

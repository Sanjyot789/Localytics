import './neighbourhoods.css';

const byId = (id) => document.getElementById(id);
const explorer = byId('neighbourhoods');
const form = byId('area-preferences');
const status = byId('area-status');
const details = byId('area-details');
const names = {
  bus_stop: 'Bus stops', metro_station: 'Metro stations', airport_terminal: 'Airport terminals',
  school: 'Schools', hospital: 'Hospitals', park: 'Public green spaces', gym: 'Gyms',
  mall: 'Malls', ev: 'EV charging',
};
const initialWeights = { transit: 4, school: 3, hospital: 3, park: 3 };
const evidence = byId('neighbourhood-evidence');
let loading = false;

let grid, factors, groups, map, active, selected;
let areas = [];
let comparison = new Map();
let revision = 0;

function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

async function request(path, query = '') {
  const response = await fetch('/api/localytics/' + path + '?' + query);
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new Error('Localytics data server is unavailable. Start the Localytics data service and try again.');
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Localytics data server is unavailable.');
  return data;
}

function createInputs() {
  for (const [key, name] of Object.entries(factors)) {
    const label = element('label', name);
    const input = document.createElement('input');
    input.type = 'range';
    input.min = 0;
    input.max = 5;
    input.name = 'w_' + key;
    input.value = initialWeights[key] ?? 0;
    const value = element('output', input.value);
    input.addEventListener('input', () => { value.textContent = input.value; });
    label.append(value, input);
    byId('area-factors').append(label);
  }
  for (const key of ['metro_station', 'school', 'hospital', 'park', 'ev']) {
    const label = element('label', names[key]);
    const input = document.createElement('input');
    input.type = 'number';
    input.min = '0.1';
    input.step = '0.1';
    input.name = 'must_' + key;
    label.append(input);
    byId('area-must').append(label);
  }
}

function drawGrid() {
  if (!map?.getSource('localytics-grid')) return;
  const rows = new Map(areas.map((row) => [row.id, row]));
  for (const feature of grid.features) {
    const id = feature.properties.area;
    feature.properties.score = rows.get(id)?.score ?? -1;
    feature.properties.pm = rows.get(id)?.pm ?? -1;
    feature.properties.group = groups?.[id] ?? -1;
    feature.properties.selected = feature.properties.area === selected;
  }
  map.getSource('localytics-grid').setData(grid);
  const layer = byId('area-layer').value;
  const colors = {
    score: ['step', ['get', 'score'], '#7c8189', 0, '#de796d', 40, '#efc46c', 70, '#55b99c'],
    pm: ['step', ['get', 'pm'], '#7c8189', 0, '#55b99c', 30.01, '#efc46c', 60.01, '#e78e58', 90.01, '#de796d', 120.01, '#b74b68', 250.01, '#7b3360'],
    groups: ['match', ['get', 'group'], 0, '#70b0e0', 1, '#dcb46e', 2, '#69bb9e', 3, '#c58cce', 4, '#df826d', 5, '#866fc1', '#7c8189'],
  };
  map.setPaintProperty('area-fill', 'fill-color', colors[layer]);
  byId('area-legend').textContent = {
    score: 'Green ≥70 · Gold 40–69 · Red <40 · Grey unranked',
    pm: 'PM2.5 indicator · Green ≤30 through burgundy >250 · Grey means no eligible recent reading',
    groups: 'Colours show groups of similar areas. Grey means no group data.',
  }[layer];
}

function mountMap() {
  if (!map || map.getSource('localytics-grid')) return;
  map.addSource('localytics-grid', { type: 'geojson', data: grid });
  const before = map.getLayer('site-fill') ? 'site-fill' : undefined;
  map.addLayer({ id: 'area-fill', source: 'localytics-grid', type: 'fill', paint: {
    'fill-color': '#7c8189', 'fill-opacity': 0.47,
  } }, before);
  map.addLayer({ id: 'area-outline', source: 'localytics-grid', type: 'line', paint: {
    'line-color': ['case', ['boolean', ['get', 'selected'], false], '#fff', '#15242b'],
    'line-width': ['case', ['boolean', ['get', 'selected'], false], 3, 0.5],
  } }, before);
  map.on('click', 'area-fill', ({ features, point }) => {
    const propertyLayers = ['bld', 'site-fill', 'glow'].filter((id) => map.getLayer(id));
    if (propertyLayers.length && map.queryRenderedFeatures(point, { layers: propertyLayers }).length) return;
    showArea(features[0].properties.area);
  });
  map.on('mouseenter', 'area-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'area-fill', () => { map.getCanvas().style.cursor = ''; });
  setAreaLayers();
  drawGrid();
}

function setAreaLayers() {
  for (const layer of ['area-fill', 'area-outline']) {
    if (map?.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', explorer.open ? 'visible' : 'none');
  }
}

document.addEventListener('flat-finder-map-ready', () => {
  map = window.__map;
  if (grid) mountMap();
});

byId('area-zoom').onclick = () => {
  map?.fitBounds([[76.78, 28.39], [77.35, 28.9]], { padding: 40, pitch: 0, bearing: 0 });
};

const fmt = (value, suffix = '') => value == null ? 'Unavailable' : String(value) + suffix;

function renderComparison() {
  const panel = byId('area-compare');
  panel.replaceChildren();
  for (const row of comparison.values()) {
    const item = element('details', '');
    item.append(element('summary', row.label + ' · ' + fmt(row.score, '/100')));
    for (const [key, label] of Object.entries(factors)) {
      item.append(element('p', label + ' · ' + fmt(row.scores[key] == null ? null : Math.round(row.scores[key] * 100), '/100')));
    }
    const remove = element('button', 'Remove');
    remove.onclick = () => { comparison.delete(row.id); renderComparison(); };
    item.append(remove);
    panel.append(item);
  }
}

async function showArea(id, focus = false) {
  if (!active) return;
  selected = id;
  evidence.hidden = false;
  document.body.classList.add('area-evidence-open');
  drawGrid();
  const query = new URLSearchParams(active);
  query.set('id', id);
  details.textContent = 'Loading area evidence…';
  try {
    const row = await request('area', query);
    if (selected !== id || query.get('revision') !== active.get('revision')) return;
    if (focus) map?.easeTo({ center: [row.lon, row.lat], zoom: 12 });
    details.replaceChildren(
      element('h3', row.label),
      element('p', fmt(row.score, '/100') + ' · ' + row.lat.toFixed(4) + ', ' + row.lon.toFixed(4)),
    );
    const compare = element('button', 'Add to comparison');
    compare.className = 'ghost';
    compare.onclick = () => {
      if (!comparison.has(id) && comparison.size === 3) {
        status.textContent = 'Remove an area before adding another.';
        return;
      }
      comparison.set(id, row);
      renderComparison();
    };
    details.append(compare, element('h4', 'Factor scores and contributions'));
    for (const [key, label] of Object.entries(factors)) {
      const score = row.scores[key];
      const contribution = row.contributions[key];
      details.append(element('p', label + ' · ' + fmt(score == null ? null : Math.round(score * 100), '/100')
        + (contribution == null ? '' : ' · +' + contribution.toFixed(1) + ' points')));
    }
    for (const check of row.checks) {
      details.append(element('p', names[check.factor] + ' within ' + check.limit + ' km · ' + check.status));
    }
    details.append(element('h4', 'Nearby facilities'));
    for (const [key, entry] of Object.entries(row.features)) {
      details.append(element('p', (names[key] ?? key) + ' · ' + (entry.coverage
        ? entry.count + ' mapped · nearest ' + fmt(entry.nearest_km, ' km') : 'Incomplete coverage')));
    }
    if (row.work_km != null) details.append(element('p', 'Workplace · ' + row.work_km + ' km straight line'));
    details.append(element('h4', 'Air-quality observations'));
    if (row.air) {
      details.append(element('p', row.air.name + ' · ' + row.air.distance_km + ' km · PM2.5 ' + fmt(row.air.pm)
        + ' · age ' + fmt(row.air.age_hours, ' h')), element('p', row.air.status));
      for (const reading of row.air.readings) {
        details.append(element('p', reading.pollutant_id + ' · Avg ' + fmt(reading.avg_value) + ' · ' + fmt(reading.last_update)));
      }
    } else {
      details.append(element('p', 'No cached monitor observations.'));
    }
  } catch (error) {
    if (selected === id && query.get('revision') === active.get('revision')) details.textContent = error.message;
  }
}

async function rank() {
  const current = ++revision;
  const query = new URLSearchParams(new FormData(form));
  query.set('revision', current);
  status.textContent = 'Ranking neighbourhoods…';
  try {
    const result = await request('rank', query);
    if (current !== revision) return;
    active = query;
    areas = result.areas;
    comparison.clear();
    renderComparison();
    const ranked = areas.filter((row) => row.score != null);
    status.textContent = ranked.length + ' of ' + areas.length + ' cells ranked'
      + (result.air_fetched ? ' · Cached air observations fetched ' + result.air_fetched : '');
    const shortlist = byId('area-shortlist');
    shortlist.replaceChildren();
    for (const row of ranked.slice(0, 10)) {
      const item = element('li', '');
      const button = element('button', row.label + ' · ' + row.score + '/100');
      button.className = 'ghost';
      button.onclick = () => showArea(row.id, true);
      item.append(button);
      shortlist.append(item);
    }
    byId('area-export').disabled = !areas.length;
    drawGrid();
    if (selected) showArea(selected);
  } catch (error) {
    if (current === revision) status.textContent = error.message;
  }
}

byId('area-export').onclick = () => {
  const header = 'Area ID,Area,Suitability,Rank';
  let position = 0;
  const csv = areas.map((row) => [row.id, row.label, row.score ?? '', row.score == null ? '' : ++position]
    .map((value) => '"' + String(value).replaceAll('"', '""') + '"').join(','));
  const url = URL.createObjectURL(new Blob([header, '\n', csv.join('\n')], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'localytics-area-scores.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

byId('area-layer').onchange = drawGrid;

form.onsubmit = (event) => { event.preventDefault(); if (grid) rank(); };

explorer.addEventListener('toggle', async () => {
  setAreaLayers();
  if (!explorer.open) {
    closeEvidence();
    return;
  }
  if (grid || loading) return;
  loading = true;
  status.textContent = 'Loading Delhi area data…';
  try {
    ({ grid, factors, groups } = await request('grid'));
    createInputs();
    mountMap();
    await rank();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    loading = false;
  }
});

function closeEvidence() {
  evidence.hidden = true;
  document.body.classList.remove('area-evidence-open');
}

byId('area-back').onclick = closeEvidence;

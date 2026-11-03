// Catalog names come from DPIA. Images remain the existing local artwork.
let catalogAmbitos = [], catalogCategorias = [];
let catalogState = {ambitos: 'loading', categorias: 'loading'};
let catalogGeneration = 0;
const interestSelections = {};
const catalogMessages = {
 es: ['Cargando catálogo…', 'No hay datos disponibles.', 'No se pudo cargar el catálogo.', 'Reintentar', 'Podés continuar y elegir intereses más tarde.'],
 en: ['Loading catalog…', 'No data available.', 'Could not load the catalog.', 'Retry', 'You can continue and choose interests later.'],
 pl: ['Ładowanie katalogu…', 'Brak danych.', 'Nie udało się wczytać katalogu.', 'Spróbuj ponownie', 'Możesz kontynuować i wybrać zainteresowania później.'],
 it: ['Caricamento catalogo…', 'Nessun dato disponibile.', 'Impossibile caricare il catalogo.', 'Riprova', 'Puoi continuare e scegliere gli interessi più tardi.']
};
const catalogLanguage = () => window.DPIAI18N?.language || 'es';
function catalogImage(name) {
 const key = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
 const images = {tecnologia:'laptop.webp', technology:'laptop.webp', technologia:'laptop.webp', moda:'sneakers.webp', fashion:'sneakers.webp', hogar:'sofa.webp', deporte:'football.webp', sports:'football.webp', sport:'football.webp', cocina:'blender.webp', audio:'headphones.webp', industria:'industry.svg', belleza:'beauty.svg'};
 return images[key] || 'industry.svg';
}
function catalogStatus(container, name) {
 const state = catalogState[name], messages = catalogMessages[catalogLanguage()] || catalogMessages.es;
 if (state === 'ready') return false;
 const text = document.createElement('p'); text.className = 'hint'; text.setAttribute('role', 'status');
 text.textContent = messages[state === 'loading' ? 0 : state === 'empty' ? 1 : 2];
 if (name === 'ambitos' && state !== 'loading') text.textContent += ' ' + messages[4];
 container.append(text);
 if (state === 'error' || state === 'empty') {
  const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = messages[3];
  retry.onclick = () => loadCatalogs(); container.append(retry);
 }
 return true;
}
function renderInterests() {
 const grid = document.querySelector('#interestGrid'); grid.replaceChildren();
 if (step === 2) document.querySelector('#nextBtn').disabled = catalogState.ambitos === 'loading';
 if (catalogStatus(grid, 'ambitos')) return;
 for (const item of catalogAmbitos) {
  const id = String(item.ambito_id), button = document.createElement('button');
  button.className = 'interest' + (selected.has(id) ? ' active' : ''); button.dataset.interest = id;
  const image = document.createElement('img'); image.src = '/static/images/' + catalogImage(item.nombre); image.alt = '';
  const label = document.createElement('span'); label.textContent = item.nombre; label.dataset.catalogName = '';
  const check = document.createElement('i'); check.className = 'interest-check'; check.textContent = selected.has(id) ? '✓' : '+';
  button.append(image, label, check);
  button.onclick = () => { selected.has(id) ? selected.delete(id) : selected.add(id); interestSelections[catalogLanguage()] = [...selected]; renderInterests(); };
  grid.append(button);
 }
}
function selectedNames() {
 return catalogAmbitos.filter(item => selected.has(String(item.ambito_id))).map(item => item.nombre);
}
function renderCategories() {
 const grid = document.querySelector('#categoryGrid'); grid.replaceChildren();
 if (catalogStatus(grid, 'categorias')) return;
 const preferred = item => item.ambito_ids.some(id => selected.has(String(id)));
 const items = [...catalogCategorias].sort((a,b) => Number(preferred(b)) - Number(preferred(a)));
 for (const item of items) {
  const button = document.createElement('button'); button.className = 'category'; button.dataset.cat = String(item.categoria_id);
  const image = document.createElement('img'); image.src = '/static/images/' + catalogImage(item.nombre); image.alt = '';
  const label = document.createElement('span'); label.textContent = item.nombre; label.dataset.catalogName = '';
  button.append(image, label);
  button.onclick = () => { show('consultPage'); document.querySelector('#promptText').value = `Buscar productos de ${item.nombre} en ${city}, ${country}. Priorizar publicaciones locales.`; };
  grid.append(button);
 }
}
async function loadCatalogs() {
 const generation = ++catalogGeneration, language = catalogLanguage();
 catalogAmbitos = []; catalogCategorias = [];
 catalogState = {ambitos:'loading', categorias:'loading'};
 renderInterests(); renderCategories();
 await Promise.all(['ambitos','categorias'].map(async name => {
  try {
   const response = await fetch('/api/catalogos/' + name + '?' + new URLSearchParams({idioma:language}), {signal:AbortSignal.timeout(18000)});
   if (!response.ok) throw new Error('catalog');
   const payload = await response.json();
   if (payload.success !== true || !Array.isArray(payload[name])) throw new Error('catalog');
   if (generation !== catalogGeneration) return;
   catalogState[name] = payload[name].length ? 'ready' : 'empty';
   if (name === 'ambitos') {
    catalogAmbitos = payload.ambitos;
    const available = new Set(catalogAmbitos.map(item => String(item.ambito_id)));
    // Migrate old demo names once; keep IDs scoped to their catalog language.
    const legacy = new Set((saved?.catalogVersion ? [] : saved?.selected || []).map(n => n.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()));
    selected = new Set([...(interestSelections[language] || [])].filter(id => available.has(id)));
    if (!saved?.catalogVersion) for (const item of catalogAmbitos) {
     if (legacy.has(item.nombre.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase())) selected.add(String(item.ambito_id));
    }
    interestSelections[language] = [...selected];
   } else catalogCategorias = payload.categorias;
  } catch (_) {
   if (generation !== catalogGeneration) return;
   catalogState[name] = 'error';
  }
  renderInterests(); renderCategories();
 }));
}

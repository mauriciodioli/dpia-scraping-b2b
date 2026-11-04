// Postal IDs stay on the server; the user sees the selected city.
let localCategory = null;
let localPublicationsGeneration = 0, localPublicationsOffset = 0;
async function loadLocalPublications(append = false) {
 const generation = ++localPublicationsGeneration, chosenCountry = country, chosenCity = city;
 const chosenCategory = localCategory?.id || '';
 const params = new URLSearchParams({pais:chosenCountry, ciudad:chosenCity, offset:String(append ? localPublicationsOffset : 0)});
 if (chosenCategory) params.set('categoria_id', chosenCategory);
 document.querySelector('#localPublicationsHeading').textContent = localCategory ? `Publicaciones locales · ${localCategory.name}` : 'Publicaciones locales';
 const grid = document.querySelector('#localPublications'), status = document.querySelector('#localPublicationsStatus');
 const retry = document.querySelector('#retryLocalPublications'), more = document.querySelector('#moreLocalPublications');
 if (!append) { localPublicationsOffset = 0; grid.replaceChildren(); }
 retry.hidden = true; more.hidden = true; status.textContent = 'Cargando publicaciones locales…';
 try {
  const response = await fetch('/api/publicaciones/locales?' + params, {signal:AbortSignal.timeout(20000)});
  const payload = await response.json();
  if (!response.ok || !payload.success || !Array.isArray(payload.publicaciones)) throw new Error('publications');
  if (generation !== localPublicationsGeneration || country !== chosenCountry || city !== chosenCity || (localCategory?.id || '') !== chosenCategory) return;
  for (const item of payload.publicaciones) {
   const card = document.createElement('article'); card.className = 'product';
   const image = document.createElement('img'); image.alt = ''; image.loading = 'lazy'; image.src = '/static/images/industry.svg';
   try { const url = new URL(item.imagen, location.origin); if (item.imagen && ['https:', 'http:'].includes(url.protocol)) image.src = url.href; } catch (_) {}
   image.onerror = () => { image.onerror = null; image.src = '/static/images/industry.svg'; };
   const title = document.createElement('strong'); title.textContent = item.titulo;
   const description = document.createElement('p'); description.textContent = item.descripcion || '';
   const detail = document.createElement('small'); detail.textContent = chosenCity;
   card.append(image, title, description, detail);
   if (item.precio != null) {
    const price = document.createElement('small'); price.textContent = `${item.precio} ${item.moneda || ''}`.trim(); card.append(price);
   }
   card.dataset.catalogName = ''; grid.append(card);
  }
  localPublicationsOffset += payload.publicaciones.length;
  status.textContent = grid.children.length ? '' : 'No hay publicaciones locales disponibles en esta ciudad.';
  more.hidden = !payload.has_more;
 } catch (_) {
  if (generation !== localPublicationsGeneration || country !== chosenCountry || city !== chosenCity || (localCategory?.id || '') !== chosenCategory) return;
  status.textContent = 'No se pudieron cargar las publicaciones locales.'; retry.hidden = false;
  retry.onclick = () => loadLocalPublications(append);
 }
 more.onclick = () => loadLocalPublications(true);
}

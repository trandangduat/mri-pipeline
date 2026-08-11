export function filterImages(images, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) {
    return images;
  }
  return images.filter((image) => `${image.image} ${(image.tools || []).join(' ')}`.toLowerCase().includes(q));
}

export function imageRowKey(image, index) {
  return image.image ? `${image.image}` : `image-${index}`;
}

export function selectAllVisible({images, keys, setKeys, predicate = () => true}) {
  const selected = new Set(keys);
  images.filter(predicate).forEach((image) => selected.add(imageRowKey(image, 0)));
  setKeys(selected);
}

export function selectVisibleWhere({images, keys, setKeys, predicate}) {
  const selected = new Set(keys);
  images.filter(predicate).forEach((image) => selected.add(imageRowKey(image, 0)));
  setKeys(selected);
}

export function unselectVisible({images, keys, setKeys, predicate = () => true}) {
  const selected = new Set(keys);
  images.filter(predicate).forEach((image) => selected.delete(imageRowKey(image, 0)));
  setKeys(selected);
}

export function selectMissing(images, keys, setKeys) {
  selectVisibleWhere({images, keys, setKeys, predicate: (image) => image?.status !== 'Installed'});
}

export function toggleImageKey(keys, key) {
  const next = new Set(keys);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

import type {ToolImage} from '../types/backend';

export type ToolImagePredicate = (image: ToolImage) => boolean;

export function isImageInstalled(image: ToolImage | Record<string, unknown> | null | undefined): boolean {
  if (!image) return false;
  const status = String((image as Record<string, unknown>).status || '').toLowerCase();
  if (status === 'installed' || status === 'present' || status === 'ready') return true;
  if ((image as Record<string, unknown>).present === true || (image as Record<string, unknown>).installed === true)
    return true;
  return false;
}

export function filterImages(images: ToolImage[], query: string): ToolImage[] {
  const q = String(query || '')
    .trim()
    .toLowerCase();
  if (!q) {
    return images;
  }
  return images.filter((image) => `${image.image} ${(image.tools || []).join(' ')}`.toLowerCase().includes(q));
}

export function imageRowKey(image: ToolImage, index: number): string {
  return image.image ? `${image.image}` : `image-${index}`;
}

export function selectAllVisible({
  images,
  keys,
  setKeys,
  predicate = () => true,
}: {
  images: ToolImage[];
  keys: ReadonlySet<string>;
  setKeys: (next: Set<string>) => void;
  predicate?: ToolImagePredicate;
}): void {
  const selected = new Set(keys);
  images.filter(predicate).forEach((image) => selected.add(imageRowKey(image, 0)));
  setKeys(selected);
}

export function selectVisibleWhere({
  images,
  keys,
  setKeys,
  predicate,
}: {
  images: ToolImage[];
  keys: ReadonlySet<string>;
  setKeys: (next: Set<string>) => void;
  predicate: ToolImagePredicate;
}): void {
  const selected = new Set(keys);
  images.filter(predicate).forEach((image) => selected.add(imageRowKey(image, 0)));
  setKeys(selected);
}

export function unselectVisible({
  images,
  keys,
  setKeys,
  predicate = () => true,
}: {
  images: ToolImage[];
  keys: ReadonlySet<string>;
  setKeys: (next: Set<string>) => void;
  predicate?: ToolImagePredicate;
}): void {
  const selected = new Set(keys);
  images.filter(predicate).forEach((image) => selected.delete(imageRowKey(image, 0)));
  setKeys(selected);
}

export function selectMissing(
  images: ToolImage[],
  keys: ReadonlySet<string>,
  setKeys: (next: Set<string>) => void,
): void {
  selectVisibleWhere({images, keys, setKeys, predicate: (image) => !isImageInstalled(image)});
}

export function toggleImageKey(keys: ReadonlySet<string>, key: string): Set<string> {
  const next = new Set(keys);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

import type {ToolImage} from '../types/backend';

export function isImageInstalled(image: ToolImage | Record<string, unknown> | null | undefined): boolean {
  if (!image) return false;
  const status = String((image as Record<string, unknown>).status || '').toLowerCase();
  if (status === 'installed' || status === 'present' || status === 'ready') return true;
  if ((image as Record<string, unknown>).present === true || (image as Record<string, unknown>).installed === true)
    return true;
  return false;
}

export function isImageDownloading(image: ToolImage | Record<string, unknown> | null | undefined): boolean {
  if (!image) return false;
  const status = String((image as Record<string, unknown>).status || '').toLowerCase();
  if (status === 'downloading') return true;
  const pullStatus = String((image as Record<string, unknown>).pull_status || '').toLowerCase();
  if (pullStatus === 'pulling') return true;
  return false;
}

export function isImageFailed(image: ToolImage | Record<string, unknown> | null | undefined): boolean {
  if (!image) return false;
  const status = String((image as Record<string, unknown>).status || '').toLowerCase();
  if (status === 'failed') return true;
  const pullStatus = String((image as Record<string, unknown>).pull_status || '').toLowerCase();
  if (pullStatus === 'failed') return true;
  return false;
}

export function splitByInstallStatus(images: ToolImage[]): {installed: ToolImage[]; missing: ToolImage[]} {
  const installed: ToolImage[] = [];
  const missing: ToolImage[] = [];
  for (const img of images) {
    if (isImageInstalled(img)) {
      installed.push(img);
    } else {
      missing.push(img);
    }
  }
  return {installed, missing};
}

export function imageRowKey(image: ToolImage, index: number): string {
  return image.image || `image-${index}`;
}

export function filterImages(images: ToolImage[], query: string): ToolImage[] {
  const trimmed = query.trim();
  if (!trimmed) return images;
  const lower = trimmed.toLowerCase();
  return images.filter((img) => {
    if (img.image.toLowerCase().includes(lower)) return true;
    return img.tools.some((t) => t.toLowerCase().includes(lower));
  });
}

export function selectAllVisible({
  images,
  keys,
  setKeys,
  predicate,
}: {
  images: ToolImage[];
  keys: Set<string>;
  setKeys: (next: Set<string>) => void;
  predicate?: (image: ToolImage) => boolean;
}): void {
  const next = new Set(keys);
  for (const img of images) {
    if (!predicate || predicate(img)) {
      next.add(imageRowKey(img, 0));
    }
  }
  setKeys(next);
}

export function unselectVisible({
  images,
  keys,
  setKeys,
}: {
  images: ToolImage[];
  keys: Set<string>;
  setKeys: (next: Set<string>) => void;
}): void {
  const next = new Set(keys);
  for (const img of images) {
    next.delete(imageRowKey(img, 0));
  }
  setKeys(next);
}

export function selectMissing(
  images: ToolImage[],
  keys: Set<string>,
  setKeys: (next: Set<string>) => void,
): void {
  const next = new Set(keys);
  for (const img of images) {
    if (!isImageInstalled(img)) {
      next.add(imageRowKey(img, 0));
    }
  }
  setKeys(next);
}

export function toggleImageKey(keys: Set<string>, key: string): Set<string> {
  const next = new Set(keys);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

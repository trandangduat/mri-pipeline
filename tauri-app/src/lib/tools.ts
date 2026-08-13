import type {ToolImage} from '../types/backend';

export function isImageInstalled(image: ToolImage | Record<string, unknown> | null | undefined): boolean {
  if (!image) return false;
  const status = String((image as Record<string, unknown>).status || '').toLowerCase();
  if (status === 'installed' || status === 'present' || status === 'ready') return true;
  if ((image as Record<string, unknown>).present === true || (image as Record<string, unknown>).installed === true)
    return true;
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

import {expect, test} from 'vitest';
import {
  filterImages,
  imageRowKey,
  selectAllVisible,
  unselectVisible,
  selectMissing,
  toggleImageKey,
  isImageInstalled,
} from '../src/lib/tools';

const images = [
  {image: 'nighres/nighres:v1', tools: ['nighres'], status: 'Installed'},
  {image: 'freesurfer/freesurfer:7.4.1', tools: ['freesurfer'], status: 'Missing'},
  {image: 'mrtrix3/mrtrix3:latest', tools: ['mrtrix'], status: 'Installed'},
];

test('isImageInstalled evaluates status field accurately', () => {
  expect(isImageInstalled({status: 'Installed'})).toBe(true);
  expect(isImageInstalled({status: 'installed'})).toBe(true);
  expect(isImageInstalled({status: 'Missing'})).toBe(false);
  expect(isImageInstalled({present: true})).toBe(true);
  expect(isImageInstalled({installed: true})).toBe(true);
  expect(isImageInstalled(null)).toBe(false);
});

test('imageRowKey uses image name when present', () => {
  expect(imageRowKey(images[0]!, 0)).toBe('nighres/nighres:v1');
  expect(imageRowKey({image: '', tools: [], status: 'Missing'}, 2)).toBe('image-2');
});

test('filterImages returns all rows for empty query', () => {
  expect(filterImages(images, '')).toBe(images);
  expect(filterImages(images, '   ')).toBe(images);
});

test('filterImages matches on image name and tool name (case-insensitive)', () => {
  expect(filterImages(images, 'freesurfer').length).toBe(1);
  expect(filterImages(images, 'MRTRIX').length).toBe(1);
  expect(filterImages(images, 'nighres:v1').length).toBe(1);
});

test('filterImages returns empty array for no matches', () => {
  expect(filterImages(images, 'nonexistent').length).toBe(0);
});

test('selectAllVisible selects every visible image', () => {
  let keys = new Set<string>();
  selectAllVisible({
    images,
    keys,
    setKeys: (next) => {
      keys = next;
    },
  });
  expect(keys.size).toBe(3);
});

test('selectAllVisible with predicate only selects matching images', () => {
  let keys = new Set<string>();
  selectAllVisible({
    images,
    keys,
    setKeys: (next) => {
      keys = next;
    },
    predicate: (i) => i.status === 'Installed',
  });
  expect(keys.size).toBe(2);
});

test('unselectVisible removes images while keeping unrelated keys', () => {
  let keys = new Set(['nighres/nighres:v1', 'freesurfer/freesurfer:7.4.1', 'keep']);
  unselectVisible({
    images,
    keys,
    setKeys: (next) => {
      keys = next;
    },
  });
  expect(keys.has('keep')).toBe(true);
  expect(keys.has('nighres/nighres:v1')).toBe(false);
});

test('selectMissing only selects images that are not Installed', () => {
  let keys = new Set<string>();
  selectMissing(images, keys, (next) => {
    keys = next;
  });
  expect(keys.size).toBe(1);
  expect(keys.has('freesurfer/freesurfer:7.4.1')).toBe(true);
});

test('toggleImageKey adds and removes keys', () => {
  let keys = new Set(['a']);
  keys = toggleImageKey(keys, 'b');
  expect(keys.has('b')).toBe(true);
  keys = toggleImageKey(keys, 'a');
  expect(keys.has('a')).toBe(false);
});

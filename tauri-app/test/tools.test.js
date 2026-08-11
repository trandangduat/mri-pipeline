import assert from 'node:assert/strict';
import {test} from 'node:test';
import {filterImages, imageRowKey, selectAllVisible, unselectVisible, selectMissing, toggleImageKey} from '../src/lib/tools.js';

const images = [
  {image: 'nighres/nighres:v1', tools: ['nighres'], status: 'Installed'},
  {image: 'freesurfer/freesurfer:7.4.1', tools: ['freesurfer'], status: 'Missing'},
  {image: 'mrtrix3/mrtrix3:latest', tools: ['mrtrix'], status: 'Installed'},
];

test('imageRowKey uses image name when present', () => {
  assert.equal(imageRowKey(images[0], 0), 'nighres/nighres:v1');
  assert.equal(imageRowKey({image: ''}, 2), 'image-2');
});

test('filterImages returns all rows for empty query', () => {
  assert.equal(filterImages(images, ''), images);
  assert.equal(filterImages(images, '   '), images);
});

test('filterImages matches on image name and tool name (case-insensitive)', () => {
  assert.equal(filterImages(images, 'freesurfer').length, 1);
  assert.equal(filterImages(images, 'MRTRIX').length, 1);
  assert.equal(filterImages(images, 'nighres:v1').length, 1);
});

test('filterImages returns empty array for no matches', () => {
  assert.equal(filterImages(images, 'nonexistent').length, 0);
});

test('selectAllVisible selects every visible image', () => {
  let keys = new Set();
  selectAllVisible({images, keys, setKeys: (next) => { keys = next; }});
  assert.equal(keys.size, 3);
});

test('selectAllVisible with predicate only selects matching images', () => {
  let keys = new Set();
  selectAllVisible({images, keys, setKeys: (next) => { keys = next; }, predicate: (i) => i.status === 'Installed'});
  assert.equal(keys.size, 2);
});

test('unselectVisible removes images while keeping unrelated keys', () => {
  let keys = new Set(['nighres/nighres:v1', 'freesurfer/freesurfer:7.4.1', 'keep']);
  unselectVisible({images, keys, setKeys: (next) => { keys = next; }});
  assert.equal(keys.has('keep'), true);
  assert.equal(keys.has('nighres/nighres:v1'), false);
});

test('selectMissing only selects images that are not Installed', () => {
  let keys = new Set();
  selectMissing(images, keys, (next) => { keys = next; });
  assert.equal(keys.size, 1);
  assert.equal(keys.has('freesurfer/freesurfer:7.4.1'), true);
});

test('toggleImageKey adds and removes keys', () => {
  let keys = new Set(['a']);
  keys = toggleImageKey(keys, 'b');
  assert.equal(keys.has('b'), true);
  keys = toggleImageKey(keys, 'a');
  assert.equal(keys.has('a'), false);
});

import assert from 'node:assert/strict';
import {test} from 'node:test';
import {currentTargetHardware, runtimeWarnings} from '../src/lib/runtime.js';

test('currentTargetHardware reads local environment hardware', () => {
  const hardware = currentTargetHardware({
    runtimeTarget: 'Local',
    environment: {hardware: {logical_cores: 8, total_ram_bytes: 17179869184}},
    remoteResult: {},
  });
  assert.equal(hardware.label, 'Local');
  assert.equal(hardware.connected, true);
  assert.equal(hardware.logicalCores, 8);
  assert.equal(hardware.totalRamBytes, 17179869184);
});

test('currentTargetHardware reads remote hardware when Server target', () => {
  const hardware = currentTargetHardware({
    runtimeTarget: 'Server',
    environment: {},
    remoteResult: {connected: true, logicalCores: 32, totalRamBytes: 68719476736},
  });
  assert.equal(hardware.label, 'Server');
  assert.equal(hardware.connected, true);
  assert.equal(hardware.logicalCores, 32);
});

test('currentTargetHardware reports disconnected Server', () => {
  const hardware = currentTargetHardware({
    runtimeTarget: 'Server',
    environment: {},
    remoteResult: {connected: false},
  });
  assert.equal(hardware.connected, false);
  assert.equal(hardware.logicalCores, null);
});

test('runtimeWarnings flags threads above 90% of max', () => {
  const warnings = runtimeWarnings({
    runtimeTarget: 'Local',
    hardware: {logicalCores: 8, connected: true},
    cpuThreads: 8,
    ramPercent: 40,
  });
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /CPU threads 8/);
});

test('runtimeWarnings flags RAM above 90%', () => {
  const warnings = runtimeWarnings({
    runtimeTarget: 'Local',
    hardware: {logicalCores: 8, connected: true},
    cpuThreads: 2,
    ramPercent: 95,
  });
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /RAM 95%/);
});

test('runtimeWarnings flags disconnected server target', () => {
  const warnings = runtimeWarnings({
    runtimeTarget: 'Server',
    hardware: {logicalCores: null, connected: false},
    cpuThreads: 2,
    ramPercent: 50,
  });
  assert.equal(warnings.some((w) => w.includes('SSH is not connected')), true);
});

test('runtimeWarnings is empty for a healthy local config', () => {
  const warnings = runtimeWarnings({
    runtimeTarget: 'Local',
    hardware: {logicalCores: 16, connected: true},
    cpuThreads: 4,
    ramPercent: 50,
  });
  assert.deepEqual(warnings, []);
});

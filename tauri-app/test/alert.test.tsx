import {expect, test} from 'vitest';
import {render} from '@testing-library/react';
import {Alert} from '../src/components/ui';

test('Alert severity warning renders orange warn tokens with triangle icon', () => {
  const {container} = render(<Alert severity="warning">Watch out</Alert>);
  const el = container.querySelector('[role="alert"]');
  expect(el).not.toBeNull();
  expect(el!.className).toMatch(/border-cursor-semantic-warn\/40/);
  expect(el!.className).toMatch(/bg-cursor-semantic-warn\/10/);
  expect(el!.className).toMatch(/text-cursor-semantic-warn/);
  expect(el!.querySelector('svg')).not.toBeNull();
  expect(el!.textContent).toContain('Watch out');
});

test('Alert severity error renders red error tokens', () => {
  const {container} = render(<Alert severity="error">Broken</Alert>);
  const el = container.querySelector('[role="alert"]')!;
  expect(el.className).toMatch(/border-cursor-semantic-error\/30/);
  expect(el.className).toMatch(/bg-cursor-semantic-error\/10/);
  expect(el.className).toMatch(/text-cursor-semantic-error/);
});

test('Alert size sm vs md produce different padding and radius', () => {
  const sm = render(<Alert severity="warning" size="sm">s</Alert>);
  const md = render(<Alert severity="warning" size="md">m</Alert>);
  expect(sm.container.querySelector('[role="alert"]')!.className).toMatch(/rounded-md/);
  expect(md.container.querySelector('[role="alert"]')!.className).toMatch(/rounded-lg/);
});

test('Alert icon=false hides the glyph; custom node is rendered', () => {
  const noIcon = render(<Alert severity="error" icon={false}>plain</Alert>);
  expect(noIcon.container.querySelector('svg')).toBeNull();

  const custom = render(
    <Alert severity="error" icon={<span data-testid="custom-icon" />}>
      custom
    </Alert>,
  );
  expect(custom.container.querySelector('[data-testid="custom-icon"]')).not.toBeNull();
});

import {expect, test} from 'vitest';
import {render} from '@testing-library/react';
import {Alert} from '../src/components/ui';

test('Alert severity warning renders badge with Warning text, triangle icon and no border', () => {
  const {container} = render(<Alert severity="warning">Watch out</Alert>);
  const el = container.querySelector('[role="alert"]');
  expect(el).not.toBeNull();
  expect(el!.className).toMatch(/border-none/);
  expect(el!.className).toMatch(/bg-amber-500\/10/);
  expect(el!.querySelector('svg')).not.toBeNull();
  expect(el!.textContent).toContain('Warning');
  expect(el!.textContent).toContain('Watch out');
});

test('Alert severity error renders badge with Error and rose tokens', () => {
  const {container} = render(<Alert severity="error">Broken</Alert>);
  const el = container.querySelector('[role="alert"]')!;
  expect(el.className).toMatch(/border-none/);
  expect(el.className).toMatch(/bg-rose-500\/10/);
  expect(el.textContent).toContain('Error');
  expect(el.textContent).toContain('Broken');
});

test('Alert severity success renders badge with Success and emerald tokens', () => {
  const {container} = render(<Alert severity="success">All good</Alert>);
  const el = container.querySelector('[role="alert"]')!;
  expect(el.className).toMatch(/border-none/);
  expect(el.className).toMatch(/bg-emerald-500\/10/);
  expect(el.textContent).toContain('Success');
  expect(el.textContent).toContain('All good');
});

test('Alert size sm vs md produce different padding and radius', () => {
  const sm = render(<Alert severity="warning" size="sm">s</Alert>);
  const md = render(<Alert severity="warning" size="md">m</Alert>);
  expect(sm.container.querySelector('[role="alert"]')!.className).toMatch(/rounded-lg/);
  expect(md.container.querySelector('[role="alert"]')!.className).toMatch(/rounded-xl/);
});

test('Alert renders list children directly with uniform text-xs', () => {
  const {container} = render(
    <Alert severity="warning">
      <ul className="list-disc">
        <li>Issue 1</li>
        <li>Issue 2</li>
      </ul>
    </Alert>,
  );
  const listItems = container.querySelectorAll('li');
  expect(listItems.length).toBe(2);
  expect(listItems[0].textContent).toContain('Issue 1');
  expect(listItems[1].textContent).toContain('Issue 2');
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

import React from 'react';
import {createPortal} from 'react-dom';

/**
 * Renders modal overlays directly under <body> so they escape ancestor
 * stacking contexts (sticky header z-30, page containers, ...).
 * Without this, `fixed z-50` dialogs lose to the sticky footer (z-30, later
 * in DOM order) and never cover the bottom status line.
 */
export function ModalPortal({children}: {children: React.ReactNode}) {
  return createPortal(children, document.body);
}

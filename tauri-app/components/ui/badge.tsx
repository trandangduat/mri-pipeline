import React from 'react';
import {cva, type VariantProps} from 'class-variance-authority';
import {cn} from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.06em] transition-colors focus:outline-none',
  {
    variants: {
      variant: {
        default: 'bg-cursor-primary/10 text-cursor-primary',
        primary: 'bg-cursor-primary/10 text-cursor-primary',
        secondary: 'bg-cursor-surface-strong/70 text-cursor-body',
        outline: 'border border-cursor-hairline bg-cursor-surface-card text-cursor-ink',
        success: 'bg-cursor-semantic-success/10 text-cursor-semantic-success',
        running: 'bg-cursor-primary/10 text-cursor-primary animate-pulse',
        destructive: 'bg-cursor-semantic-error/10 text-cursor-semantic-error',
        error: 'bg-cursor-semantic-error/10 text-cursor-semantic-error',
        warning: 'bg-cursor-semantic-warn/10 text-cursor-semantic-warn',
        skipped: 'bg-cursor-canvas-soft text-cursor-muted-soft opacity-70',
        not_scheduled: 'bg-cursor-canvas-soft text-cursor-muted opacity-50 font-normal',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

function Badge({className, variant, ...props}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({variant, className}))} {...props} />;
}

export {Badge, badgeVariants};

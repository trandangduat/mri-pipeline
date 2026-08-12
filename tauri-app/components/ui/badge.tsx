import React from 'react';
import {cva, type VariantProps} from 'class-variance-authority';
import {cn} from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider transition-colors focus:outline-none font-mono',
  {
    variants: {
      variant: {
        default: 'border-[#0077b6]/20 bg-[#0077b6]/10 text-[#0077b6]',
        secondary: 'border-[#e6e5e0] bg-[#f7f7f4] text-[#5a5852]',
        outline: 'border-[#e6e5e0] bg-white text-[#26251e]',
        success: 'border-emerald-200 bg-emerald-50/60 text-emerald-700',
        running: 'border-blue-300 bg-blue-50/70 text-blue-700 animate-pulse',
        destructive: 'border-rose-200 bg-rose-50/60 text-rose-700',
        skipped: 'border-[#e6e5e0] bg-[#f7f7f4] text-[#807d72] opacity-70',
        not_scheduled: 'border-[#e6e5e0] bg-[#f7f7f4] text-[#807d72] opacity-50 font-normal',
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

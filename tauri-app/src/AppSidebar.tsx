import React, {useCallback, useState} from 'react';
import {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarMenuBadge,
  SidebarMenuSub,
  SidebarMenuSubItem,
  SidebarMenuSubButton,
  SidebarFooter,
  SidebarTrigger,
} from '@/components/ui/sidebar';
import {Activity, BrainCircuit, Container, SlidersHorizontal} from 'lucide-react';
import type {AppTab} from './stores/uiStore';
import {displayJobState, sidebarDotClass} from './lib/jobs';
import {jobBasename, sortJobsByStartedAtDesc} from './jobFormatters';

const SIDEBAR_JOBS_PER_GROUP = 3;

export interface AppSidebarProps {
  activeTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
  jobs?: unknown[];
  selectedJobId?: string | null;
  onSelectJob?: (jobId: string) => void;
  envText?: string;
  sidebarOpen: boolean;
  onSidebarOpenChange: (open: boolean) => void;
  sidebarWidth: number;
  onSidebarWidthChange: (width: number) => void;
}

export function AppSidebar({
  activeTab,
  onSelectTab,
  jobs = [],
  selectedJobId,
  onSelectJob,
  envText,
  sidebarOpen,
  onSidebarOpenChange,
  sidebarWidth,
  onSidebarWidthChange,
}: AppSidebarProps) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const sortedJobs = sortJobsByStartedAtDesc((jobs as Record<string, unknown>[]).filter(Boolean));
  const groupedJobs = [
    {label: 'Local', jobs: sortedJobs.filter((job) => String(job.target || 'Local') !== 'Server')},
    {label: 'Server', jobs: sortedJobs.filter((job) => String(job.target || 'Local') === 'Server')},
  ];

  const startResize = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!sidebarOpen) return;
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = sidebarWidth;

      const onMove = (moveEvent: PointerEvent) => {
        onSidebarWidthChange(startWidth + moveEvent.clientX - startX);
      };
      const onUp = () => {
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
    },
    [onSidebarWidthChange, sidebarOpen, sidebarWidth],
  );

  return (
    <SidebarProvider open={sidebarOpen} onOpenChange={onSidebarOpenChange} style={{'--sidebar-width': `${sidebarWidth}px`} as React.CSSProperties}>
      <Sidebar
        collapsible="icon"
        className="font-sans border-r border-cursor-hairline bg-sidebar text-cursor-ink"
      >
        <SidebarHeader className="border-b border-cursor-hairline px-4 py-3 flex flex-row items-center justify-between gap-2 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:justify-center">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-cursor-primary text-white">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div className="flex flex-col min-w-0 group-data-[collapsible=icon]:hidden">
              <strong className="truncate text-sm font-semibold tracking-tight text-cursor-ink">NeuroFlow</strong>
              <span className="text-[11px] font-mono text-cursor-body">MRI Pipeline</span>
            </div>
          </div>
        </SidebarHeader>

        <SidebarContent className="px-3 py-4 group-data-[collapsible=icon]:px-0">
          <SidebarMenu className="gap-2">
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'pipeline'}
                onClick={() => onSelectTab('pipeline')}
                tooltip="Pipeline Configuration"
                className="h-10 text-[15px] font-medium"
              >
                <SlidersHorizontal className="h-4.5 w-4.5" />
                <span className="group-data-[collapsible=icon]:hidden">Pipeline Configuration</span>
              </SidebarMenuButton>
            </SidebarMenuItem>

            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'tools'}
                onClick={() => onSelectTab('tools')}
                tooltip="Tools Configuration"
                className="h-10 text-[15px] font-medium"
              >
                <Container className="h-4.5 w-4.5" />
                <span className="group-data-[collapsible=icon]:hidden">Tools Configuration</span>
              </SidebarMenuButton>
            </SidebarMenuItem>

            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'jobs'}
                onClick={() => onSelectTab('jobs')}
                tooltip="Jobs Monitor"
                className="h-10 text-[15px] font-medium"
              >
                <Activity className="h-4.5 w-4.5" />
                <span className="group-data-[collapsible=icon]:hidden">Jobs Monitor</span>
                <SidebarMenuBadge className="bg-cursor-hairline text-cursor-ink text-xs">{jobs.length}</SidebarMenuBadge>
              </SidebarMenuButton>

              <SidebarMenuSub className="ml-4 mt-1 border-l border-cursor-hairline pl-2.5">
                {jobs.length === 0 ? (
                  <SidebarMenuSubItem>
                    <span className="block rounded-md bg-cursor-canvas-soft px-2.5 py-1.5 text-[12px] italic text-cursor-body">
                      No active jobs
                    </span>
                  </SidebarMenuSubItem>
                ) : (
                  groupedJobs.map((group) => {
                    if (group.jobs.length === 0) return null;
                    const isExpanded = Boolean(expandedGroups[group.label]);
                    const visibleJobs = isExpanded ? group.jobs : group.jobs.slice(0, SIDEBAR_JOBS_PER_GROUP);
                    const hiddenCount = group.jobs.length - SIDEBAR_JOBS_PER_GROUP;

                    return (
                      <React.Fragment key={group.label}>
                        <SidebarMenuSubItem>
                          <span className="mt-2 block px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-cursor-muted">
                            {group.label}
                          </span>
                        </SidebarMenuSubItem>
                        {visibleJobs.map((job) => {
                          const isSelected = selectedJobId === job.job_id;
                          const stateCls = sidebarDotClass(job);
                          const title = jobBasename(job.display_name || job.job_id || job.remote_job_dir || job.job_dir);
                          const subtitle = displayJobState(job.state);

                          return (
                            <SidebarMenuSubItem key={String(job.job_id || job.remote_job_dir || job.job_dir || title)}>
                              <SidebarMenuSubButton
                                isActive={isSelected}
                                onClick={() => {
                                  onSelectTab('jobs');
                                  onSelectJob?.(String(job.job_id || ''));
                                }}
                                className="min-h-11 text-[13px] flex items-center justify-between gap-2 cursor-pointer rounded-lg border border-transparent px-2 py-2 data-active:bg-cursor-primary/10 data-active:text-cursor-ink data-active:hover:bg-cursor-primary/15"
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className={`h-2 w-2 rounded-full flex-none ${stateCls}`} />
                                  <span className="grid min-w-0 gap-0.5">
                                    <span className="truncate text-[13px] font-medium text-cursor-ink">{title}</span>
                                    <span className="truncate text-[10px] uppercase tracking-[0.08em] text-cursor-muted">{subtitle}</span>
                                  </span>
                                </div>
                              </SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          );
                        })}
                        {hiddenCount > 0 ? (
                          <SidebarMenuSubItem>
                            <SidebarMenuSubButton
                              onClick={(event) => {
                                event.preventDefault();
                                onSelectTab('jobs');
                                setExpandedGroups((prev) => ({...prev, [group.label]: !prev[group.label]}));
                              }}
                              className="h-8 cursor-pointer rounded-lg px-2 text-[12px] text-cursor-body hover:bg-cursor-canvas-soft"
                            >
                              {isExpanded
                                ? 'Show fewer server jobs'
                                : `View all ${group.label.toLowerCase()} jobs (${hiddenCount} more)`}
                            </SidebarMenuSubButton>
                          </SidebarMenuSubItem>
                        ) : null}
                      </React.Fragment>
                    );
                  })
                )}
              </SidebarMenuSub>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarContent>

        <SidebarFooter className="border-t border-cursor-hairline p-3 text-xs text-cursor-body">
          <div id="environmentList" className="group-data-[collapsible=icon]:hidden">
            {envText || 'Backend ready'}
          </div>
        </SidebarFooter>
      </Sidebar>
      <div
        className="fixed top-4 z-40"
        style={{left: sidebarOpen ? `${sidebarWidth + 16}px` : '72px'}}
      >
        <SidebarTrigger className="h-10 w-10 shrink-0 rounded-lg border border-cursor-hairline bg-white shadow-none transition-none hover:bg-cursor-canvas-soft text-cursor-ink [&_svg]:size-4" />
      </div>
    </SidebarProvider>
  );
}

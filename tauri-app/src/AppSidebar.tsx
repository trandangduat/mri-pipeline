import React from 'react';
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

export interface AppSidebarProps {
  activeTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
  jobs?: unknown[];
  selectedJobId?: string | null;
  onSelectJob?: (jobId: string) => void;
  envText?: string;
  sidebarOpen: boolean;
  onSidebarOpenChange: (open: boolean) => void;
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
}: AppSidebarProps) {
  return (
    <SidebarProvider open={sidebarOpen} onOpenChange={onSidebarOpenChange}>
      <Sidebar
        collapsible="icon"
        className="font-sans border-r border-cursor-hairline bg-cursor-canvas text-cursor-ink"
      >
        <SidebarHeader className="border-b border-cursor-hairline px-4 py-3 flex flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-cursor-primary text-white">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div className="flex flex-col min-w-0 group-data-[collapsible=icon]:hidden">
              <strong className="truncate text-sm font-semibold tracking-tight text-cursor-ink">NeuroFlow</strong>
              <span className="text-[11px] font-mono text-cursor-body">MRI Pipeline</span>
            </div>
          </div>
          <SidebarTrigger className="flex-none" />
        </SidebarHeader>

        <SidebarContent className="px-3 py-4">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'pipeline'}
                onClick={() => onSelectTab('pipeline')}
                tooltip="Pipeline Configuration"
                className="h-10 text-sm"
              >
                <SlidersHorizontal className="h-4 w-4" />
                <span className="group-data-[collapsible=icon]:hidden">Pipeline Configuration</span>
              </SidebarMenuButton>
            </SidebarMenuItem>

            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'tools'}
                onClick={() => onSelectTab('tools')}
                tooltip="Tools Configuration"
                className="h-10 text-sm"
              >
                <Container className="h-4 w-4" />
                <span className="group-data-[collapsible=icon]:hidden">Tools Configuration</span>
              </SidebarMenuButton>
            </SidebarMenuItem>

            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={activeTab === 'jobs'}
                onClick={() => onSelectTab('jobs')}
                tooltip="Jobs Monitor"
                className="h-10 text-sm"
              >
                <Activity className="h-4 w-4" />
                <span className="group-data-[collapsible=icon]:hidden">Jobs Monitor</span>
                <SidebarMenuBadge className="bg-cursor-hairline text-cursor-ink">{jobs.length}</SidebarMenuBadge>
              </SidebarMenuButton>

              <SidebarMenuSub className="ml-4 mt-1 border-l border-cursor-hairline pl-2.5">
                {jobs.length === 0 ? (
                  <SidebarMenuSubItem>
                    <span className="block rounded-md bg-cursor-canvas-soft px-2.5 py-1.5 text-xs italic text-cursor-body">
                      No active jobs
                    </span>
                  </SidebarMenuSubItem>
                ) : (
                  jobs.map((jobItem) => {
                    const job = jobItem as Record<string, unknown>;
                    const isSelected = selectedJobId === job.job_id;
                    const stateCls =
                      job.state === 'running'
                        ? 'bg-cursor-timeline-read animate-pulse'
                        : job.state === 'completed'
                          ? 'bg-cursor-semantic-success'
                          : 'bg-cursor-semantic-error';

                    return (
                      <SidebarMenuSubItem key={String(job.job_id || '')}>
                        <SidebarMenuSubButton
                          isActive={isSelected}
                          onClick={() => {
                            onSelectTab('jobs');
                            onSelectJob?.(String(job.job_id || ''));
                          }}
                          className="min-h-9 text-xs flex items-center justify-between gap-2 cursor-pointer"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className={`h-2 w-2 rounded-full flex-none ${stateCls}`} />
                            <span className="truncate">{String(job.display_name || job.job_id || '')}</span>
                          </div>
                          <span className="rounded border border-cursor-hairline bg-white px-1.5 py-0.5 text-[10px] font-mono uppercase text-cursor-body">
                            {String(job.target || 'Local')}
                          </span>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
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
    </SidebarProvider>
  );
}

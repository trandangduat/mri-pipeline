import React from 'react';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {DualPaneTransferModal} from '../src/components/DualPaneTransferModal';

const mockBrowseLocal = vi.fn();
const mockBrowseRemote = vi.fn();
const mockUploadStage = vi.fn();
const mockRemoteMkdir = vi.fn();

vi.mock('../src/query/useEnvironment', () => ({
  useClient: () => ({
    browseLocalPath: (...args: unknown[]) => mockBrowseLocal(...args),
    browseRemotePath: (...args: unknown[]) => mockBrowseRemote(...args),
    uploadStage: (...args: unknown[]) => mockUploadStage(...args),
    remoteMkdir: (...args: unknown[]) => mockRemoteMkdir(...args),
  }),
}));

vi.mock('../src/query/useRemote', () => ({
  useLocalBrowseMutation: () => ({
    mutate: (payload: {path: string; purpose?: string; recursive?: boolean}, options?: {onSuccess?: (res: unknown) => void}) => {
      const res = mockBrowseLocal(payload);
      if (options?.onSuccess) options.onSuccess(res);
    },
    isPending: false,
  }),
  useRemoteBrowseMutation: () => ({
    mutate: (payload: Record<string, unknown>, options?: {onSuccess?: (res: unknown) => void}) => {
      const res = mockBrowseRemote(payload);
      if (options?.onSuccess) options.onSuccess(res);
    },
    isPending: false,
  }),
  useUploadStageMutation: () => ({
    mutate: (payload: Record<string, unknown>, options?: {onSuccess?: (res: unknown) => void}) => {
      const res = mockUploadStage(payload);
      if (options?.onSuccess) options.onSuccess(res);
    },
    isPending: false,
  }),
  useRemoteMkdirMutation: () => ({
    mutate: (payload: Record<string, unknown>, options?: {onSuccess?: (res: unknown) => void}) => {
      const res = mockRemoteMkdir(payload);
      if (options?.onSuccess) options.onSuccess(res);
    },
    isPending: false,
  }),
}));

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {queries: {retry: false}},
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('DualPaneTransferModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockBrowseLocal.mockReturnValue({
      ok: true,
      path: '/home/user/local-data',
      parent: '/home/user',
      dirs: [
        {name: 'sub-01', path: '/home/user/local-data/sub-01', kind: 'directory', selectable: true, is_dicom_series: false},
      ],
      files: [
        {name: 'scan1.nii.gz', path: '/home/user/local-data/scan1.nii.gz', kind: 'file', selectable: true, is_dicom_series: false, size: 1024},
      ],
      entries: [
        {name: 'sub-01', path: '/home/user/local-data/sub-01', kind: 'directory', selectable: true, is_dicom_series: false},
        {name: 'scan1.nii.gz', path: '/home/user/local-data/scan1.nii.gz', kind: 'file', selectable: true, is_dicom_series: false, size: 1024},
      ],
    });

    mockBrowseRemote.mockReturnValue({
      ok: true,
      path: '/remote/workspace',
      parent: '/remote',
      dirs: [
        {name: 'existing_dir', path: '/remote/workspace/existing_dir', kind: 'directory', selectable: true},
      ],
      files: [],
      entries: [
        {name: 'existing_dir', path: '/remote/workspace/existing_dir', kind: 'directory', selectable: true},
      ],
    });

    mockUploadStage.mockReturnValue({ok: true, uploaded_count: 1});
    mockRemoteMkdir.mockReturnValue({ok: true, path: '/remote/workspace/new_sub'});
  });

  it('renders both Local Computer and Remote Server panes with entries', () => {
    renderWithClient(
      <DualPaneTransferModal
        onClose={vi.fn()}
        remotePayload={{host: 'server', username: 'alice'}}
        initialLocalPath="/home/user/local-data"
        initialRemotePath="/remote/workspace"
      />,
    );

    expect(screen.getByText('Local Computer')).toBeInTheDocument();
    expect(screen.getByText('Remote Server (SSH)')).toBeInTheDocument();
    expect(screen.getByText('scan1.nii.gz')).toBeInTheDocument();
    expect(screen.getByText('existing_dir')).toBeInTheDocument();
  });

  it('allows selecting items on the left and uploading to the right remote directory', async () => {
    const user = userEvent.setup();
    renderWithClient(
      <DualPaneTransferModal
        onClose={vi.fn()}
        remotePayload={{host: 'server', username: 'alice'}}
        initialLocalPath="/home/user/local-data"
        initialRemotePath="/remote/workspace"
      />,
    );

    // Select scan1.nii.gz
    const checkbox = screen.getByLabelText('Select scan1.nii.gz');
    await user.click(checkbox);

    expect(screen.getByText('1 selected')).toBeInTheDocument();

    // Click Upload button
    const uploadBtn = screen.getByText('Upload ->');
    await user.click(uploadBtn);

    expect(mockUploadStage).toHaveBeenCalledWith(
      expect.objectContaining({
        local_paths: ['/home/user/local-data/scan1.nii.gz'],
        remote_path: '/remote/workspace',
      }),
    );
    expect(screen.getByText(/Successfully uploaded 1 item/)).toBeInTheDocument();
  });

  it('supports creating a new remote folder', async () => {
    const user = userEvent.setup();
    renderWithClient(
      <DualPaneTransferModal
        onClose={vi.fn()}
        remotePayload={{host: 'server', username: 'alice'}}
        initialLocalPath="/home/user/local-data"
        initialRemotePath="/remote/workspace"
      />,
    );

    // Click New Folder button
    const newFolderBtn = screen.getByTitle('Create new remote folder');
    await user.click(newFolderBtn);

    expect(screen.getByText('Create Remote Folder')).toBeInTheDocument();

    // Enter name
    const folderInput = screen.getByLabelText('New folder name');
    await user.type(folderInput, 'new_sub');

    // Click Create
    const createBtn = screen.getByRole('button', {name: 'Create'});
    await user.click(createBtn);

    expect(mockRemoteMkdir).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/remote/workspace/new_sub',
      }),
    );
  });

  it('supports Set as Input Location button', async () => {
    const user = userEvent.setup();
    const handleSet = vi.fn();
    renderWithClient(
      <DualPaneTransferModal
        onClose={vi.fn()}
        remotePayload={{host: 'server', username: 'alice'}}
        initialLocalPath="/home/user/local-data"
        initialRemotePath="/remote/workspace"
        onSetInputLocation={handleSet}
      />,
    );

    const setBtn = screen.getByText('Set as Input Location');
    await user.click(setBtn);

    expect(handleSet).toHaveBeenCalledWith('/remote/workspace');
  });
});

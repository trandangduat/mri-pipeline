import React from 'react';
import {describe, it, expect, vi} from 'vitest';
import {render, screen, fireEvent} from '@testing-library/react';
import {ConfirmDialog} from '../src/components/ConfirmDialog';

describe('ConfirmDialog', () => {
  it('does not render when open is false', () => {
    render(
      <ConfirmDialog
        open={false}
        title="Delete Job"
        description="Are you sure?"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders title, description, entity name, and buttons when open', () => {
    render(
      <ConfirmDialog
        open={true}
        title="Delete Job"
        description="Are you sure you want to delete this job?"
        entityName="remote_job_20260819_182002"
        confirmLabel="Delete Job"
        cancelLabel="Cancel"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Delete Job'})).toBeInTheDocument();
    expect(screen.getByText('Are you sure you want to delete this job?')).toBeInTheDocument();
    expect(screen.getByText('remote_job_20260819_182002')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Delete Job'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Cancel'})).toBeInTheDocument();
  });

  it('calls onConfirm when confirm button is clicked', () => {
    const handleConfirm = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        title="Stop Job"
        description="Stop current execution?"
        confirmLabel="Stop Job"
        onConfirm={handleConfirm}
        onClose={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', {name: 'Stop Job'}));
    expect(handleConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when cancel button is clicked', () => {
    const handleClose = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        title="Remove Docker Image"
        description="Remove from disk?"
        cancelLabel="Cancel"
        onConfirm={vi.fn()}
        onClose={handleClose}
      />
    );

    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape key is pressed', () => {
    const handleClose = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        title="Delete Job"
        description="Are you sure?"
        onConfirm={vi.fn()}
        onClose={handleClose}
      />
    );

    fireEvent.keyDown(window, {key: 'Escape'});
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('renders loading state and disables buttons when isLoading is true', () => {
    const handleClose = vi.fn();
    render(
      <ConfirmDialog
        open={true}
        title="Delete Job"
        description="Permanent removal notice"
        confirmLabel="Delete Job"
        confirmLoadingLabel="Deleting..."
        isLoading={true}
        onConfirm={vi.fn()}
        onClose={handleClose}
      />
    );

    expect(screen.getByRole('button', {name: 'Deleting...'})).toBeInTheDocument();
    const buttons = screen.getAllByRole('button');
    buttons.forEach((button) => {
      expect(button).toBeDisabled();
    });

    // Escape should not trigger onClose while loading
    fireEvent.keyDown(window, {key: 'Escape'});
    expect(handleClose).not.toHaveBeenCalled();
  });
});

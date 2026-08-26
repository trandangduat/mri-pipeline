import {render, screen} from '@testing-library/react';
import {InstalledImageCard, MissingImageCard} from '../src/components/ImageCard';
import type {ToolImage} from '../src/types/backend';

const image: ToolImage = {
  image: 'example/image:latest',
  status: 'Installed',
  tools: ['example'],
  disk_usage: '41.3 GB',
  content_size: '13.3 GB',
};

it('shows distinct disk usage and content size for an installed image', () => {
  render(<InstalledImageCard image={image} />);

  expect(screen.getByTitle(/^Docker's total local disk usage/)).toHaveTextContent('Disk41.3 GB');
  expect(screen.getByTitle(/Stored image content size/)).toHaveTextContent('Content13.3 GB');
});

it('shows compressed download size without installed metadata for a missing image', () => {
  render(<MissingImageCard image={{...image, status: 'Missing', download_size: '13.3 GB'}} />);

  expect(screen.getByTitle(/Estimated compressed registry layer data/)).toHaveTextContent('Download~13.3 GB');
  expect(screen.queryByText('Disk')).not.toBeInTheDocument();
  expect(screen.queryByText('Content')).not.toBeInTheDocument();
});

it('shows an unavailable fallback when a missing image has no download size', () => {
  render(<MissingImageCard image={{...image, status: 'Missing'}} />);

  expect(screen.getByText('Download size unavailable')).toBeInTheDocument();
});

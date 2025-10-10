import type { PageLoad } from './$types';

// Disable SSR to prevent Plyr module resolution errors
export const ssr = false;

export const load: PageLoad = ({ params }) => {
  return {
    id: params.id
  };
};

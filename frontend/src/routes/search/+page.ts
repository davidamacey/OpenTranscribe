import type { PageLoad } from './$types';

export const ssr = false;

export const load: PageLoad = ({ url }) => {
  return {
    query: url.searchParams.get('q') || '',
  };
};

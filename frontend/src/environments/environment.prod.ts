export const environment = {
  production: true,
  apiBase: '/api/v1',
  wsBase: `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`,
};

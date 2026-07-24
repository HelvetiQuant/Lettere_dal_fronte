(function (global) {
  'use strict';

  const routes = [];
  let currentPath = '';

  function parseHash() {
    const hash = global.location.hash.slice(1) || '/';
    const [path, queryStr] = hash.split('?');
    const query = {};
    if (queryStr) {
      for (const pair of queryStr.split('&')) {
        const [k, v] = pair.split('=');
        query[decodeURIComponent(k)] = decodeURIComponent(v || '');
      }
    }
    return { path: path || '/', query };
  }

  function buildHash(path, query) {
    let hash = path;
    if (query && Object.keys(query).length > 0) {
      const qs = Object.entries(query)
        .filter(([, v]) => v != null && v !== '')
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join('&');
      if (qs) hash += '?' + qs;
    }
    return hash;
  }

  var _handling = false;

  function navigate(path, query) {
    const hash = buildHash(path, query);
    if (global.location.hash !== '#' + hash) {
      global.location.hash = hash;
    } else if (!_handling) {
      handleRoute();
    }
  }

  function handleRoute() {
    if (_handling) return;
    _handling = true;
    try {
      const { path, query } = parseHash();
      currentPath = path;
      for (const route of routes) {
        const match = matchRoute(route.pattern, path);
        if (match) {
          route.handler(match.params, query);
          return;
        }
      }
      if (routes.length > 0) {
        routes[routes.length - 1].handler({}, query);
      }
    } finally {
      _handling = false;
    }
  }

  function matchRoute(pattern, path) {
    const patternParts = pattern.split('/').filter(Boolean);
    const pathParts = path.split('/').filter(Boolean);
    if (patternParts.length !== pathParts.length) return null;
    const params = {};
    for (let i = 0; i < patternParts.length; i++) {
      if (patternParts[i].startsWith(':')) {
        params[patternParts[i].slice(1)] = decodeURIComponent(pathParts[i]);
      } else if (patternParts[i] !== pathParts[i]) {
        return null;
      }
    }
    return { params };
  }

  function register(pattern, handler) {
    routes.push({ pattern, handler });
    return { pattern, handler };
  }

  function setDefault(handler) {
    routes.push({ pattern: '*', handler });
  }

  function init() {
    global.addEventListener('hashchange', handleRoute);
    handleRoute();
  }

  function getPath() { return currentPath; }

  global.Router = {
    navigate,
    register,
    setDefault,
    init,
    getPath,
    parseHash,
    buildHash,
  };
})(typeof window !== 'undefined' ? window : this);
